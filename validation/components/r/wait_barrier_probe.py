"""New independent R wait-barrier trajectories, frozen before repair."""
from pathlib import Path
import hashlib,json,os,sqlite3,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source'));sys.path.insert(0,str(ROOT/'fixture'))
from lore_control import ControlStore
from input_fixture import make_input,check_input_ref
canonical=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
sha=lambda b:hashlib.sha256(b).hexdigest()
class Fixture:
 def __init__(self,path,create=True):
  self.root=Path(path);self.audit=[];self.db=self.root/'control.sqlite';self.refroot=self.root/'originals'
  if create:
   self.root.mkdir(parents=True,exist_ok=False);self.refroot.mkdir();self.refs={};self.authority={'admin':{'namespaces':['n1'],'roles':['admin','submit','runtime']},'alice':{'namespaces':['n1'],'roles':['submit']}}
   self.add('h1','harness','F');self.add('result','tool_result','X');self.add('condition','code','F')
   self.store=ControlStore(self.db,authority=self.authority,reference_checker=self.checker)
   for resource,kind in [('s1','surface'),('w1','workspace'),('secret','workspace')]:
    path=self.root/resource;path.mkdir();grants={'admin':['read','write']}
    if resource!='secret':grants['alice']=['read','write']
    self.store.register('admin','reg-'+resource,resource,'n1',kind,str(path),self.refs['h1'],grants)
    base=self.add(resource+'-base','file_version','F',{'resource_id':resource});self.add(resource+'-next','file_version','F',{'resource_id':resource});context={'resource_id':resource,'execution_id':'exec-'+resource,'base_ref':base}
    self.add(resource+'-stop','stopped','X',context);self.add(resource+'-published','file_version','F',context)
   self.save_meta()
  else:
   meta=json.loads((self.root/'fixture.json').read_text());self.refs=meta['refs'];self.authority=meta['authority'];self.store=ControlStore(self.db,authority=self.authority,reference_checker=self.checker)
 def add(self,id,kind,owner,context=None):
  record={'reference':{'id':id,'kind':kind,'owner':owner},'context':context or {},'original_content':'original '+id+' 雪'};b=canonical(record);(self.refroot/(id+'.json')).write_bytes(b);ref=record['reference']|{'sha256':sha(b)};self.refs[id]=ref;return ref
 def save_meta(self):(self.root/'fixture.json').write_text(json.dumps({'refs':self.refs,'authority':self.authority},ensure_ascii=False,indent=2)+'\n')
 def checker(self,ref,purpose,expected=None):
  if purpose=='input':valid=check_input_ref(ref,expected,self.root)
  else:
   valid=False
   if isinstance(ref,dict):
    path=self.refroot/(str(ref.get('id'))+'.json')
    if path.is_file():
     b=path.read_bytes();record=json.loads(b);valid=ref==record['reference']|{'sha256':sha(b)}
     kinds={'base':{'file_version'},'stopped':{'stopped'},'published':{'file_version'},'result':{'tool_result','answer'},'harness':{'harness'},'condition':{'code'}}
     valid=valid and (purpose not in kinds or ref['kind'] in kinds[purpose])
     if valid and expected is not None:valid=all(canonical(record['context'].get(k))==canonical(v) for k,v in expected.items())
  self.audit.append({'id':ref.get('id') if isinstance(ref,dict) else None,'purpose':purpose,'expected':expected,'valid':valid});return valid
 def acquire(self,resource='s1',new=False):return self.store.acquire(resource,'new-'+resource if new else 'exec-'+resource,self.refs[resource+'-next' if new else resource+'-base'])
 def release(self,resource='s1'):return self.store.release(resource,'exec-'+resource,self.refs[resource+'-stop'],self.refs[resource+'-published'])
 def ready(self,two=False):
  payload={'resource_id':'s1','resource_revision':1,'harness_ref':self.refs['h1'],'input_ref':None,'source_ref':None}
  if two:
   binding={'namespace':'n1','source':'alice','start_sequence':1,'filters':{},'page_size':16,'surface_ref':{'resource_id':'s1','revision':1,'version_ref':self.refs['s1-base']},'previous_session_ref':None,'execution_targets':[{'resource_id':'w1','revision':1,'kind':'workspace'}]};payload['input_binding']=binding
  self.store.accept('alice',{'id':'parent','namespace':'n1','kind':'invocation','payload':payload})
  if two:
   ref=make_input(self.root/'fixed-input','parent',binding);self.store.bind_input('admin','parent',binding,ref)
  claim=self.store.claim('worker',100);self.store.save_result('parent',claim['token'],self.refs['result']);return claim
 def body(self,resources=('s1',),target='s1'):
  return {'wait':{'id':'wait-original','namespace':'n1','target':target,'harness_ref':self.refs['h1'],'condition_ref':self.refs['condition'],'start_sequence':1,'filters':{},'refs':[],'release_refs':[self.refs[r+'-stop'] for r in resources]}}
 def accept(self,claim,body):return self.store.accept_decision('parent',claim['token'],'decision',self.refs['result'],self.refs['h1'],body)
 def raw(self):
  with sqlite3.connect('file:'+str(self.db)+'?mode=ro',uri=True) as db:
   db.row_factory=sqlite3.Row;return {t:[dict(x) for x in db.execute('SELECT * FROM '+t)] for t in ['requests','decisions','holders','releases','waits']}
 def close(self,label):
  self.store.close();(self.root/('authority-'+label+'.json')).write_text(json.dumps(self.audit,ensure_ascii=False,indent=2)+'\n')
def error_call(fn):
 try:return {'value':fn()}
 except Exception as e:return {'error':{'type':type(e).__name__,'code':getattr(e,'code',None),'message':str(e)}}
def child(f,action):
 f.save_meta();argv=[sys.executable,'-B',str(Path(__file__).resolve()),'--child',str(f.root),action];env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'source')};done=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=5)
 (f.root/('child-'+action+'.stdout')).write_text(done.stdout);(f.root/('child-'+action+'.stderr')).write_text(done.stderr)
 if done.returncode:raise RuntimeError('child driver failed '+str(done.returncode))
 return json.loads(done.stdout)
def tuples(f,resources):return [{'resource_id':r,'execution_id':'exec-'+r,'base_ref':f.refs[r+'-base']} for r in sorted(resources)]
def main_case(id):
 f=Fixture(ROOT/'evidence'/id);observations={};checks={};body=None;expected=[]
 try:
  if id=='RW05-held-matching-stop':
   f.acquire();claim=f.ready();body=f.body();f.accept(claim,body);expected=tuples(f,['s1']);observations['apply']=error_call(lambda:f.store.apply_decision('parent','decision'));checks['exact_busy']=observations['apply'].get('error',{}).get('code')=='busy'
  elif id=='RW06-release-retry-restart':
   f.acquire();f.acquire('w1');claim=f.ready(True);body=f.body(('s1','w1'));f.accept(claim,body);expected=tuples(f,['s1','w1']);f.close('before-child');observations['child_before']=child(f,'query');f=Fixture(f.root,False);f.release();f.release('w1');f.close('after-release');observations['child_apply']=child(f,'apply');f=Fixture(f.root,False)
   checks['child_before_original_barriers']=observations['child_before'].get('decision',{}).get('wait_barriers')==expected;checks['child_after_original_barriers']=observations['child_apply'].get('decision',{}).get('wait_barriers')==expected;checks['new_processes']=observations['child_before']['pid']!=os.getpid() and observations['child_apply']['pid']!=os.getpid()
  elif id=='RW07-empty-noholder':
   claim=f.ready();body=f.body(());f.accept(claim,body);observations['apply']=error_call(lambda:f.store.apply_decision('parent','decision'))
  elif id=='RW08-new-holder-after-original-release':
   f.acquire();claim=f.ready();body=f.body();f.accept(claim,body);expected=tuples(f,['s1']);f.release();f.acquire(new=True);observations['apply']=error_call(lambda:f.store.apply_decision('parent','decision'))
  else:
   claim=f.ready();body=f.body((),target='missing-resource' if id=='RW09-unregistered-target' else 'secret');observations['accept']=error_call(lambda:f.accept(claim,body));checks['target_exact_rejection']=observations['accept'].get('error',{}).get('code')==('not_found' if id=='RW09-unregistered-target' else 'denied')
  raw=f.raw();phase=raw['requests'][0]['phase'];checks['original_result']=json.loads(raw['requests'][0]['result_ref_json'])==f.refs['result']
  if id in ('RW09-unregistered-target','RW10-unauthorized-target'):checks.update(no_decision=not raw['decisions'],no_wait=not raw['waits'],original_decide=phase=='decide')
  else:
   decision=raw['decisions'][0];barrier_raw=decision.get('wait_barriers_json');observations['missing_barrier_column']='wait_barriers_json' not in decision;checks['fixed_barriers']=barrier_raw is not None and json.loads(barrier_raw)==expected;checks['original_body']=json.loads(decision['body_json'])==body
   if id=='RW05-held-matching-stop':checks.update(original_decide=phase=='decide',not_applied=decision['applied']==0,no_wait=not raw['waits'],holder_retained=len(raw['holders'])==1)
   else:
    checks.update(waiting=phase=='waiting',applied=decision['applied']==1,one_static_wait=len(raw['waits'])==1)
    if id=='RW08-new-holder-after-original-release':checks['new_holder_unchanged']=len(raw['holders'])==1 and raw['holders'][0]['execution_id']=='new-s1' and json.loads(raw['holders'][0]['base_ref_json'])==f.refs['s1-next']
    else:checks['no_holders']=not raw['holders']
    if expected:checks['original_release_tuples']=all(any(row.get('holder_json') is not None and json.loads(row['holder_json'])==t for row in raw['releases']) for t in expected)
  report={'case':id,'checks':checks,'status':'PASS' if all(checks.values()) else 'FAIL','raw':raw,'observations':observations,'expected_barriers_from_original_fixture':expected,'source':str(Path(sys.modules['lore_control'].__file__).resolve())};(f.root/'observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return {'case':id,'status':report['status'],'failed_checks':[k for k,v in checks.items() if not v]}
 finally:f.close('final')
def main():
 if len(sys.argv)>1 and sys.argv[1]=='--child':
  f=Fixture(Path(sys.argv[2]),False);out={'pid':os.getpid(),'source':str(Path(sys.modules['lore_control'].__file__).resolve())}
  if sys.argv[3]=='apply':out['apply']=error_call(lambda:f.store.apply_decision('parent','decision'))
  out['decision']=f.store.query_decision('decision');out['raw']=f.raw();f.close('child-'+sys.argv[3]);print(json.dumps(out));return 0
 started=time.time();protocol=json.loads((ROOT/'protocol.json').read_text());rows=[]
 for case in protocol['new_cases']:
  try:rows.append(main_case(case['id']))
  except Exception as e:rows.append({'case':case['id'],'status':'ERROR','error':{'type':type(e).__name__,'message':str(e)}})
 result={'status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL','cases':rows,'elapsed_seconds':time.time()-started,'protocol_sha256':sha((ROOT/'protocol.json').read_bytes()),'probe_sha256':sha(Path(__file__).read_bytes())};(ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
