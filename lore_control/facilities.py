"""Immutable facility receipt and input associations. Their owners keep original bytes."""
import hashlib
from .values import ControlError,fail,encode,decode,same,fields,positive_int
from .responsibilities import DELIVERY_KINDS

class Facilities:
    def _receipt_expected(self,row):
        return dict(request_id=row['id'],namespace=row['namespace'],source=row['principal'],delivery_owner=DELIVERY_KINDS[row['kind']],request_digest=hashlib.sha256(encode(self._request_binding(row)).encode()).hexdigest())

    def _verify_receipt(self,row,ref):
        if type(ref) is not dict or ref.get('outcome') not in ('positive','negative') or (ref.get('outcome')=='negative' and ref.get('definite') is not True):fail('reference_invalid','only a definite original facility receipt can be confirmed')
        self._reference(ref,'receipt',self._receipt_expected(row))

    def _validate_retry(self,principal,request):
        retry=request['payload']['retry_of'];fields(retry,{'request_id','receipt_ref'},'retry association')
        if request['kind'] not in DELIVERY_KINDS:fail('invalid','retry association is only for a facility attempt')
        old=self.db.execute('SELECT * FROM requests WHERE id=?',(retry['request_id'],)).fetchone()
        if old is None or old['phase']!='confirmed' or old['principal']!=principal or old['namespace']!=request['namespace'] or old['kind']!=request['kind']:fail('reference_invalid','retry must refer to an accepted definite rejection')
        receipt=decode(old['receipt_ref_json'])
        if not same(receipt,retry['receipt_ref']) or receipt.get('outcome')!='negative' or receipt.get('definite') is not True:fail('reference_invalid','retry must retain original definite negative receipt')
        self._verify_receipt(old,receipt)

    def mark_dispatched(self,principal,id,delivery_owner):
        with self._tx():
            row=self._get_request(id);self._authorize(principal,row['namespace'],{'runtime'})
            if row['kind'] not in DELIVERY_KINDS or DELIVERY_KINDS[row['kind']]!=delivery_owner:fail('invalid','facility owner does not match accepted kind')
            fresh=row['phase']=='accepted_delivery'
            if fresh:self.db.execute("UPDATE requests SET phase='issued',delivery_owner=? WHERE id=?",(delivery_owner,id))
            return self._request_value(self._get_request(id))|{'fresh':fresh,'mode':'execute' if fresh else 'reconcile'}

    def confirm_delivery(self,principal,id,receipt_ref):
        with self._tx():
            row=self._get_request(id);self._authorize(principal,row['namespace'],{'runtime'})
            if row['kind'] not in DELIVERY_KINDS:fail('invalid','ordinary responsibility needs its original decision')
            if row['receipt_ref_json'] is not None:
                if not same(decode(row['receipt_ref_json']),receipt_ref):fail('conflict','confirmed original receipt cannot change')
                self._verify_receipt(row,receipt_ref);return self._request_value(row)
            if row['phase']!='issued':fail('invalid','facility invocation was not dispatched')
            self._verify_receipt(row,receipt_ref)
            self.db.execute("UPDATE requests SET phase='confirmed',receipt_ref_json=? WHERE id=?",(encode(receipt_ref),id))
            return self._request_value(self._get_request(id))

    def _validate_selector(self,principal,namespace,selector):
        fields(selector,{'namespace','source','start_sequence','filters','page_size','surface_ref','previous_session_ref','execution_targets'},'input selector')
        if selector['namespace']!=namespace or selector['source']!=principal:fail('denied','input selector cannot change trusted source or namespace')
        positive_int(selector['start_sequence']);positive_int(selector['page_size'])
        if type(selector['filters']) is not dict or type(selector['execution_targets']) is not list or type(selector['surface_ref']) is not dict:fail('invalid','invalid input selector structure')
        encode(selector)

    def _input_association(self,row):
        payload=decode(row['payload_json'])
        if row['kind']!='invocation' or 'input_binding' not in payload:fail('invalid','request did not declare an input binding')
        return payload['input_binding']

    def _verify_input(self,id,binding,ref):
        if type(ref) is not dict or ref.get('owner')!='E' or ref.get('kind')!='input' or ref.get('id')!=id:fail('reference_invalid','input reference owner or identity mismatch')
        self._reference(ref,'input',{'invocation_id':id,'binding':binding})

    def _input_ready(self,row):
        if row['kind']!='invocation' or 'input_binding' not in decode(row['payload_json']):return True
        item=self.db.execute('SELECT * FROM inputs WHERE invocation_id=?',(row['id'],)).fetchone()
        if item is None:return False
        try:self._verify_input(row['id'],self._input_association(row),decode(item['input_ref_json']))
        except ControlError as exc:
            if exc.code=='reference_invalid':return False
            raise
        return True

    def bind_input(self,principal,invocation_id,binding,input_ref):
        encode(binding);encode(input_ref)
        with self._tx():
            row=self._get_request(invocation_id);self._authorize(principal,row['namespace'],{'runtime'})
            original=self._input_association(row)
            if not same(original,binding):fail('conflict','accepted original input selector cannot change')
            prior=self.db.execute('SELECT * FROM inputs WHERE invocation_id=?',(invocation_id,)).fetchone()
            if prior and not same(decode(prior['input_ref_json']),input_ref):fail('conflict','original input reference cannot change')
            self._verify_input(invocation_id,binding,input_ref)
            if prior is None:self.db.execute('INSERT INTO inputs VALUES(?,?,?)',(invocation_id,encode(binding),encode(input_ref)))
            return {'invocation_id':invocation_id,'binding':decode(encode(binding)),'input_ref':decode(encode(input_ref))}

    def query_input(self,principal,invocation_id):
        with self._tx(False):
            row=self._get_request(invocation_id);self._authorize(principal,row['namespace'])
            if principal!=row['principal'] and not set(self.authority[principal].get('roles',[]))&{'runtime','admin'}:fail('denied','input belongs to a different accepted principal')
            binding=self._input_association(row)
            prior=self.db.execute('SELECT * FROM inputs WHERE invocation_id=?',(invocation_id,)).fetchone()
            if prior is None:return None
            ref=decode(prior['input_ref_json']);self._verify_input(invocation_id,binding,ref)
            return {'invocation_id':invocation_id,'binding':binding,'input_ref':ref}
