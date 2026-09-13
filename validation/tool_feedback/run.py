"""Finite original-file feedback projection and actual S/Node/Pi; no Engine/network."""
from pathlib import Path
import argparse,base64,copy,hashlib,json,subprocess,sys,time,types
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));HERE=Path(__file__).parent
from lore_runtime.tool_service import ToolService
from lore_runtime.tool_facts import ToolFacts
from lore_session.service import SessionService
from lore_session.snapshots import SnapshotStore
from validation.session_service.run import NoEngineX,Plans,Provider
D=copy.deepcopy
sha=lambda b:hashlib.sha256(b).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def source_ref(v):return dict(path=v['path'],bytes=v['size'],sha256=v['sha256'])
def bytes_ref(v):
 b=Path(v['path']).read_bytes();assert len(b)==v.get('bytes',v.get('size')) and sha(b)==v['sha256'];return b
def query_port(sample):
 row=D(sample['row']);record=D(sample['record']);receipt=row['receipt_ref']
 # Only original row/ref selection is fixture-controlled, no permissions claim.
 def authoritative(ref,purpose,expected):
  assert ref==receipt and purpose=='receipt' and all(receipt[k]==v for k,v in expected.items());return True
 return types.SimpleNamespace(_row=lambda eid,b: D(row) if eid==row['id'] and b==row['payload']['binding'] else None,
  control_reference=authoritative,_record=lambda selected:D(record),stdout_reference=ToolService.stdout_reference)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);a=ap.parse_args();assert Path(a.batch).name==a.batch
 out=HERE/'evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);original=json.loads((HERE/'originals.json').read_bytes());f=json.loads((ROOT/original['session_fixture']).read_bytes());checks=[]
 paths=[HERE/'run.py',HERE/'node.mts',HERE/'originals.json',HERE/'contract.md',ROOT/'validation/session_service/run.py',ROOT/'validation/session_service/fixtures.json',ROOT/'lore_runtime/tool_service.py',ROOT/'lore_runtime/tool_facts.py']+list((ROOT/'lore_session').glob('*.py'))+list((ROOT/'lore_session/node').glob('*.mts'))+list((ROOT/'harnesses/minimal').glob('*.mts'))
 before={str(v):sha(v.read_bytes()) for v in paths};snap=out/'source-before';snap.mkdir()
 for i,v in enumerate(paths):(snap/(str(i)+'-'+v.name)).write_bytes(v.read_bytes())
 def test(id,fn):
  try:observed=fn();checks.append(dict(id=id,passed=True,observed=observed))
  except Exception as e:checks.append(dict(id=id,passed=False,error=repr(e)))
 def qcheck():
  result=[];failures=[]
  for s in original['samples']:
   assert sha(Path(s['source_record']['path']).read_bytes())==s['source_record']['sha256'];b=s['row']['payload']['binding'];q=ToolService.query(query_port(s),s['id'],b);save(out/('query-'+s['id']+'.json'),q)
   result.append(q);assert q['stdout_ref']==s['row']['receipt_ref']['facility_ref']['stdout_ref']
   if q.get('exit_code')!=s['record']['result']['exit_code'] or q.get('stderr_ref')!=source_ref(s['record']['artifacts']['stderr']):failures.append(s['id'])
   else:bytes_ref(q['stderr_ref'])
  assert not failures, 'original failure feedback absent: '+str(failures)
  return result
 test('TF01-original-query',qcheck)
 def mismatch():
  s=original['samples'][0];bad=D(s['record']);bad['result']['exit_code']=0;obj=types.SimpleNamespace(_record=lambda row:bad)
  try:ToolFacts._result_ref(obj,s['row'])
  except Exception:return {'rejected':True}
  raise AssertionError('original stopped/record exit mismatch accepted')
 test('TF02-original-stop-exit',mismatch)
 sample=original['samples'][0];error_reply=D(f['replies'][1]);error_reply['result_ref']=D(sample['row']['receipt_ref']['facility_ref']['result_ref']);error_reply['publication_ref']=D(sample['row']['receipt_ref']['facility_ref']['publication_ref'])
 for name in ['stdout','stderr']:
  b=bytes_ref(sample['record']['artifacts'][name]);error_reply[name]={'data_b64':base64.b64encode(b).decode(),'bytes':len(b),'sha256':sha(b)}
 error_reply['exit_code']=1
 def callback(zero=False,mode=None):
  home=out/('service-'+mode if mode else 'service-zero' if zero else 'service-error');home.mkdir();log=[];reply=D(error_reply);reply['exit_code']=0 if zero else 1
  if zero:reply['stderr']={'data_b64':'','bytes':0,'sha256':sha(b'')};reply['stdout']=D(f['replies'][1]['stdout'])
  class Tools:
   def execute(self,*args):
    result=dict(status='RECEIVED',fresh=True,result_ref=D(reply['result_ref']),publication_ref=D(reply['publication_ref']),exit_code=reply['exit_code'])
    for n in ['stdout','stderr']:
     dest=home/(n+'.raw');dest.write_bytes(base64.b64decode(reply[n]['data_b64']));result[n+'_ref']={'path':str(dest),'bytes':dest.stat().st_size,'sha256':sha(dest.read_bytes())}
    if mode=='sha':result['stderr_ref']['sha256']='0'*64
    if mode=='bytes':result['stderr_ref']['bytes']+=1
    if mode=='exit':result['exit_code']=None
    if mode=='pair':del result['stderr_ref']
    return result
  x=NoEngineX(home,f,[('provider',f['frames'][1]),('tool',f['frames'][2]),('saved',f['frames'][3])],log)
  owner=SnapshotStore(home/'owners',f['originals']['provider']['request']['expected_scope']['namespace'],lambda *v:log.append('S.register'),global_budget_bytes=67108864)
  req=D(f['request']);req['action']='drive';error=None;result=None
  try:result=SessionService(x,owner,Provider(f,log,'normal'),Plans(x),Tools()).invoke(req,execution_id=x.id,deadline_monotonic=time.monotonic()+3)
  except Exception as exc:error=repr(exc)
  replies=[json.loads(raw) for raw in x.writes if json.loads(raw).get('type')=='tool.reply'];save(home/'observed.json',dict(replies=replies,log=log,result=result,error=error))
  if mode:
   assert error is not None and not replies, 'invalid stderr/code reached tool.reply';return dict(error=error,replies=replies)
  assert error is None
  assert len(replies)==1 and replies[0]['stdout']==reply['stdout'] and replies[0]['result_ref']==reply['result_ref'] and replies[0]['publication_ref']==reply['publication_ref'];assert replies[0]['stderr']==reply['stderr'] and replies[0]['exit_code']==reply['exit_code'];return replies[0]
 test('TF03-service-error',lambda:callback(False));test('TF04-service-zero',lambda:callback(True))
 negative_service={}
 for id,mode in [('TF07-bad-stderr-sha','sha'),('TF08-bad-stderr-bytes','bytes'),('TF09-unknown-exit','exit'),('TF10-pair-required','pair')]:
  try:negative_service[id]=dict(passed=True,observed=callback(mode=mode))
  except Exception as exc:negative_service[id]=dict(passed=False,error=repr(exc))
 save(out/'service-negative-checks.json',negative_service)
 save(out/'node-input.json',dict(original_model=original['model'],pi_root=original['pi_root'],fixture=f,error_reply=error_reply))
 node=Path('/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node');argv=[str(node),'--import',str(ROOT/'research/repos/pi/node_modules/tsx/dist/loader.mjs'),str(HERE/'node.mts'),str(out/'node-input.json'),str(out/'node-result.json')]
 config=json.loads((ROOT/'research/pi/tsconfig.json').read_bytes());config['compilerOptions']['baseUrl']=original['pi_root'];save(out/'tsconfig.json',config)
 run=subprocess.run(argv,cwd=ROOT,env={'PATH':str(node.parent)+':/usr/bin:/bin','LANG':'C.UTF-8','TSX_TSCONFIG_PATH':str(out/'tsconfig.json')},capture_output=True,timeout=40);save(out/'node-command.json',argv);(out/'node.stdout').write_bytes(run.stdout);(out/'node.stderr').write_bytes(run.stderr)
 if (out/'node-result.json').exists():
  for item in json.loads((out/'node-result.json').read_bytes())['checks']:
   if item['id'] in negative_service:item['service_check']=negative_service[item['id']];item['passed']=item['passed'] and negative_service[item['id']]['passed']
   checks.append(item)
 after={str(v):sha(v.read_bytes()) for v in paths};result=dict(status='PASS' if len(checks)==10 and all(v['passed'] for v in checks) and before==after and run.returncode==0 else 'FAIL',scope='NO_ENGINE_OR_NETWORK_TOOL_FEEDBACK_ONLY',checks=checks,source_before=before,source_after=after,source_unchanged=before==after,node_exit=run.returncode)
 save(out/'result.json',result);print(json.dumps({k:result[k] for k in ['status','checks','source_unchanged','node_exit']},ensure_ascii=False));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
