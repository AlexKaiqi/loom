"""Run original X cases only from complete source copies, including verified F."""
from pathlib import Path
import argparse,hashlib,json,os,platform,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/v'))
from source_snapshot import capture,unchanged
sys.path.insert(0,str(ROOT/'validation/components/r'))
from process_group import cleanup
from source_closure import copy_f,AUDIT,inventory,python_children

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--module',default='lore_execution.adapter');ap.add_argument('--case');a=ap.parse_args()
 if not a.batch.replace('-','').isalnum():raise SystemExit('fresh alphanumeric batch required')
 out=ROOT/'validation/components/x/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);ws=out/'workspace'
 result={'status':'INVALID','type':'PARTIAL_COMPONENT_DIAGNOSTIC' if a.case else 'FORMAL_COMPONENT_RUN','module':a.module,'case':a.case,'started':time.time(),'platform':platform.platform(),'python':{'path':sys.executable,'sha256':digest(Path(sys.executable).resolve())},'snapshots':[]}
 def save(): (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 p=None;rc=1;bindings=[]
 try:
  source=capture(a.module,[ROOT,Path(__file__).parent],ws)
  if source is None:result.update(status='MISSING_COMPONENT',actual_runs=0);save();return 4
  result['snapshots'].append(source)
  paths=[*Path(__file__).parent.glob('*.py'),*list((ROOT/'design/g3/x').glob('*.json')),*list((ROOT/'design/g3/x').glob('*.md')),ROOT/'research/docker-linux/seccomp.json',ROOT/'design/g4/x-author-plan.md',ROOT/'validation/components/v/source_snapshot.py',ROOT/'validation/components/r/process_group.py',ROOT/'design/g4/x-independent-preparation-001/protocol.md']
  origin=ROOT/a.module.split('.')[0]
  if origin.is_dir():paths += [q for q in origin.rglob('*') if q.is_file() and (q.suffix in ('.json','.md') or q.name in ('LICENSE.moby','NOTICE.moby'))]
  for q in paths:
   if q.is_symlink():raise ValueError('symlink source input')
   dest=ws/q.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(q.read_bytes());bindings.append({'original':str(q),'copy':str(dest),'sha256':digest(q)})
  # A separate equivalence document preserves the original gate verbatim.
  f=copy_f(ws);result['F_source_equivalence']=f;bindings.extend(f['implementation']);bindings.append(f['gate'])
  equivalence=ws/'f-source-equivalence.json';audit=ws/'sitecustomize.py';audit.write_text(AUDIT)
  generated={str(equivalence):digest(equivalence),str(audit):digest(audit)};result['generated']=generated;result['inputs']=bindings
  cases=json.loads((ws/'design/g3/x/cases.json').read_text())['cases'];expected=inventory(cases,a.case);result['expected_inventory']=expected
  if not expected or (not a.case and (len(cases)!=28 or len(expected)!=97)):raise ValueError('original X28/97 inventory absent')
  argv=[sys.executable,'-B',str(ws/'validation/components/x/run.py'),'--batch','actual','--component-json',json.dumps([sys.executable,'-B','-m',a.module])]
  if a.case:argv+=['--case',a.case]
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1','LORE_X_REQUIRE_SOURCE_AUDIT':'1'};result.update(argv=argv,cwd=str(ws),execution_environment=env);save();started=time.monotonic()
  with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
   p=subprocess.Popen(argv,cwd=ws,stdout=stdout,stderr=stderr,start_new_session=True,env=env,close_fds=True)
   try:result['exit_code']=p.wait(timeout=120 if a.case else 11800)
   except subprocess.TimeoutExpired:result['error']='outer_deadline';result['exit_code']=124
   finally:result['cleanup']=cleanup(p.pid)
  result['elapsed_seconds']=time.monotonic()-started
  result['source_unchanged']=unchanged(source) and all(Path(x[k]).is_file() and digest(Path(x[k]))==x['sha256'] for x in bindings for k in ('original','copy')) and all(Path(q).is_file() and digest(Path(q))==h for q,h in generated.items())
  inner=ws/'validation/components/x/evidence/actual/assessment.json';observed=json.loads(inner.read_text());rows=observed.get('rows',[])
  result['inner']={'path':str(inner),'sha256':digest(inner),'status':observed['status']};result['actual_runs']=len(rows);result['failed']=[{'id':x['case_id'],'parameters':x['parameters'],'error':x.get('error'),'assessment':x.get('assessment')} for x in rows if x['status']!='PASS']
  actual=[{'case_id':x['case_id'],'parameters':x['parameters']} for x in rows];result['inventory_matches']=actual==expected and observed['type']==result['type'] and observed['case_suite_sha256']==digest(ws/'design/g3/x/cases.json')
  events=[json.loads(line) for log in sorted((out/'imports').glob('*.jsonl')) for line in log.read_text().splitlines()];executed=[e for e in events if e['kind']=='exec'];result['observed_execution']=events;result['python_child_closure']=python_children(events,ws)
  known={**source['executed_snapshot'],**generated,**{x['copy']:x['sha256'] for x in bindings}}
  result['observed_source_bound']=bool(executed) and all(known.get(x['filename'])==x['sha256'] for x in executed)
  adapters=[json.loads(line) for q in ws.glob('validation/components/x/evidence/actual/*/adapter-processes.jsonl') for line in q.read_text().splitlines()]
  result['adapter_processes']=adapters;result['candidate_execution_pids']=sorted({x['pid'] for x in executed if x['filename'] in source['executed_snapshot']})
  result['every_adapter_executed_copied_candidate']=bool(adapters) and all(row['pid'] in result['candidate_execution_pids'] for row in adapters)
  result['F_execution_pids']=sorted({x['pid'] for x in executed if x['filename'] in {i['copy'] for i in f['implementation']}})
  result['remaining_adapter_cleanup']=[{'pid':row['pid'],**cleanup(row['pid'])} for row in adapters]
  clean=not result['cleanup'].get('before') and all(not x['before'] and x['no_running_members'] for x in result['remaining_adapter_cleanup'])
  conditions=[observed['status']=='PASS',result['exit_code']==0,result['source_unchanged'],result['inventory_matches'],result['observed_source_bound'],result['every_adapter_executed_copied_candidate'],result['python_child_closure']['pass'],clean]
  if any(x['case_id']=='X016' for x in expected):conditions.append(bool(result['F_execution_pids']))
  result['status']='PASS' if all(conditions) else 'FAIL';rc=0 if result['status']=='PASS' else 1
 except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc)}
 finally:
  if p is not None:
   result.setdefault('cleanup',cleanup(p.pid))
   # Nested adapter sessions are explicit driver-owned IDs, never arbitrary host groups.
   for log in ws.glob('validation/components/x/evidence/actual/*/adapter-processes.jsonl'):
    for line in log.read_text().splitlines():
     pid=json.loads(line)['pid'];facts=cleanup(pid)
     if facts['before'] or not facts['no_running_members']:result.setdefault('late_cleanup',[]).append({'pid':pid,**facts});result['status']='FAIL';rc=1
  result['finished']=time.time();save()
 print(json.dumps({'status':result['status'],'actual_runs':result.get('actual_runs',0),'failed':result.get('failed')}));return rc
if __name__=='__main__':raise SystemExit(main())
