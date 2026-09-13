"""Independent F wrapper: execute the unchanged 19 cases only from captured source."""
import argparse,hashlib,json,os,platform,subprocess,sys,time,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from validation.components.v.source_snapshot import capture,unchanged
from validation.components.r.process_group import cleanup
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
AUDIT = r"""import os,sys,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parent
out=root.parent/'imports';out.mkdir(exist_ok=True)
fd=os.open(out/(str(os.getpid())+'.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
def hook(event,args):
 if event!='exec':return
 path=getattr(args[0],'co_filename','')
 if path.startswith(str(root)):
  p=Path(path)
  row={'pid':os.getpid(),'filename':path,'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}
  os.write(fd,(json.dumps(row)+'\n').encode());os.fsync(fd)
sys.addaudithook(hook)
"""
def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--module',default='lore_files');p.add_argument('--suite',choices=['contract','scope'],default='contract');args=p.parse_args()
 if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch):p.error('fresh simple batch required')
 out=ROOT/'validation/components/f/evidence'/args.batch;out.mkdir(parents=True,exist_ok=False);stage=out/'workspace'
 report={'status':'INVALID','module':args.module,'scope':('Original F19' if args.suite=='contract' else 'Independent FS01-FS12 authority scope')+' from copied source; R/X authority fixtures only','started':time.time(),'source_before':{},'copied_before':{},'environment':{'python':sys.version,'platform':platform.platform(),'uid':os.getuid(),'interpreter':str(Path(sys.executable).resolve()),'interpreter_sha256':sha(Path(sys.executable).resolve()),'git_sha256':sha('/usr/bin/git')}}
 child=None;rc=1
 try:
  candidate=capture(args.module,[ROOT,ROOT/'validation/components/f'],stage);report['candidate']=candidate
  if candidate is None:stage.mkdir()
  files=[q for base in ['design/g3/f','validation/components/f'] for q in (ROOT/base).iterdir() if q.is_file() and q.suffix in ('.py','.md','.json')]
  files += [ROOT/'validation/components/v/source_snapshot.py',ROOT/'validation/components/r/process_group.py',ROOT/'design/g4/f-snapshot-runner-protocol.md']
  for original in files:
   dest=stage/original.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original.read_bytes());report['source_before'][str(original)]=sha(original);report['copied_before'][str(dest)]=sha(dest)
  audit=stage/'sitecustomize.py';audit.write_text(AUDIT);report['copied_before'][str(audit)]=sha(audit)
  argv=[sys.executable,'-B',str(stage/('validation/components/f/run_contract.py' if args.suite=='contract' else 'validation/components/f/run_scope.py')),'--module',args.module,'--batch','actual']
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(stage),'PYTHONDONTWRITEBYTECODE':'1'}
  report.update(argv=argv,cwd=str(stage),suite=args.suite,execution_environment=env);(out/'before.json').write_text(json.dumps(report,indent=2))
  with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
   child=subprocess.Popen(argv,cwd=stage,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   try:child.wait(timeout=180)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5);raise
  report['actual_exit']=child.returncode;inner=stage/'validation/components/f/evidence/actual/result.json';result=json.loads(inner.read_text());report['inner_result']={'path':str(inner),'sha256':sha(inner)}
  report['source_drift']=[q for field in ['source_before','copied_before'] for q,h in report[field].items() if not Path(q).is_file() or sha(q)!=h]
  report['candidate_unchanged']=candidate is None or unchanged(candidate)
  loaded=result.get('implementation',{});report['loaded_source_inside_snapshot']=all(Path(q).is_relative_to(stage) and sha(q)==h for q,h in loaded.items())
  seen=[]
  for path in sorted((out/'imports').glob('*.jsonl')):
   seen.extend(json.loads(line) for line in path.read_text().splitlines())
  report['observed_execution']=seen
  expected_sources={**report['copied_before'],**(candidate['executed_snapshot'] if candidate else {})}
  report['observed_source_bound']=bool(seen) and all(expected_sources.get(row['filename'])==row['sha256'] for row in seen)
  report['candidate_execution_pids']=sorted({row['pid'] for row in seen if candidate and row['filename'] in candidate['executed_snapshot']})
  expected=['F%02d'%n for n in range(1,20)] if args.suite=='contract' else ['FS%02d'%n for n in range(1,13)];executed=result['executed_cases'];report['counts']={'cases':len(executed)};report['inner_status']=result['status']
  if report['source_drift'] or not report['candidate_unchanged'] or not report['loaded_source_inside_snapshot'] or not report['observed_source_bound']:raise RuntimeError('execution source drift or unbound observed code')
  if result['status']=='PASS' and child.returncode==0 and candidate and loaded and sorted(executed)==expected and len(executed)==len(set(executed)) and not result.get('skipped') and len(report['candidate_execution_pids'])>=(4 if args.suite=='contract' else 1):report['status']='PASS';rc=0
  elif result['status']=='MISSING' and child.returncode==2 and not executed:report['status']='MISSING';rc=2
  else:report['status']='FAIL'
 except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)}
 finally:
  if child is not None:
   report['cleanup']=cleanup(child.pid)
   if child.poll() is None:child.wait(timeout=5)
   if report['cleanup']['before'] or not report['cleanup']['no_running_members']:report['status']='FAIL';rc=1
 report['finished']=time.time();(out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps({'status':report['status'],'counts':report.get('counts'),'batch':args.batch}));return rc
if __name__=='__main__':raise SystemExit(main())
