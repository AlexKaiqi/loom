"""Finite V contract runner. Evidence batches are append-only."""
import argparse,hashlib,importlib,io,json,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--module',default='lore_validation.gate');a=p.parse_args()
if not a.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.batch):p.error('fresh simple batch required')
out=ROOT/'validation/components/v/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
inputs={str(q.relative_to(ROOT)):sha(q) for b in ['design/g3/v','validation/components/v'] for q in (ROOT/b).glob('*') if q.is_file() and q.suffix in {'.py','.md','.json'}}
plan=json.loads((ROOT/'design/g3/v/cases.json').read_text());expected=[c['id'] for c in plan['cases']];record={'scope':'V component contracts, not Runtime acceptance','started':time.time(),'module':a.module,'inputs':inputs,'expected_cases':expected,'executed_cases':[],'status':'STARTED'};rc=1
try:
 from source_snapshot import capture,load,unchanged
 captured=capture(a.module,sys.path,out/'candidate-source')
 if captured is None:
  record.update(status='MISSING',reason='V implementation unavailable; no cases credited');rc=2
 else:
  record['implementation']=captured;mod=load(captured)
  import test_gate
  test_gate.AUDIT=mod.audit;test_gate.OUT=out
  suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_gate.Contract);actual=[t._testMethodName.split('_')[1] for t in suite]
  if sorted(actual)!=sorted(expected) or len(set(actual))!=len(expected):raise RuntimeError('fixed inventory mismatch')
  class Result(unittest.TextTestResult):
   def startTest(self,t):record['executed_cases'].append(t._testMethodName.split('_')[1]);super().startTest(t)
  log=io.StringIO();result=unittest.TextTestRunner(stream=log,resultclass=Result,verbosity=2).run(suite);(out/'tests.txt').write_text(log.getvalue());record.update(tests_run=result.testsRun,failures=[{'test':str(t),'detail':d} for t,d in result.failures],errors=[{'test':str(t),'detail':d} for t,d in result.errors],skipped=[str(t) for t,_ in result.skipped])
  stable=all((ROOT/n).is_file() and sha(ROOT/n)==h for n,h in inputs.items()) and unchanged(captured);record['source_unchanged']=stable
  passed=result.wasSuccessful() and not result.skipped and sorted(record['executed_cases'])==sorted(expected) and stable;record['status']='PASS' if passed else 'FAIL';rc=0 if passed else 1
except Exception as e:record.update(status='INVALID',error={'type':type(e).__name__,'message':str(e)});rc=1
record['finished']=time.time();(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'batch':a.batch,'status':record['status'],'expected':len(expected),'executed':len(record['executed_cases'])}));sys.exit(rc)
