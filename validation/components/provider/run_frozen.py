"""Independent provider acceptance wrapper: copied source executes all original workers."""
import argparse,hashlib,json,os,platform,subprocess,sys,time,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from validation.components.v.source_snapshot import capture,unchanged
from validation.components.r.process_group import cleanup
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
AUDIT = "import os,sys,json,hashlib\nfrom pathlib import Path\nroot=Path(__file__).resolve().parent\nout=root.parent/'imports';out.mkdir(exist_ok=True)\nfd=os.open(out/(str(os.getpid())+'.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)\ndef hook(event,args):\n if event!='exec':return\n path=getattr(args[0],'co_filename','')\n if path.startswith(str(root)):\n  p=Path(path)\n  row={'pid':os.getpid(),'filename':path,'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}\n  os.write(fd,(json.dumps(row)+'\\n').encode());os.fsync(fd)\nsys.addaudithook(hook)\n"

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--batch',required=True);parser.add_argument('--module',default='lore_provider');parser.add_argument('--selection',choices=['all','bad','missing'],default='all');args=parser.parse_args()
 if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch):parser.error('fresh simple batch required')
 out=ROOT/'validation/components/provider/evidence'/args.batch;out.mkdir(parents=True,exist_ok=False);stage=out/'workspace';child=None;rc=1
 report={'status':'INVALID','module':args.module,'selection':args.selection,'scope':'Provider finite wire profile only; actual local HTTP and copied candidate workers, no real proxy/Pi/S acceptance','started':time.time(),'source_before':{},'copied_before':{},'environment':{'python':sys.version,'platform':platform.platform(),'interpreter':str(Path(sys.executable).resolve()),'interpreter_sha256':sha(Path(sys.executable).resolve()),'uid':os.getuid()}}
 try:
  candidate=capture(args.module,[ROOT,ROOT/'validation/components/provider'],stage);report['candidate']=candidate
  if candidate is None:stage.mkdir()
  paths=[p for p in (ROOT/'design/g3/provider').rglob('*') if p.is_file()]+list((ROOT/'validation/components/provider').glob('*.py'))
  paths += [ROOT/'validation/components/v/source_snapshot.py',ROOT/'validation/components/r/process_group.py',ROOT/'design/g4/provider-snapshot-protocol.md']
  for original in paths:
   if original.is_symlink():raise RuntimeError('source symlink is not captured')
   dest=stage/original.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original.read_bytes());report['source_before'][str(original)]=sha(original);report['copied_before'][str(dest)]=sha(dest)
  audit=stage/'sitecustomize.py';audit.write_text(AUDIT);report['copied_before'][str(audit)]=sha(audit)
  argv=[sys.executable,'-B',str(stage/'validation/components/provider/run_contract.py'),'--module',args.module,'--batch','actual','--selection',args.selection]
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(stage)+':'+str(stage/'validation/components/provider'),'PYTHONDONTWRITEBYTECODE':'1'}
  report.update(argv=argv,cwd=str(stage),execution_environment=env);(out/'before.json').write_text(json.dumps(report,indent=2))
  with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
   child=subprocess.Popen(argv,cwd=stage,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   try:child.wait(timeout=65)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5);raise
  report['actual_exit']=child.returncode;actual=stage/'validation/components/provider/evidence/actual';inner=actual/'result.json';result=json.loads(inner.read_text());observations=json.loads((actual/'observations.json').read_text());report['inner_result']={'path':str(inner),'sha256':sha(inner)}
  requests=json.loads((stage/'design/g3/provider/request-cases.json').read_text())['cases'];responses=json.loads((stage/'design/g3/provider/cases.json').read_text())['cases'];expected=[c['id'] for c in responses+requests]
  if args.selection=='bad':expected=[id for id in expected if id in {'PW01-text','PW08-short-body','PQ04-untrusted-url'}]
  if args.selection=='missing':expected=[requests[0]['id']]
  report['expected_case_ids']=expected;report['executed_case_ids']=[o['case_id'] for o in observations]
  report['source_drift']=[q for group in ['source_before','copied_before'] for q,h in report[group].items() if not Path(q).is_file() or sha(q)!=h];report['candidate_unchanged']=candidate is None or unchanged(candidate)
  seen=[]
  for path in sorted((out/'imports').glob('*.jsonl')):seen.extend(json.loads(line) for line in path.read_text().splitlines())
  report['observed_execution']=seen;bound={**report['copied_before'],**(candidate['executed_snapshot'] if candidate else {})}
  report['observed_source_bound']=bool(seen) and all(bound.get(x['filename'])==x['sha256'] for x in seen)
  pids=sorted({x['pid'] for x in seen if candidate and x['filename'] in candidate['executed_snapshot']});report['candidate_worker_pids']=pids
  worker_pids=sorted(o['returned']['pid'] for o in observations if o['returned'].get('status')=='RETURNED');report['returned_worker_pids']=worker_pids
  report['counts']={'workers':len(observations),'http_requests':result['http_requests']};report['inner_status']=result['status']
  if report['source_drift'] or not report['candidate_unchanged'] or not report['observed_source_bound']:raise RuntimeError('candidate or observed execution source drift')
  if report['executed_case_ids']!=expected or len(set(expected))!=len(expected):raise RuntimeError('original sample inventory mismatch')
  if result['status']=='PASS' and child.returncode==0 and args.selection=='all' and len(expected)==33 and candidate and pids==worker_pids and len(pids)==33 and all(o['exit_code']==0 and not o['failures'] for o in observations):report['status']='PASS_WIRE_COMPONENT_FINITE_PROFILE_ONLY';rc=0
  elif result['status']=='MISSING' and child.returncode==2 and result['http_requests']==0:report['status']='MISSING';rc=2
  else:report['status']='FAIL'
 except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)}
 finally:
  if child is not None:
   report['cleanup']=cleanup(child.pid)
   if child.poll() is None:child.wait(timeout=5)
   if report['cleanup']['before'] or not report['cleanup']['no_running_members']:report['status']='FAIL';rc=1
 report['finished']=time.time();(out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps({'status':report['status'],'counts':report.get('counts'),'batch':args.batch}));return rc
if __name__=='__main__':raise SystemExit(main())
