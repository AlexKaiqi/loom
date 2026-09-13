"""A single fresh R dispatch permit, then reconciliation by original NATS identity."""
import nats.errors
from .values import encode,decode,sha,same,fail,identifier,envelope
from .persistence import read_file

class Publication:
    def _event_row(self,context,id):
        identifier(id)
        row=self.control.query(self.runtime,id);self._authorize(context,row['namespace'])
        if context!=row['principal'] and not self._is_runtime(context):fail('denied','event belongs to another original source')
        if row['kind']!='event':fail('invalid','original request is not an event')
        return row

    async def submit(self,context,request_id,namespace,name,payload):
        self._authorize(context,namespace,submit=True)
        if type(payload) is dict and set(payload)&{'origin','principal','system'}:fail('invalid','application payload cannot impersonate control source')
        return await self._submit(context,request_id,namespace,name,payload,'application')

    async def emit_observation(self,context,request_id,namespace,observation_ref):
        self._authorize(context,namespace,runtime=True)
        required={'owner','kind','id','namespace','resource_id','revision','sha256'}
        if type(observation_ref) is not dict or set(observation_ref)!=required or observation_ref.get('owner')!='R' or observation_ref.get('kind')!='registration':
            fail('reference_invalid','unsupported or incomplete original observation reference')
        checker=self.control.reference_checker
        expected={'namespace':namespace,'source':context,'event_name':'surface.registered'}
        if not callable(checker):fail('reference_invalid','original observation authority missing')
        try:valid=checker(decode(encode(observation_ref)),'observation',expected)
        except Exception as exc:fail('reference_invalid','original observation authority unavailable: '+str(exc))
        if valid is not True:fail('reference_invalid','original observation source or binding rejected')
        return await self._submit(context,request_id,namespace,'surface.registered',{'observation_ref':observation_ref},'runtime')

    async def _submit(self,context,id,namespace,name,payload,origin):
        identifier(id)
        if type(name) is not str or not name:fail('invalid','event name must be nonempty string')
        raw=encode(envelope(context,id,namespace,name,payload,origin))
        if len(raw)>self.profile['message_limit_bytes']:fail('invalid','complete event exceeds configured bytes')
        request={'id':id,'namespace':namespace,'kind':'event','payload':{'subject':self._subject(namespace,id),'event_sha256':sha(raw),'event_bytes':len(raw)}}
        self.control.accept(context,request)
        row=self.control.mark_dispatched(self.runtime,id,'E')
        if not row['fresh']:return await self.query(context,id)
        await self._checkpoint('after_dispatch_before_publish',{'request_id':id,'namespace':namespace})
        try:
            reply=await self.nc.request(request['payload']['subject'],raw,timeout=2,headers={'Nats-Msg-Id':id})
        except (nats.errors.Error,OSError):return self._unknown(row)
        return await self._received(row,reply.data)

    def _unknown(self,row):
        return {'status':'UNKNOWN','request_id':row['id'],'namespace':row['namespace'],'source':row['principal'],'subject':row['payload']['subject']}

    async def query(self,context,request_id):
        row=self._event_row(context,request_id)
        if row['receipt_ref'] is not None:return await self._confirmed(row)
        if row['phase']=='accepted_delivery':return {'status':'ACCEPTED','request_id':request_id}
        path=self._receipt_path(row)
        if path.exists():return await self._received(row,read_file(path))
        try:msg=await self.js.get_msg(self._stream(row['namespace']),subject=row['payload']['subject'])
        except (nats.errors.Error,OSError):return self._unknown(row)
        return self._confirm(row,self._facility(row,msg),'positive')
