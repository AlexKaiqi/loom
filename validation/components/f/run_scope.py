"""Finite preregistered F authority-scope driver. Missing implementation is never green."""
import argparse, ast, contextlib, hashlib, importlib, io, json, os, platform, sys, time, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--module',default='lore_files');parser.add_argument('--batch',required=True);args=parser.parse_args()
if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch):parser.error('fresh simple batch ID required')
out=ROOT/'validation/components/f/evidence'/args.batch;out.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs={str(p.relative_to(ROOT)):sha(p) for base in [ROOT/'design/g3/f',ROOT/'validation/components/f'] for p in base.glob('*') if p.suffix in {'.py','.md','.json'}}
plan=json.loads((ROOT/'design/g3/f/scope-cases.json').read_text());expected=[x['id'] for x in plan['cases']]
record={'scope':'F independent component contract; controlled R/X ports only, no real cross-facility proof','module':args.module,'inputs':inputs,'python':platform.python_version(),'expected_cases':expected,'executed_cases':[],'status':'STARTED','assertions':'unittest assertions against actual filesystem/Git and fixed fixture; failures retained','started':time.time()}
rc=1
try:
 try:module=importlib.import_module(args.module)
 except ModuleNotFoundError as e:
  if e.name!=args.module:raise
  record.update(status='MISSING',reason='production component module unavailable; no tests credited');rc=2
 else:
  origin=Path(module.__file__).resolve();package=origin.parent if origin.name=='__init__.py' else None
  files=sorted(package.rglob('*.py')) if package else [origin];sources={str(p):sha(p) for p in files};record['implementation']=sources
  import test_scope as tests
  tests.FACTORY=module.FileStore;tests.OUT=out;tests.MODULE=args.module
  suite=unittest.defaultTestLoader.loadTestsFromTestCase(tests.Contract)
  discovered=[t._testMethodName.split('_')[1] for t in suite]
  if len(discovered)!=len(expected) or sorted(discovered)!=sorted(expected):raise RuntimeError('registered/discovered test inventory mismatch')
  class Result(unittest.TextTestResult):
   def startTest(self,test):record['executed_cases'].append(test._testMethodName.split('_')[1]);super().startTest(test)
  log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite);(out/'test-log.txt').write_text(log.getvalue())
  record['tests_run']=result.testsRun;record['failures']=[{'test':str(t),'detail':s} for t,s in result.failures];record['errors']=[{'test':str(t),'detail':s} for t,s in result.errors]
  record['skipped']=[{'test':str(t),'reason':s} for t,s in result.skipped];record['source_unchanged']=all(Path(p).is_file() and sha(Path(p))==h for p,h in sources.items());record['inputs_unchanged']=all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in inputs.items())
  success=result.wasSuccessful() and not result.skipped and record['source_unchanged'] and record['inputs_unchanged'] and sorted(record['executed_cases'])==sorted(expected)
  record['status']='PASS' if success else 'FAIL';rc=0 if success else 1
except BaseException as e:
 record.update(status='INVALID',error={'type':type(e).__name__,'message':str(e)});rc=1
record['finished']=time.time();(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'status':record['status'],'expected':len(expected),'executed':len(record['executed_cases']),'batch':str(out)},indent=2));sys.exit(rc)
