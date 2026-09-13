"""Execute all fixed R independent failure supplements from fresh source snapshots."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from validation.components.v.source_snapshot import capture,unchanged
from process_group import cleanup
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--module',default='lore_control');args=ap.parse_args()
 if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch):ap.error('simple fresh batch ID required')
 out=ROOT/'validation/components/r/evidence'/args.batch;out.mkdir(parents=True,exist_ok=False);started=time.time();report={'status':'INVALID','module':args.module,'scope':'R original association supplements; explicit owner fixtures, no X/F/S actual capability claim','source_before':{},'groups':[]};code=1
 sources=['validation/components/r/run_supplement.py','validation/components/r/wait_association_probe.py','validation/components/r/wait_barrier_probe.py','validation/components/r/input_fixture.py','design/g4/r-reference-independent-001/probe.py','design/g4/r-wait-independent-001/protocol.json','design/g4/r-reference-independent-001/protocol.json','design/g3/r/wait-reference-protocol.json','design/g3/r/wait-reference-supplement.md','design/g3/r/contract.md']
 report['source_before']={str(ROOT/p):sha(ROOT/p) for p in sources}
 definitions=[('wait-original','validation/components/r/wait_association_probe.py','design/g4/r-wait-independent-001/protocol.json','fixed_cases'),('references','design/g4/r-reference-independent-001/probe.py','design/g4/r-reference-independent-001/protocol.json','fixed_cases'),('wait-barriers','validation/components/r/wait_barrier_probe.py','design/g3/r/wait-reference-protocol.json','new_cases')]
 all_expected=[];all_observed=[]
 try:
  for name,driver,protocol,key in definitions:
   group=out/name;stage=group/'source';candidate=capture(args.module,[ROOT],stage)
   if candidate is None:report['status']='MISSING';code=2;break
   if args.module!='lore_control':raise ValueError('supplement currently fixes lore_control import surface')
   group.mkdir(parents=True,exist_ok=True);(group/'probe.py').write_bytes((ROOT/driver).read_bytes());(group/'protocol.json').write_bytes((ROOT/protocol).read_bytes());fixture=group/'fixture';fixture.mkdir();(fixture/'input_fixture.py').write_bytes((ROOT/'validation/components/r/input_fixture.py').read_bytes())
   expected=[c['id'] for c in json.loads((group/'protocol.json').read_text())[key]];all_expected+=expected
   item={'group':name,'candidate':candidate,'expected':expected,'driver_sha256':sha(group/'probe.py'),'protocol_sha256':sha(group/'protocol.json'),'input_fixture_sha256':sha(fixture/'input_fixture.py')};argv=[sys.executable,'-B',str(group/'probe.py')];env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(stage)};item.update(argv=argv,environment=env)
   child=None
   try:
    with (group/'stdout').open('wb') as so,(group/'stderr').open('wb') as se:
     child=subprocess.Popen(argv,cwd=group,env=env,stdout=so,stderr=se,start_new_session=True);child.wait(timeout=30)
    item['exit']=child.returncode;result=json.loads((group/'result.json').read_text());item['result_ref']={'path':str(group/'result.json'),'sha256':sha(group/'result.json')};item['status']=result['status'];item['cases']=result['cases'];observed=[c['case'] for c in result['cases']];all_observed+=observed;item['inventory_exact']=observed==expected and len(set(observed))==len(observed);item['sources_unchanged']=unchanged(candidate) and sha(group/'probe.py')==item['driver_sha256'] and sha(group/'protocol.json')==item['protocol_sha256'] and sha(fixture/'input_fixture.py')==item['input_fixture_sha256'];item['pass']=child.returncode==0 and result['status']=='PASS' and all(c['status']=='PASS' for c in result['cases']) and item['inventory_exact'] and item['sources_unchanged']
   except Exception as e:item.update(status='INVALID',error={'type':type(e).__name__,'message':str(e)},passed=False)
   finally:
    if child:
     item['cleanup']=cleanup(child.pid)
     if child.poll() is None:child.wait(timeout=5)
     if item['cleanup']['before'] or not item['cleanup']['no_running_members']:item['pass']=False
   report['groups'].append(item)
  report['source_drift']=[p for p,h in report['source_before'].items() if not Path(p).is_file() or sha(Path(p))!=h];report['expected_cases']=all_expected;report['executed_cases']=all_observed
  if report['status']!='MISSING':
   good=len(report['groups'])==3 and len(all_expected)==21 and all_expected==all_observed and len(set(all_observed))==21 and not report['source_drift'] and all(g.get('pass') for g in report['groups']);report['status']='PASS' if good else 'FAIL';code=0 if good else 1
 except Exception as e:report['error']={'type':type(e).__name__,'message':str(e)}
 report['elapsed_seconds']=time.time()-started
 if report['elapsed_seconds']>100:report['status']='FAIL';code=1
 report['implementation']={str(p.resolve()):sha(p) for p in (ROOT/'lore_control').glob('*.py')};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'cases':len(all_observed),'batch':args.batch}));return code
if __name__=='__main__':raise SystemExit(main())
