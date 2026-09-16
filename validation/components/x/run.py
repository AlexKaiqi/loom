"""Pre-registered real X driver. A missing target is a failure, never a fixture success."""
from pathlib import Path
import argparse,base64,copy,hashlib,itertools,json,os,selectors,signal,socket,subprocess,sys,time
from fixtures import create,script_bytes
import restore_actions
from collector import Collector,ENV
from oracle import assess,EvidenceError
from runtime_observations import await_source_start,await_fixture_stdio
from peer_fixture import LivePeer
ROOT=Path(__file__).resolve().parents[3]
class Missing(Exception):pass
class Adapter:
 def __init__(self,argv,fx,out):self.argv=argv;self.fx=fx;self.out=out;self.n=0;self.p=None;self.start()
 def start(self):
  self.control_fd=os.open(self.fx['root']/'control'/'control-canary',os.O_RDONLY);self.control_peer,self.control_child=socket.socketpair();self.control_peer.setblocking(False);self.fx['control_peer']=self.control_peer
  self.p=subprocess.Popen(self.argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,close_fds=True,pass_fds=(self.control_fd,self.control_child.fileno()),env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(self.fx['root']),'LORE_X_STATE_DIR':str(self.fx['state']),'LORE_X_CACHE_DIR':str(self.fx['cache']),'LORE_TEST_CONTROL_CANARY':self.fx['canary'].decode(),'PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1'});self.record_start();self.sel=selectors.DefaultSelector();self.sel.register(self.p.stdout,selectors.EVENT_READ,'stdout');self.sel.register(self.p.stderr,selectors.EVENT_READ,'stderr');self.buf=b''
  try:await_source_start(self.p,self.argv,ROOT,self.out)
  except Exception:self.stop();raise
 def record_start(self):
  with (self.out/'adapter-processes.jsonl').open('a') as f:f.write(json.dumps({'pid':self.p.pid,'argv':self.argv,'cwd':os.getcwd(),'pythonpath':str(ROOT)})+'\n');f.flush();os.fsync(f.fileno())
 def stop(self):
  if self.p and self.p.poll() is None:os.killpg(self.p.pid,signal.SIGKILL);self.p.wait(timeout=3)
  if hasattr(self,'sel'):self.sel.close()
  if self.p:
   for stream in (self.p.stdin,self.p.stdout,self.p.stderr):
    if stream is not None:stream.close()
  if getattr(self,'control_fd',None) is not None:os.close(self.control_fd);self.control_fd=None
  for n in ['control_peer','control_child']:
   sock=getattr(self,n,None)
   if sock is not None:sock.close();setattr(self,n,None)
 def call(self,method,args,barrier=None,timeout=10):
  self.n+=1;rid='r'+str(self.n);request={'request_id':rid,'method':method,'arguments':args};prefix=self.out/f'control-{self.n:04d}';prefix.with_suffix('.request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n');self.p.stdin.write(json.dumps(request).encode()+b'\n');self.p.stdin.flush();end=time.monotonic()+min(10,timeout);stderr=bytearray();raw=bytearray()
  try:
   while time.monotonic()<end:
    while b'\n' in self.buf:
     line,self.buf=self.buf.split(b'\n',1);obj=json.loads(line)
     if barrier and obj.get('test_barrier')==barrier:return obj
     if obj.get('request_id')==rid:return obj
     raise EvidenceError('unexpected control response')
    for key,_ in self.sel.select(.02):
     by=os.read(key.fileobj.fileno(),65536)
     if not by:
      self.sel.unregister(key.fileobj)
      if key.data=='stdout' and b'\n' not in self.buf:raise EvidenceError('adapter exited before correlated response')
      continue
     if key.data=='stdout':self.buf+=by;raw+=by
     else:stderr+=by
     if len(raw)+len(stderr)>262144:raise EvidenceError('control channel cap')
   raise EvidenceError('adapter response timeout')
  finally:prefix.with_suffix('.stdout').write_bytes(raw);prefix.with_suffix('.stderr').write_bytes(stderr)

def variants(case):
 p=case['initial']['parameters'];groups=case['parameter_rules']['zip_groups'];used=set();dimensions=[]
 for group in groups:
  sizes={len(p[k]) for k in group}
  if len(sizes)!=1:raise EvidenceError('mismatched zipped parameters')
  dimensions.append([dict(zip(group,x)) for x in zip(*(p[k] for k in group))]);used.update(group)
 for k,v in p.items():
  if k in used:continue
  if k=='repetitions':dimensions.append([{'repeat_index':i} for i in range(v)])
  else:dimensions.append([{k:x} for x in (v if isinstance(v,list) else [v])])
 for combo in itertools.product(*dimensions):
  d={}
  for x in combo:d.update(x)
  d.setdefault('domain','task');yield d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--component-json');ap.add_argument('--case');ap.add_argument('--variant');a=ap.parse_args()
 if not a.batch.replace('-','').isalnum():raise SystemExit('invalid new batch name')
 out=Path(__file__).parent/'evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
 suite=json.loads((ROOT/'design/g3/x/cases.json').read_text());selected=[x for x in suite['cases'] if not a.case or x['id']==a.case]
 result={'type':'FORMAL_COMPONENT_RUN' if not a.case else 'PARTIAL_COMPONENT_DIAGNOSTIC','case_suite_sha256':hashlib.sha256((ROOT/'design/g3/x/cases.json').read_bytes()).hexdigest(),'rows':[],'target':a.component_json,'variant':a.variant,'status':'INCOMPLETE'}
 def save(): (out/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 if not selected:result['status']='MISSING_CASE';save();return 4
 if not a.component_json:result['status']='MISSING_COMPONENT';save();return 4
 argv=json.loads(a.component_json)
 if not isinstance(argv,list) or not argv or not all(isinstance(x,str) for x in argv):raise SystemExit('component must be an explicit argv JSON array')
 if not Path(argv[0]).is_absolute() or not Path(argv[0]).exists():result['status']='MISSING_COMPONENT';save();return 4
 for case in selected:
  for index,params in enumerate(variants(case)):
   dest=out/(case['id']+'-'+str(index));dest.mkdir();row={'case_id':case['id'],'parameters':params,'status':'INCOMPLETE'};result['rows'].append(row);fx=None;adapter=None;observer=None;peer=None;network=None;binding={};api={};frames={};handoff=None;live_peer=None;deadline=time.monotonic()+120
   try:
    fx=create(dest/'fixture',case,params)
    if 'F_handoff_adapter' in case['dependencies']:
     try:
      from f_handoff import Handoff
      handoff=Handoff(fx,dest)
     except (FileNotFoundError,ImportError,ValueError) as exc:raise Missing('verified actual F source dependency: '+str(exc)) from exc
    observer=Collector(dest,fx);adapter=Adapter(argv,fx,dest)
    for step in case['actions']:
     if time.monotonic()>deadline:raise EvidenceError('whole case deadline')
     op=step['op'];arg=step['args']
     if op in ('invoke','fault_invoke'):
      method=arg['method'];extra=copy.deepcopy(arg.get('arguments',{}));req=copy.deepcopy(fx['request']);req.update(extra.pop('request_overrides',{}))
      from lore_execution.requests import PROFILES as _REG
      for _k,_v in list(req.items()):
       if isinstance(_v,str) and _v.startswith('@profile_sha256:'):req[_k]=_REG[_v.split(':',1)[1]]['profile_sha256']
      fx['request']=req
      if method=='execute_conflicting':
       method='execute';field=params['conflict_field'];field={'script':'script_base64','stdin':'stdin_base64'}.get(field,field)
       val=req.get(field)
       if field in ('script_base64','stdin_base64'):val=base64.b64encode(base64.b64decode(val)+b'\n# different bytes').decode()
       req[field]=({**val,'conflict':True} if isinstance(val,dict) else (val+'-conflict' if isinstance(val,str) else 'conflict'))
       if field in ('script_base64','stdin_base64'):req[field]=val
      callargs={'request':req,'authority':fx['authority'],'binding':binding,'state_dir':str(fx['state']),**extra,'test_context':{'cache_dir':str(fx['cache']),'variant':a.variant,'requested_barrier':arg.get('barrier')}}
      if method=='restore':callargs.update({'source_ref':fx['restore_source'],'object_generation':req['object_generation']})
      if method=='validate_handoff':
       if handoff is None:raise Missing('external actual F handoff')
       api=handoff.validate(frames,observer)
      else:api=adapter.call(method,callargs,arg.get('barrier'))
      binding=api.get('binding') or binding
      if op=='fault_invoke':
       frames['fault-'+arg['barrier']]=observer.capture(api,binding,'fault-'+arg['barrier']);adapter.stop();row.setdefault('faults',[]).append({'barrier':arg['barrier'],'actual_killed_pid':adapter.p.pid,'returncode':adapter.p.returncode})
     elif op=='collect':
      # A fresh query is NOT substituted for the response being checked.
      frames[arg['tag']]=observer.capture(api,binding,arg['tag'],arg.get('sample_resources_seconds',0))
      if handoff is not None and arg['tag']=='prepared':handoff.prepared(frames['prepared'])
     elif op=='await_stdio':
      record=await_fixture_stdio(adapter,observer,fx,binding,arg,frames,deadline);frames[arg['tag']]=record;(dest/(arg['tag']+'.json')).write_text(json.dumps(record,indent=2)+'\n')
     elif op=='retain_checkpoint':restore_actions.retain(fx,frames,arg['from_tag'],dest)
     elif op=='cold_restore_boundary':frames['cold_boundary']=restore_actions.cold_boundary(fx,adapter,dest)
     elif op=='fault_restore_source':adapter.stop();restore_actions.fault_source(fx,dest);restore_actions.clear_cache(fx);adapter.start()
     elif op=='prepare_restore_request':restore_actions.prepare_request(fx);binding={}
     elif op=='query_saved_execution':frames[arg['tag']]=restore_actions.query_saved(fx,adapter,observer,dest,arg['tag'])
     elif op=='restart':adapter.stop();adapter.start()
     elif op=='delay':time.sleep(min(float(arg['seconds']),.5))
     elif op=='replace_target':
      fx['target'].rename(fx['root']/'retired');fx['target'].mkdir();(fx['target']/'canary').write_bytes(b'unchanged')
     elif op=='host_edit':(fx['target']/'human-edit').write_bytes(b'actual-human-edit');fx['human_edit']=True
     elif op=='replace_input':(fx['target']/'untracked-dependency').unlink();(fx['target']/'input-a').write_bytes(b'changed')
     elif op=='prepare_peer':live_peer=LivePeer(observer,fx,dest);live_peer.prepare()
     elif op=='start_peer':
      if live_peer is None:raise EvidenceError('peer network/request not frozen before execute')
      live_peer.start(binding)
     elif op=='observe_peer_completion':
      if live_peer is None:raise EvidenceError('live peer missing')
      frames[arg['tag']]=live_peer.completion(binding)
     elif op=='stop_peer':
      if live_peer is None:raise EvidenceError('live peer missing')
      live_peer.stop()
     else:raise EvidenceError('unimplemented driver action '+op)
    row['assessment']=assess(case['expected'],frames,fx['values'],params);row['status']='PASS' if row['assessment']['pass'] else 'FAIL'
   except Missing as e:row['status']='MISSING_DEPENDENCY';row['error']=str(e)
   except Exception as e:row['status']='FAIL';row['error']=repr(e)+(' missing='+str(e.filename) if getattr(e,'filename',None) else '')
   finally:
    if adapter:adapter.stop()
    if observer:
     # Never delete an unrelated concurrent object: cleanup requires the exact
     # fixture execution label in actual inspect, even when the case failed.
     try:
      ids=set(observer.ids('container'))-set(observer.baseline_containers)
      for cid in ids:
       st=observer.inspect(cid)
       if st and st['Config'].get('Labels',{}).get('lore.x.execution_id')in fx['execution_ids']:observer.run(['docker','rm','-f',cid],check=False)
      if peer:observer.run(['docker','rm','-f',peer],check=False)
      if live_peer:live_peer.cleanup()
      vols=set(observer.ids('volume'))-set(observer.baseline_volumes)
      for vol in vols:
       actual=json.loads(observer.run(['docker','volume','inspect',vol])[1])[0]
       if (actual.get('Labels') or {}).get('lore.x.execution_id')in fx['execution_ids']:observer.run(['docker','volume','rm',vol],check=False)
      if network:observer.run(['docker','network','rm',network],check=False)
     except Exception as e:row['cleanup_error']=repr(e);row['status']='FAIL'
    save()
 result['status']='PASS' if result['rows'] and all(x['status']=='PASS' for x in result['rows']) else 'FAIL';save();print(json.dumps({'status':result['status'],'cases':len(result['rows'])}));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
