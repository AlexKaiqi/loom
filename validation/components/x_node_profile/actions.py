"""Pre-registered candidate actions and independent checks, not executor behavior."""
from pathlib import Path
import base64,copy,json,time
from artifacts import canonical,file_fact,read_ref,require,save,sha_bytes,strict_json,InvalidEvidence
from rpc import Rpc,ShortPeerBridge
from observer import NodeObserver

class Experiment:
    def __init__(self,fixture,argv,out):
        self.fx=fixture;self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.rpc=Rpc(argv,fixture,self.out/'rpc');self.observer=NodeObserver(self.out/'engine',fixture)
        self.binding={};self.api={};self.calls=[];self.checkpoints=[];self.write_offset=0;self.serial=0;self.bridge=None
    def args(self,**extra):
        return {'request':copy.deepcopy(self.fx.request),'authority':copy.deepcopy(self.fx.authority),
                'binding':copy.deepcopy(self.binding),'state_dir':str(self.fx.state),**copy.deepcopy(extra)}
    def call(self,method,**extra):
        args=self.args(**extra);self.serial+=1;value=self.rpc.call(method,args)
        save(self.out/f'operation-{self.serial:04d}.json',{'method':method,'args':args,'response':value})
        require('error'not in value,'candidate '+method+' rejected legitimate action: '+str(value.get('error')))
        self.api=value;self.binding=value.get('binding',self.binding);return value
    def execute(self,live=True):
        value=self.call('execute');require(bool(value.get('binding')),'actual binding absent from execute')
        observation=self.observer.binding(self.binding,live=live);save(self.out/'initial-physical.json',observation);return value
    def call_fields(self,method,call_id,offset=0):
        require(bool(self.binding),'original channel binding missing')
        return {'call_id':call_id,'execution_id':self.binding['execution_id'],
                'object_generation':self.binding['object_generation'],'channel_id':self.binding['channel_id'],
                'method':method,'request_digest':self.binding['request_digest'],'byte_offset':offset}
    def call_record(self,value,expected,data=None,state=None):
        ref=value.get('call_ref');require(isinstance(ref,dict),'original X call ref missing')
        fact,raw=read_ref({'path':ref['path'],'sha256':ref['sha256'],'bytes':ref['size']},2097152);record=strict_json(raw)
        for key in ['call_id','method','execution_id','object_generation','channel_id','request_digest','byte_offset']:
            require(record.get(key)==expected[key],'original X call association differs:'+key)
        require(record.get('state')in('ISSUED','CONFIRMED','UNKNOWN'),'original call state missing')
        if state:require(record['state']==state,'original call state differs')
        if data is not None:require(record.get('data_sha256')==sha_bytes(data)and record.get('data_bytes')==len(data),'original call bytes differ')
        self.calls.append({'expected':copy.deepcopy(expected),'ref':copy.deepcopy(ref),'record':record});return record
    def read(self,call_id=None,offset=0,max_bytes=1048576,transport=None):
        name=call_id or 'read-'+str(len(self.calls));fields=self.call_fields('channel_read',name,offset)
        args=self.args(**fields,stream='stdout',max_bytes=max_bytes)
        value=(transport or self.rpc).call('channel_read',args)
        require('error'not in value,'legitimate channel read rejected')
        raw=base64.b64decode(value['data_base64'],validate=True)
        require(value.get('stream')=='stdout'and value.get('byte_offset')==offset and value.get('next_byte_offset')==offset+len(raw),'original read range differs')
        self.call_record(value,fields,raw,'CONFIRMED');return raw,value
    def ready(self,kind='ready',seconds=5,predicate=None):
        deadline=time.monotonic()+seconds;attempt=0
        while time.monotonic()<deadline:
            raw,_=self.read('ready-'+str(len(self.calls)));attempt+=1
            for line in raw.splitlines():
                try:value=strict_json(line)
                except InvalidEvidence:continue
                if isinstance(value,dict)and value.get('kind')==kind and (predicate is None or predicate(value)):return value
            # Queries are bounded actual observation; no fixed sleep used as readiness proof.
        raise InvalidEvidence('actual stdout readiness missing:'+kind)
    def write(self,data,call_id=None,transport=None):
        name=call_id or 'write-'+str(len(self.calls));fields=self.call_fields('channel_write',name,self.write_offset)
        args=self.args(**fields,data_base64=base64.b64encode(data).decode())
        value=(transport or self.rpc).call('channel_write',args);require('error'not in value,'legitimate original write rejected')
        record=self.call_record(value,fields,data,'CONFIRMED');require(record.get('written_bytes')==len(data),'original complete write count differs')
        self.write_offset+=len(data);return value,fields,args
    def nonce(self,value,**kw):
        result=self.write(canonical({'nonce':value})+b'\n',**kw)
        self.ready('accepted',predicate=lambda event:event.get('nonce')==value)
        return result
    def freeze(self,name):
        value=self.call('checkpoint',checkpoint_id=name,purpose='checkpoint')
        checkpoint=self.observer.checkpoint(value,self.binding,name);self.checkpoints.append(checkpoint);return checkpoint
    def resume(self,checkpoint):
        before=copy.deepcopy(self.binding);self.call('resume',receipt=checkpoint['ref'])
        require(all(self.binding[k]==before[k]for k in ['container_id','exec_id','object_generation','channel_id']),'resume changed original execution object')
        self.observer.binding(self.binding,live=True)
    def seal(self,checkpoint):
        value=self.call('seal',receipt=checkpoint['ref']);observation=self.observer.stopped(self.binding)
        path=self.out/('actual-stopped-'+str(len(self.checkpoints))+'.json')
        if path.exists():path=self.out/('actual-stopped-'+str(len(self.checkpoints))+'-repeat-'+str(self.serial)+'.json')
        save(path,observation);return value
    def stream_original(self):
        value=self.call('query');ref=value['artifacts']['stdout'];return read_ref({'path':ref['path'],'sha256':ref['sha256'],'bytes':ref['size']},1048576)[1]
    def compare_channel(self,checkpoint,nonces):
        raw=checkpoint['files'].get('channel.jsonl');require(raw is not None and raw.endswith(b'\n'),'original channel JSONL missing/incomplete')
        entries=[strict_json(line)for line in raw.splitlines()]
        require([x.get('nonce')for x in entries]==nonces,'actual Node accepted duplicate/missing/out-of-order input')
        return entries
    def cleanup(self):
        failures=[]
        if self.bridge:
            try:self.bridge.stop()
            except Exception as exc:failures.append({'phase':'bridge','error':repr(exc)})
        try:self.rpc.stop()
        except Exception as exc:failures.append({'phase':'adapter','error':repr(exc)})
        bindings=[copy.deepcopy(self.binding)]
        # Original durable execution records also cover an accepted create whose reply was lost.
        for path in sorted(self.fx.state.glob('*/record.json')):
            try:
                record=strict_json(path.read_bytes())
                if record.get('request',{}).get('execution_id')in self.fx.execution_ids:bindings.append(record.get('binding',{}))
            except Exception as exc:failures.append({'phase':'read-original','path':str(path),'error':repr(exc)})
        facts=self.observer.cleanup_owned(bindings,self.fx.execution_ids)
        failures.extend(facts['failures'])
        process=self.rpc.p
        save(self.out/('cleanup.json'if not (self.out/'cleanup.json').exists()else 'cleanup-retry-'+str(time.time_ns())+'.json'),
             {'failed_original_objects':failures,'physical':facts,'adapter_pid':process.pid if process else None,'adapter_exit':process.returncode if process else None})
        require(not failures,'actual owned object cleanup incomplete:'+repr(failures))
