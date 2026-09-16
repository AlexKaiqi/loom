"""Two actual Linux processes/ControlStores compete for one scope attempt."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def worker(out,index):
 sys.path.insert(0,str(ROOT));from lore_control import ControlStore
 from lore_runtime.provider_owner import ProviderOwner
 from lore_session.provider import ProviderBridge
 from lore_provider.request import SHELL
 from lore_runtime.session_plan_files import compact
 def audit(event,args):
  if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('race is noHTTP')
 sys.addaudithook(audit)
 c=ControlStore(out/'R.sqlite',{'runtime':{'namespaces':['n'],'roles':['runtime','submit','admin']}},reference_checker=lambda ref,purpose,expected:purpose=='harness')
 budget=dict(max_requests=1,max_input_tokens=1024,max_output_tokens_per_request=32,max_request_body_bytes=1024,max_seconds=15,reasoning_effort='medium')
 owner=ProviderOwner(c,out/'provider',dict(scheme='http',host='127.0.0.1',port=1),principal='runtime',budget=budget,timeout=2)
 scope=dict(session_id='race',operation_id='race-parent',response_entry_id='response-'+index,session_scope=dict(namespace='n',surface_id='surface',session_id='race',session_generation=1),harness_ref=compact({'owner':'F','sha256':'a'*64}),capability_ref=compact({'owner':'F','sha256':'b'*64}),input_ref=dict(id='input',sha256='c'*64),source_result_ref=None)
 raw=json.dumps([scope['session_scope'],scope['operation_id'],scope['response_entry_id']],sort_keys=True,separators=(',',':')).encode();frame=dict(type='provider.request',session_id='race',operation_id='race-parent',response_entry_id=scope['response_entry_id'],effect_id='s-provider-'+sha(raw),payload=dict(systemPrompt='race fixture',messages=[dict(role='user',content='text')],tools=[SHELL]))
 original=owner._admit
 def cut(*args):
  original(*args);(out/('ready-'+index)).write_text(str(os.getpid()));deadline=time.monotonic()+.5
  while len(list(out.glob('ready-*')))<2 and time.monotonic()<deadline:time.sleep(.01)
 owner._admit=cut
 def noHTTP(*args):raise RuntimeError('actual R dispatch reached; noHTTP fixture cut')
 ProviderBridge.complete=noHTTP
 (out/('started-'+index)).write_text(str(os.getpid()))
 while not (out/'GO').exists():time.sleep(.01)
 try:owner.complete(scope,frame);error='unexpected completion'
 except Exception as ex:error=getattr(ex,'code',type(ex).__name__)
 finally:c.close()
 save(out/('process-'+index+'.json'),dict(pid=os.getpid(),effect_id=frame['effect_id'],outcome=error));return 0

def main():
 p=argparse.ArgumentParser();p.add_argument('--batch');p.add_argument('--worker',type=Path);p.add_argument('--index');a=p.parse_args()
 if a.worker:return worker(a.worker,a.index)
 sys.path.insert(0,str(ROOT));from lore_control import ControlStore
 out=ROOT/'validation/runtime-provider-race-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';files=[Path(__file__),ROOT/'lore_runtime/provider_owner.py',ROOT/'lore_runtime/session_plan_files.py',ROOT/'lore_execution/profile.json']
 for folder in ['lore_control','lore_session','lore_provider','lore_files','lore_execution']:files.extend(sorted((ROOT/folder).glob('*.py')))
 refs=[]
 for source in files:
  dest=workspace/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);refs.append(dict(original=str(source),copy=str(dest),sha256=sha(source.read_bytes())))
 save(out/'sources.json',refs);actual=out/'actual';actual.mkdir();c=ControlStore(actual/'R.sqlite',{'runtime':{'namespaces':['n'],'roles':['runtime','submit','admin']}},reference_checker=lambda ref,purpose,expected:purpose=='harness')
 c.accept('runtime',dict(id='race-parent',namespace='n',kind='invocation',payload=dict(harness_ref={'owner':'F','sha256':'a'*64},capability_ref={'owner':'F','sha256':'b'*64},source_result_ref=None)));c.claim('worker',time.monotonic());c.close()
 processes=[]
 for index in ['A','B']:
  argv=[sys.executable,'-B',str(workspace/Path(__file__).relative_to(ROOT)),'--worker',str(actual),'--index',index];processes.append((index,subprocess.Popen(argv,cwd=workspace,env=dict(PATH='/usr/bin:/bin:/usr/sbin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1'),stdout=subprocess.PIPE,stderr=subprocess.PIPE)))
 deadline=time.monotonic()+5
 while len(list(actual.glob('started-*')))<2 and time.monotonic()<deadline:time.sleep(.01)
 (actual/'GO').write_text('start both actual processes')
 for index,proc in processes:
  stdout,stderr=proc.communicate(timeout=10);(out/(index+'.stdout')).write_bytes(stdout);(out/(index+'.stderr')).write_bytes(stderr)
 c=ControlStore(actual/'R.sqlite',{'runtime':{'namespaces':['n'],'roles':['runtime','submit','admin']}},reference_checker=lambda ref,purpose,expected:False);rows=[dict(v) for v in c.db.execute("SELECT id,phase,payload_json FROM requests WHERE kind='provider_transport'")];(actual/'R.sql').write_text('\n'.join(c.db.iterdump()));c.close()
 unchanged=all(sha(Path(v['original']).read_bytes())==v['sha256']==sha(Path(v['copy']).read_bytes()) for v in refs);facts=[json.loads((actual/('process-'+i+'.json')).read_bytes()) for i,_ in processes]
 result=dict(status='PASS' if len(rows)==1 and unchanged and all(p.returncode==0 for _,p in processes) else 'FAIL',accepted_count=len(rows),limit=1,processes=facts,ready_cuts=len(list(actual.glob('ready-*'))),original_R_rows=rows,source_unchanged=unchanged,HTTP=0,Docker=0,source_manifest_sha256=sha((out/'sources.json').read_bytes()))
 save(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='original_R_rows'}));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
