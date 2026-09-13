"""Reuse existing source-copy/audit facilities for the fixed Node increment driver."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/v'))
from source_snapshot import capture,unchanged
sys.path.insert(0,str(ROOT/'validation/components/x'))
from source_closure import copy_f,AUDIT,python_children
sys.path.insert(0,str(ROOT/'validation/components/r'))
from process_group import cleanup

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--module',default='lore_execution.adapter');ap.add_argument('--case');a=ap.parse_args()
 if not a.batch.replace('-','').isalnum():ap.error('fresh batch')
 out=ROOT/'validation/components/x_node_profile/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);ws=out/'workspace';rows=[];result={'status':'INVALID','actual_runs':0,'started':time.time(),'module':a.module,'case':a.case};process=None
 def persist():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 try:
  source=capture(a.module,[ROOT,Path(__file__).parent],ws)
  if source is None:result.update(status='MISSING_COMPONENT',exit_code=4);persist();return 4
  paths=[*Path(__file__).parent.glob('*.py'),*Path(__file__).parent.glob('*.mts'),*list((ROOT/'design/g3/x-node-profile').glob('*.json')),*list((ROOT/'design/g3/x-node-profile').glob('*.md'))]
  paths += [*list((ROOT/'validation/components/x').glob('*.py')),*list((ROOT/'design/g3/x').glob('*.json')),ROOT/'research/docker-linux/seccomp.json',ROOT/'validation/components/s/probe-public.mts',ROOT/'validation/components/v/source_snapshot.py',ROOT/'validation/components/r/process_group.py']
  original=ROOT/a.module.split('.')[0]
  if original.is_dir():paths += [p for p in original.rglob('*')if p.is_file()and p.suffix!='.py'and '__pycache__'not in p.parts]
  for p in paths:
   if p.is_symlink():raise ValueError('source symlink')
   q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());rows.append({'original':str(p),'copy':str(q),'sha256':sha(p)})
  f=copy_f(ws);rows+=f['implementation']+[f['gate']];(ws/'sitecustomize.py').write_text(AUDIT)
  generated={str(ws/'sitecustomize.py'):sha(ws/'sitecustomize.py'),str(ws/'f-source-equivalence.json'):sha(ws/'f-source-equivalence.json')}
  suite=json.loads((ws/'design/g3/x-node-profile/cases-inputs.json').read_text())['cases'];expected=[x['id']for x in suite if a.case is None or x['id']==a.case]
  argv=[sys.executable,'-B',str(ws/'validation/components/x_node_profile/run.py'),'--out',str(out/'actual'),'--component-json',json.dumps([sys.executable,'-B','-m',a.module])]
  if a.case:argv+=['--case',a.case]
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1','LORE_X_REQUIRE_SOURCE_AUDIT':'1'}
  result.update(inputs=rows,candidate_source=source,F_source_equivalence=f,generated=generated,argv=argv,environment=env,expected_case_ids=expected);persist()
  with (out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
   process=subprocess.Popen(argv,cwd=ws,env=env,stdout=stdout,stderr=stderr,start_new_session=True,close_fds=True)
   try:code=process.wait(timeout=150 if a.case else 1500)
   except subprocess.TimeoutExpired:code=124
   finally:result['cleanup']=cleanup(process.pid)
  result['exit_code']=code
  assessment=json.loads((out/'actual/assessment.json').read_text());result['assessment']={'path':str(out/'actual/assessment.json'),'sha256':sha(out/'actual/assessment.json')};result['actual_runs']=len(assessment['rows'])
  events=[json.loads(line)for p in (out/'imports').glob('*.jsonl')for line in p.read_text().splitlines()];executed=[x for x in events if x['kind']=='exec'];known={**source['executed_snapshot'],**generated,**{x['copy']:x['sha256']for x in rows}}
  result['source_unchanged']=unchanged(source)and all(Path(x[k]).is_file()and sha(Path(x[k]))==x['sha256']for x in rows for k in('original','copy'))and all(sha(Path(p))==h for p,h in generated.items())
  result['actual_execution']=events;result['actual_copy_execution_bound']=bool(executed)and all(known.get(e['filename'])==e['sha256']for e in executed);result['python_child_closure']=python_children(events,ws)
  adapters=[json.loads(line)for p in (out/'actual').rglob('adapter-processes.jsonl')for line in p.read_text().splitlines()];candidate_pids={e['pid']for e in executed if e['filename']in source['executed_snapshot']}
  result['all_adapters_executed_candidate_copy']=bool(adapters)and all(x['pid']in candidate_pids for x in adapters)
  result['adapter_cleanup']=[{'pid':x['pid'],**cleanup(x['pid'])}for x in adapters]
  result['inventory_matches']=[x['case_id']for x in assessment['rows']]==expected
  result['status']='PASS'if code==0 and assessment['status']=='PASS'and result['source_unchanged']and result['actual_copy_execution_bound']and result['python_child_closure']['pass']and result['all_adapters_executed_candidate_copy']and result['inventory_matches']and all(x['no_running_members']and not x['before']for x in result['adapter_cleanup'])else 'FAIL'
 except Exception as exc:result['error']=repr(exc)
 finally:
  if process:result.setdefault('cleanup',cleanup(process.pid))
  result['finished']=time.time();persist()
 print(json.dumps({'status':result['status'],'actual_runs':result['actual_runs'],'error':result.get('error')}));return 0 if result['status']=='PASS'else 1
if __name__=='__main__':raise SystemExit(main())
