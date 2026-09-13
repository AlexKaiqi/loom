"""Public NATS references and the separate full R20 control wrapper."""
from pathlib import Path
from .values import encode,decode,sha,same,fail,original_request
from .persistence import save_once,read_file

class Receipts:
    def _receipt_path(self,row):
        digest=sha(encode(original_request(row)))
        return Path(self.profile['input_root']).parent/'event-receipts'/(digest+'.puback')

    def _facility(self,row,msg):
        payload=row['payload'];body=self._message(msg,row['namespace'])
        if msg.subject!=payload['subject'] or sha(msg.data)!=payload['event_sha256'] or len(msg.data)!=payload['event_bytes']:
            fail('reference_invalid','original event bytes or subject differ from accepted request')
        if body['request_id']!=row['id'] or body['source']!=row['principal']:fail('reference_invalid','original event source/identity differs')
        return {'owner':'E','kind':'event','request_id':row['id'],'namespace':row['namespace'],'source':row['principal'],'sequence':msg.seq,'subject':msg.subject,'sha256':sha(msg.data)}

    def _negative(self,row,raw,path):
        value=decode(raw);error=value.get('error') if type(value) is dict else None
        if type(error) is not dict or set(error)!={'code','err_code','description'} or type(error['code']) is not int or type(error['err_code']) is not int or type(error['description']) is not str or not error['description']:
            fail('reference_invalid','original response is not a definite NATS error')
        return {'owner':'E','kind':'delivery_receipt','outcome':'rejected','request_id':row['id'],'namespace':row['namespace'],'source':row['principal'],'subject':row['payload']['subject'],'error':error,'receipt_path':str(path),'sha256':sha(raw)}

    def _wrapper(self,row,facility,outcome):
        value={'owner':'E','kind':'delivery_receipt','id':row['id']+'.receipt','request_id':row['id'],'namespace':row['namespace'],'source':row['principal'],'delivery_owner':'E','request_digest':sha(encode(original_request(row))),'outcome':outcome,'definite':True,'facility_ref':facility}
        return {**value,'sha256':sha(encode(value))}

    def _confirm(self,row,facility,outcome):
        wrapper=self._wrapper(row,facility,outcome)
        self.control.confirm_delivery(self.runtime,row['id'],wrapper)
        return {'status':'CONFIRMED' if outcome=='positive' else 'REJECTED','request_id':row['id'],'receipt_ref':facility}

    async def _confirmed(self,row):
        wrapper=row['receipt_ref'];outcome=wrapper.get('outcome');facility=wrapper.get('facility_ref')
        if outcome not in ('positive','negative') or not same(wrapper,self._wrapper(row,facility,outcome)):
            fail('reference_invalid','stored control wrapper differs from complete original request')
        if outcome=='positive':
            msg=await self._get_original(row['namespace'],seq=facility['sequence'])
            if not same(facility,self._facility(row,msg)):fail('reference_invalid','original confirmed facility changed')
        else:
            path=self._receipt_path(row)
            if not same(facility,self._negative(row,read_file(path),path)):fail('reference_invalid','original negative receipt changed')
        # R independently rechecks its authority; generic confirmed is not an event status.
        return self._confirm(row,facility,outcome)

    async def _received(self,row,raw):
        path=save_once(self._receipt_path(row),raw)
        value=decode(raw)
        if type(value) is not dict:fail('reference_invalid','invalid NATS acknowledgement')
        if 'error' in value:return self._confirm(row,self._negative(row,raw,path),'negative')
        if value.get('stream')!=self._stream(row['namespace']) or type(value.get('seq')) is not int or value['seq']<1:
            fail('reference_invalid','acknowledgement has no original stream sequence')
        msg=await self._get_original(row['namespace'],seq=value['seq'])
        return self._confirm(row,self._facility(row,msg),'positive')
