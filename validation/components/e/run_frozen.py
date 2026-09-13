"""Execute E, approved R and fixed NATS client from one captured source workspace."""
import argparse,json,os,platform,signal,subprocess,sys,time
from pathlib import Path
from snapshot_support import digest,save,copy_file,package,drift,audit_execution
from dependency_snapshot import gate_original
import snapshot_verdict
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/r'))
from process_group import cleanup

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--batch',required=True);parser.add_argument('--module',default='lore_events');parser.add_argument('--r-module',default='lore_control');parser.add_argument('--r-gate',required=True);args=parser.parse_args()
 if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch):parser.error('fresh simple batch ID required')
 out=ROOT/'validation/components/e/evidence'/args.batch;out.mkdir(parents=True,exist_ok=False);stage=out/'workspace';stage.mkdir();(out/'audit').mkdir()
 report={'status':'INVALID','scope':'E captured-source component profile; R original gate preserved, copy equivalence is not another R gate','started':time.time(),'source':{'original':{},'copied':{}},'module':args.module,'r_module':args.r_module,'runs':[],'environment':{'python':sys.version,'platform':platform.platform(),'uid':os.getuid()}};record=report['source'];rc=1
 try:
  for sub in ['validation/components/e','design/g3/e']:
   for p in sorted((ROOT/sub).iterdir()):
    if p.is_file() and p.suffix in ('.py','.md','.json'):copy_file(p,stage/p.relative_to(ROOT),record)
  for name in ['validation/components/r/process_group.py','design/g4/e-snapshot-runner-protocol.md','design/g4/e-snapshot-environment.json']:
   copy_file(ROOT/name,stage/name,record)
  config=json.loads((ROOT/'design/g4/e-snapshot-environment.json').read_text())
  for source,expected in config['files'].items():
   p=Path(source)
   if digest(p)!=expected:raise ValueError('fixed environment source mismatch: '+source)
   relative=Path('research/.venvs/runtime-research/bin/python') if source=='/usr/bin/python3.10' else p.relative_to(ROOT)
   dest=copy_file(p,stage/relative,record)
   if source=='/usr/bin/python3.10' or dest.name=='nats-server':dest.chmod(0o755)
  ep=package(args.module,ROOT,stage,record) or package(args.module,ROOT/'validation/components/e',stage,record);rp=package(args.r_module,ROOT,stage,record);report['packages']={'E':ep,'R':rp}
  gate_path=Path(args.r_gate).resolve()
  # Gate checked before any candidate import, test run or NATS start.
  gate=gate_original(gate_path)
  if rp is None:raise RuntimeError('MISSING R package')
  if gate['implementation']!={k:v['sha256'] for k,v in rp['source_to_copy'].items()}:raise RuntimeError('MISSING approved full R package closure')
  gatecopy=copy_file(gate_path,stage/'dependency/r-gate.json',record)
  proof={'schema':'lore.source-equivalence/r-v1','workspace':str(stage),'gate_original':str(gate_path),'gate_copy':str(gatecopy),'gate_sha256':digest(gate_path),'source_to_copy':rp['source_to_copy'],'copied_package_root':rp['copied_package_root']}
  proof_path=out/'r-source-equivalence.json';save(proof_path,proof);report['r_equivalence']={'path':str(proof_path),'sha256':digest(proof_path)}
  if ep is None:raise RuntimeError('MISSING E candidate package')
  if not (stage/'validation/components/e/run_observation.py').is_file():raise RuntimeError('MISSING frozen observation supplement driver')
  copy_file(ROOT/'validation/components/e/snapshot_audit.py',stage/'sitecustomize.py',record)
  interpreter=stage/'research/.venvs/runtime-research/bin/python'
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(stage),'PYTHONDONTWRITEBYTECODE':'1','LORE_EVENT_MODULE':args.module,'LORE_CONTROL_MODULE':args.r_module,'LORE_R_GATE':str(gatecopy),'LORE_R_SOURCE_EQUIVALENCE':str(proof_path),'LORE_DEPENDENCY_AUDIT':str(out/'dependency-audit.jsonl'),'LORE_SNAPSHOT_ROOT':str(stage),'LORE_SNAPSHOT_AUDIT_DIR':str(out/'audit')}
  report['execution_environment']=env;save(out/'before.json',report)
  deadline=time.monotonic()+600
  runs=[('original','run_contract.py',['actual-original']),('observation','run_observation.py',['--batch','actual-observation'])]
  for label,driver,arguments in runs:
   if time.monotonic()>=deadline:report['runs'].append({'label':label,'pass':False,'error':{'type':'TimeoutError','message':'whole wrapper deadline exhausted before entry'}});break
   child=None;row={'label':label,'argv':[str(interpreter),'-B',str(stage/'validation/components/e'/driver),*arguments]}
   try:
    with (out/(label+'-stdout.log')).open('wb') as stdout,(out/(label+'-stderr.log')).open('wb') as stderr:
     child=subprocess.Popen(row['argv'],cwd=stage,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
     try:child.wait(timeout=max(1,deadline-time.monotonic()))
     except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5);raise
    row['actual_exit']=child.returncode
    inner=stage/'validation/components/e/evidence'/('actual-'+label)/'result.json';result=json.loads(inner.read_text());row['result']={'path':str(inner),'sha256':digest(inner)};row['status']=result.get('status');row['tests_run']=result.get('tests_run')
    row['inventory_pass']=(snapshot_verdict.original if label=='original' else snapshot_verdict.observation)(result)
    row['pass']=child.returncode==0 and row['status']=='PASS' and row['inventory_pass']
   except Exception as error:row.update(pass_=False,error={'type':type(error).__name__,'message':str(error)})
   finally:
    if child is not None:
     row['cleanup']=cleanup(child.pid)
     if child.poll() is None:child.wait(timeout=5)
     if row['cleanup']['before'] or not row['cleanup']['no_running_members']:row['pass']=False
    report['runs'].append(row)
  report['audit']=audit_execution(out,stage,record,[ep,rp],stage/'research/.cache/nats-server/nats-server')
  report['status']='PASS' if len(report['runs'])==2 and all(r.get('pass') for r in report['runs']) and all(report['audit']['checks'].values()) else 'FAIL';rc=0 if report['status']=='PASS' else 1
 except RuntimeError as error:
  report['error']={'type':type(error).__name__,'message':str(error)};report['status']='MISSING' if str(error).startswith('MISSING') else 'FAIL';rc=2 if report['status']=='MISSING' else 1
 except Exception as error:report.update(status='FAIL',error={'type':type(error).__name__,'message':str(error)});rc=1
 finally:
  report['source_drift']=drift(record)
  if report['source_drift']:report['status']='FAIL';rc=1
  if 'r_equivalence' in report and digest(report['r_equivalence']['path'])!=report['r_equivalence']['sha256']:report['status']='FAIL';rc=1
  report['finished']=time.time();save(out/'result.json',report)
 print(json.dumps({'batch':args.batch,'status':report['status'],'runs':len(report['runs'])}));return rc
if __name__=='__main__':raise SystemExit(main())
