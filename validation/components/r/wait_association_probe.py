"""Independent predeclared wait association probe; no candidate/original-test edits."""
from pathlib import Path
import copy,hashlib,json,os,sqlite3,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source'))
from lore_control import ControlStore
sha=lambda b:hashlib.sha256(b).hexdigest()
canonical=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
CHILD="""import os,sys
f=open(sys.argv[1],'a'); f.write('original-writer-open\\n'); f.flush()
print(os.getpid(),flush=True)
sys.stdin.readline()
f.close()
"""
def observe(child):
 rc=child.poll(); out={'pid':child.pid,'exit':rc}
 path=Path('/proc')/str(child.pid)/'stat'
 if path.exists():
  raw=path.read_text();fields=raw[raw.rfind(')')+2:].split();out.update(state=fields[0],starttime=int(fields[19]))
 return out

def one(label,mode):
 out=ROOT/'evidence'/label;out.mkdir(parents=True,exist_ok=False);originals=out/'originals';originals.mkdir();surface=out/'surface';surface.mkdir();db_path=out/'control.sqlite'; refs={};audit=[];children={};sut=None
 def original(id,kind,owner,**binding):
  v=dict(id=id,kind=kind,owner=owner,**binding); data=canonical(v);(originals/id).write_bytes(data);refs[id]=v|{'sha256':sha(data)};return refs[id]
 def checker(ref,purpose,expected=None):
  valid=False;reason='missing/mismatched original'
  if isinstance(ref,dict):
   file=originals/ref.get('id','__missing')
   if file.is_file():
    b=file.read_bytes(); saved=json.loads(b); valid=sha(b)==ref.get('sha256') and saved=={k:v for k,v in ref.items() if k!='sha256'}
    kinds={'harness':'harness','result':'tool_result','base':'file_version','published':'file_version','condition':'code','wait_ref':'file_version','stopped':'stopped'}
    valid=valid and (purpose not in kinds or saved.get('kind')==kinds[purpose])
    if valid and purpose=='stopped':
     c=children[saved['witness']['pid']]; current=observe(c); valid=current['exit'] is not None and current['exit']==saved['witness']['exit'];reason='original own child exited'
    if valid and expected is not None:
     context=json.loads((originals/'base-owner-contexts.json').read_text()).get(ref['id'],{}) if purpose=='base' else saved
     valid=all(context.get(k)==v for k,v in expected.items());reason='checked exact requested association'
  audit.append({'ref_id':ref.get('id') if isinstance(ref,dict) else None,'purpose':purpose,'expected':copy.deepcopy(expected),'valid':valid,'reason':reason})
  return valid
 try:
  h=original('h-original','harness','F');result=original('result-original','tool_result','X');base=original('base-original','file_version','F');other=original('base-other','file_version','F');cond=original('condition-original','code','F')
  (originals/'base-owner-contexts.json').write_text(json.dumps({'base-original':{'resource_id':'s1'},'base-other':{'resource_id':'s1'},'published-original':{'resource_id':'s1'}}))
  child=subprocess.Popen([sys.executable,'-B','-c',CHILD,str(surface/'writer-value')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
  children[child.pid]=child;ready=int(child.stdout.readline().strip());before=observe(child);assert ready==child.pid and before['exit'] is None
  opened={str(f.name):os.readlink(f) for f in (Path('/proc')/str(child.pid)/'fd').iterdir()}
  if mode=='wrong_execution':
   # Authentic completed exec-finished is distinct from the still-held exec-active.
   child.stdin.close();child.wait(timeout=3);stop_obs=observe(child)
   active=subprocess.Popen([sys.executable,'-B','-c',CHILD,str(surface/'writer-value')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
   children[active.pid]=active;assert int(active.stdout.readline().strip())==active.pid;active_before=observe(active)
   holder_exec='exec-active';stop_base=base
  else:
   child.stdin.close();child.wait(timeout=3);stop_obs=observe(child);active=None;active_before=None;holder_exec='exec-finished';stop_base=other if mode=='wrong_base' else base
  stopped=original('stopped-original','stopped','X',resource_id='s1',execution_id='exec-finished',base_ref=stop_base,witness=before|{'exit':stop_obs['exit']})
  published=original('published-original','file_version','F',resource_id='s1',execution_id='exec-finished',base_ref=base)
  authority={'admin':{'namespaces':['n1'],'roles':['admin','submit','runtime']},'alice':{'namespaces':['n1'],'roles':['submit']}}
  sut=ControlStore(db_path,authority=authority,reference_checker=checker)
  sut.register('admin','register-s1','s1','n1','surface',str(surface),h,{'alice':['read','write'],'admin':['read','write']})
  sut.acquire('s1',holder_exec,base)
  expected_holder={'resource_id':'s1','execution_id':holder_exec,'base_ref':base}
  authentic=checker(stopped,'stopped');matches_original=checker(stopped,'stopped',expected_holder)
  if mode in ('correct','missing'):sut.release('s1',holder_exec,stopped,published)
  if mode=='missing':(originals/'stopped-original').unlink()
  req={'id':'invocation-original','namespace':'n1','kind':'invocation','payload':{'resource_id':'s1','resource_revision':1,'harness_ref':h,'input_ref':None,'source_ref':None}}
  sut.accept('alice',req);claim=sut.claim('worker-original',100);sut.save_result(req['id'],claim['token'],result)
  wait={'id':'wait-original','namespace':'n1','target':'s1','harness_ref':h,'condition_ref':cond,'start_sequence':1,'filters':{},'refs':[base],'release_refs':[stopped]}
  outcome={}
  try:
   outcome['accepted']=sut.accept_decision(req['id'],claim['token'],'decision-original',result,h,{'wait':wait});outcome['applied']=sut.apply_decision(req['id'],'decision-original')
  except Exception as exc:outcome['error']={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}
  sut.close();sut=None
  with sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True) as sql:
   sql.row_factory=sqlite3.Row;raw={table:[dict(row) for row in sql.execute('SELECT * FROM '+table)] for table in ['resources','requests','holders','releases','decisions','waits']};(out/'raw.sql').write_text('\n'.join(sql.iterdump())+'\n')
  phase=raw['requests'][0]['phase'];new=ControlStore(db_path,authority=authority,reference_checker=checker);query=new.query('alice',req['id']);claimed=new.claim('fresh-worker',200);new.close()
  checks={'authentic_stopped_original':authentic,'original_result_preserved':json.loads(raw['requests'][0]['result_ref_json'])==result,'restart_phase_matches':query['phase']==phase,'no_successor_rows':len(raw['requests'])==1}
  if mode in ('wrong_execution','wrong_base'):
   checks.update(independent_tuple_mismatch=not matches_original,not_waiting=phase not in ('waiting','settled'),original_holder_preserved=len(raw['holders'])==1 and raw['holders'][0]['execution_id']==holder_exec and json.loads(raw['holders'][0]['base_ref_json'])==base)
   if mode=='wrong_execution':checks['original_writer_still_alive']=observe(active)['exit'] is None
  elif mode=='correct':checks.update(correct_tuple_matches=matches_original,waiting=phase=='waiting',holder_released=not raw['holders'],static_wait=len(raw['waits'])==1,no_claimable_wait=claimed is None)
  else:checks.update(exact_reference_invalid=outcome.get('error',{}).get('code')=='reference_invalid',not_waiting=phase=='decide',no_wait=not raw['waits'],no_decision=not raw['decisions'])
  report={'case':label,'mode':mode,'source_path':str(Path(sys.modules['lore_control'].__file__).resolve()),'expected_holder':expected_holder,'initial_child':before,'opened_fds':opened,'finished_child':stop_obs,'active_child_before':active_before,'active_child_after':observe(active) if active else None,'phase':phase,'fresh_query':query,'fresh_claim':claimed,'outcome':outcome,'checks':checks,'status':'PASS' if all(checks.values()) else 'FAIL'}
  (out/'observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(out/'authority-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(out/'raw.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
  return {'case':label,'status':report['status'],'phase':phase,'failed_checks':[k for k,v in checks.items() if not v]}
 finally:
  if sut is not None:sut.close()
  for c in children.values():
   if c.poll() is None:
    if c.stdin and not c.stdin.closed:c.stdin.close()
    try:c.wait(timeout=3)
    except subprocess.TimeoutExpired:c.kill();c.wait(timeout=3)
  (out/'cleanup.json').write_text(json.dumps([observe(c) for c in children.values()],indent=2)+'\n')

def main():
 started=time.time();results=[]
 for label,mode in [('RW01-wrong-execution','wrong_execution'),('RW02-wrong-base','wrong_base'),('RW03-correct-release-positive','correct'),('RW04-missing-evidence','missing')]:results.append(one(label,mode))
 elapsed=time.time()-started;report={'status':'PASS' if all(x['status']=='PASS' for x in results) else 'FAIL','cases':results,'elapsed_seconds':elapsed,'protocol_sha256':sha((ROOT/'protocol.json').read_bytes()),'probe_sha256':sha(Path(__file__).read_bytes()),'original_45_status':'independent-001 PASS only original22+23 scope','scope':'real SQLite/ref bytes/own child facts; not X physical isolation'}
 (ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
