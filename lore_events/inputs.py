"""One fixed source selection and immutable original input reference in R."""
from pathlib import Path
from .values import encode,decode,same,fail,EventError,identifier,positive
from .input_files import packet,publish,validate

class Inputs:
    def _input_original(self,context,id):
        identifier(id);row=self.control.query(self.runtime,id);self._authorize(context,row['namespace'])
        if row['kind']!='invocation' or 'input_binding' not in row['payload']:fail('invalid','invocation has no original input selector')
        return row,row['payload']['input_binding']

    def _bound_input(self,id):
        try:return self.control.query_input(self.runtime,id)
        except Exception as exc:
            if getattr(exc,'code',None)=='reference_invalid':fail('input_invalid','original confirmed input failed authority validation')
            raise

    async def _verify_input(self,item):
        binding=item['binding'];ref=item['input_ref'];files,meta=validate(ref,binding,self.profile['input_root'])
        originals=[];previous=0
        try:
            for event_ref in meta['event_refs']:
                msg=await self._get_original(binding['namespace'],seq=event_ref['sequence'])
                obj=self._message(msg,binding['namespace']);row=self.control.query(self.runtime,obj['request_id'])
                if not same(self._facility(row,msg),event_ref):fail('input_invalid','original input event reference differs')
                if msg.seq<=previous or not meta['range']['start_sequence']<=msg.seq<=meta['range']['end_sequence']:fail('input_invalid','input event order/range differs')
                previous=msg.seq;originals.append(msg.data+b'\n')
            if b''.join(originals)!=files['events.jsonl']:fail('input_invalid','input event bytes differ from original sequence references')
        except Exception as exc:
            if isinstance(exc,EventError) and exc.code=='input_invalid':raise
            fail('input_invalid','original input event reference unavailable: '+str(exc))
        return ref

    async def lookup_input(self,context,invocation_id):
        row,binding=self._input_original(context,invocation_id)
        if context!=binding['source'] and not self._is_runtime(context):fail('denied','input belongs to another original source')
        item=self._bound_input(invocation_id)
        if item is None:fail('input_invalid','input has not been completely published and bound')
        return await self._verify_input(item)

    async def prepare_input(self,context,invocation_id,namespace,start_sequence,filters,target_dir,*,input_context):
        self._authorize(context,namespace);positive(start_sequence,'start_sequence');filters=self._filters(filters,namespace)
        if type(input_context) is not dict or set(input_context)!={'surface_ref','previous_session_ref','execution_targets'}:fail('invalid','complete fixed input context required')
        binding={'namespace':namespace,'source':context,'start_sequence':start_sequence,'filters':filters,'page_size':self.profile['page_size'],**decode(encode(input_context))}
        row,original=self._input_original(context,invocation_id)
        if not same(original,binding):fail('conflict','original complete input selection cannot change')
        item=self._bound_input(invocation_id)
        if item is not None:return await self._verify_input(item)
        root=Path(target_dir)
        if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(self.profile['input_root']).resolve()):fail('invalid','input publication outside configured root')
        records,span,filters=await self._scan(context,namespace,start_sequence,filters,checkpoint=True)
        refs=[self._facility(self.control.query(self.runtime,obj['request_id']),msg) for msg,obj in records]
        ref=publish(root.resolve(),invocation_id,packet(invocation_id,binding,span,records,refs))
        try:self.control.bind_input(self.runtime,invocation_id,binding,ref)
        except Exception as exc:
            if getattr(exc,'code',None)=='reference_invalid':fail('input_invalid','published input failed original authority validation')
            raise
        return await self._verify_input({'binding':binding,'input_ref':ref})
