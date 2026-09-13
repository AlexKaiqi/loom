"""Read original sequence ranges before filtering; no consumers or wait processes."""
import nats.js.errors
from .values import encode,decode,sha,fail,identifier,positive

class History:
    def _filters(self,filters,namespace):
        if type(filters) is not dict or set(filters)-{'names','sources'}:fail('invalid','unknown event filter')
        for key,values in filters.items():
            if type(values) is not list or any(type(v) is not str for v in values):fail('invalid','filters must be string lists')
            if key=='sources' and any(namespace not in self.profile['authority'].get(source,{}).get('namespaces',[]) for source in values):fail('denied','event source not authorized in namespace')
        return decode(encode(filters))

    def _message(self,msg,namespace):
        if type(msg.data) is not bytes:fail('reference_invalid','original event bytes missing')
        obj=decode(msg.data)
        required={'schema_version','origin','source','namespace','request_id','name','payload'}
        if type(obj) is not dict or set(obj)!=required or obj['schema_version']!=1 or obj['origin'] not in ('application','runtime'):
            fail('reference_invalid','invalid original event envelope')
        identifier(obj['request_id'])
        if obj['namespace']!=namespace or type(obj['source']) is not str or type(obj['name']) is not str or not obj['name']:
            fail('reference_invalid','original event namespace/source/name invalid')
        if msg.data!=encode(obj) or msg.subject!=self._subject(namespace,obj['request_id']) or (msg.headers or {}).get('Nats-Msg-Id')!=obj['request_id']:
            fail('reference_invalid','original event canonical bytes/header/subject invalid')
        original=self.control.query(self.runtime,obj['request_id'])
        if original['kind']!='event' or original['principal']!=obj['source'] or original['namespace']!=namespace:
            fail('reference_invalid','event does not match original accepted source')
        expected={'subject':msg.subject,'event_sha256':sha(msg.data),'event_bytes':len(msg.data)}
        if any(original['payload'].get(k)!=v for k,v in expected.items()):fail('reference_invalid','event differs from original R accepted binding')
        return obj

    async def _get_original(self,namespace,seq=None,subject=None):
        try:return await self.js.get_msg(self._stream(namespace),seq=seq,subject=subject)
        except nats.js.errors.NotFoundError:fail('history_missing','original promised event sequence is missing')

    async def _scan(self,context,namespace,start_sequence,filters,checkpoint=False):
        self._authorize(context,namespace);positive(start_sequence,'start_sequence');filters=self._filters(filters,namespace)
        info=await self.js.stream_info(self._stream(namespace));high=info.state.last_seq
        if start_sequence>high+1:fail('invalid','start exceeds original high water plus one')
        end=min(high,start_sequence+self.profile['page_size']-1)
        if checkpoint:await self._checkpoint('after_input_highwater_before_scan',{'high_water':high})
        records=[]
        for seq in range(start_sequence,end+1):
            msg=await self._get_original(namespace,seq=seq);obj=self._message(msg,namespace)
            if msg.seq!=seq:fail('history_missing','source sequence changed during scan')
            selected=('names' not in filters or obj['name'] in filters['names']) and ('sources' not in filters or obj['source'] in filters['sources'])
            if selected:records.append((msg,obj))
        span={'start_sequence':start_sequence,'end_sequence':end,'high_water':high,'next_sequence':end+1 if end>=start_sequence else start_sequence}
        return records,span,filters

    async def scan(self,context,namespace,start_sequence,filters):
        records,span,filters=await self._scan(context,namespace,start_sequence,filters)
        return {'events':[value for msg,value in records],'range':span,'filters':filters}
