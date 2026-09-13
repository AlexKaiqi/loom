"""Run the unchanged R contracts entirely from a captured ordinary-file workspace."""
import argparse,hashlib,json,os,platform,sqlite3,subprocess,sys,time,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from validation.components.v.source_snapshot import capture,unchanged
from process_group import cleanup
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--module',default='lore_control');args=p.parse_args()
 if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch):p.error('simple fresh batch ID required')
 out=ROOT/'validation/components/r/evidence'/args.batch;out.mkdir(parents=True,exist_ok=False);stage=out/'workspace'
 report={'module':args.module,'status':'INVALID','scope':'R original22unit/23process from captured source; owner authorities remain explicit fixtures','started':time.time(),'source_before':{},'copied_before':{},'environment':{'python':sys.version,'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),'uid':os.getuid(),'interpreter':str(Path(sys.executable).resolve()),'interpreter_sha256':sha(Path(sys.executable).resolve())}}
 rc=1;child=None
 try:
  candidate=capture(args.module,[ROOT,ROOT/'validation/components/r'],stage);report['candidate']=candidate
  if candidate is None:stage.mkdir()
  files=[q for sub in ['design/g3/r','validation/components/r'] for q in (ROOT/sub).iterdir() if q.is_file() and q.suffix in ('.py','.md','.json')]
  files += [ROOT/'validation/components/v/source_snapshot.py',ROOT/'design/g4/r-snapshot-runner-protocol.md']
  for original in files:
   relative=original.relative_to(ROOT);dest=stage/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original.read_bytes());report['source_before'][str(original)]=sha(original);report['copied_before'][str(dest)]=sha(dest)
  argv=[sys.executable,'-B',str(stage/'validation/components/r/run_contract.py'),'--module',args.module,'--batch','actual']
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(stage),'PYTHONDONTWRITEBYTECODE':'1'}
  report.update(argv=argv,cwd=str(stage),execution_environment=env)
  (out/'before.json').write_text(json.dumps(report,indent=2))
  with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
   child=subprocess.Popen(argv,cwd=stage,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   try:child.wait(timeout=600)
   except subprocess.TimeoutExpired:
    os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5);raise
  report['actual_exit']=child.returncode;inner=stage/'validation/components/r/evidence/actual/result.json';result=json.loads(inner.read_text());report['inner_result']={'path':str(inner),'sha256':sha(inner)}
  changed=[q for field in ['source_before','copied_before'] for q,h in report[field].items() if not Path(q).is_file() or sha(Path(q))!=h]
  report['source_drift']=changed;report['candidate_unchanged']=candidate is None or unchanged(candidate)
  loaded=result.get('implementation',{});report['loaded_source_scope']='Main runner package source enumeration plus copied unchanged child drivers and fixed PYTHONPATH; not a per-child dynamic import audit';report['loaded_source_inside_snapshot']=all(Path(q).is_relative_to(stage) and sha(Path(q))==h for q,h in loaded.items())
  report['counts']={'units':len(result['executed_units']),'process':len(result['executed_process'])};report['inner_status']=result['status']
  if changed or not report['candidate_unchanged'] or not report['loaded_source_inside_snapshot']:raise RuntimeError('execution source mismatch')
  if result['status']=='PASS' and child.returncode==0 and candidate is not None and loaded and report['counts']=={'units':22,'process':23}:report['status']='PASS';rc=0
  elif result['status']=='MISSING' and child.returncode==2 and report['counts']=={'units':0,'process':0}:report['status']='MISSING';rc=2
  else:report['status']='FAIL';rc=1
 except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)}
 finally:
  if child is not None:
   report['process_group_cleanup']=cleanup(child.pid)
   if child.poll() is None:child.wait(timeout=5)
   if report['process_group_cleanup']['before'] or not report['process_group_cleanup']['no_running_members']:report['status']='FAIL';rc=1
 report['finished']=time.time();(out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps({'status':report['status'],'counts':report.get('counts'),'batch':args.batch}));return rc
if __name__=='__main__':raise SystemExit(main())
