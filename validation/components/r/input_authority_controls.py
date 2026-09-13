"""Actual-file authority rejection controls; no R/E implementation."""
import argparse,copy,hashlib,json,os,platform
from pathlib import Path
from input_fixture import make_input,check_input_ref,canonical
p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args()
if not a.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.batch):p.error('fresh simple batch required')
root=Path(__file__).resolve().parents[3];out=root/'validation/components/r/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
binding={'namespace':'n1','source':'alice','start_sequence':1,'filters':{'names':['notice']},'page_size':16,'surface_ref':{'fixture':'surface1'},'previous_session_ref':None,'execution_targets':[]};expected={'invocation_id':'inv1','binding':binding};records=[]
def record(name,ref,want,exp=expected):
 actual=check_input_ref(ref,exp,out);records.append({'name':name,'ref':ref,'expected_binding':exp,'expected':want,'actual':actual,'matched':actual is want})
ref=make_input(out/'positive','inv1',binding);record('actual-four-files',ref,True)
missing=copy.deepcopy(ref);missing['path']=str(out/'absent');record('missing-directory',missing,False)
corrupt=make_input(out/'corrupt','inv1',binding);f=Path(corrupt['path'])/'events.jsonl';raw=f.read_bytes();f.write_bytes(b'X'+raw[1:]);record('same-length-corruption',corrupt,False)
restored=make_input(out/'restored','inv1',binding);record('same-original-bytes',restored,True)
other=copy.deepcopy(binding);other['filters']={'names':['other']};wrong=make_input(out/'other-selector','inv1',other);record('genuine-other-selector',wrong,True,None);record('reject-wrong-association',wrong,False)
stale=make_input(out/'stale','inv1',binding);Path(stale['path']).rename(out/'original-object');make_input(out/'stale','inv1',binding);record('different-actual-directory-object',stale,False)
member=make_input(out/'missing-member','inv1',binding);m=Path(member['path'])/'manifest.json';data=json.loads(m.read_bytes());del data['files']['events.jsonl'];m.write_bytes(canonical(data));member['manifest_sha256']=hashlib.sha256(m.read_bytes()).hexdigest();record('valid-hash-missing-manifest-member',member,False)
result={'scope':'authority-fixture-only; no R/E behavior passed','status':'PASS' if all(x['matched'] for x in records) else 'FAIL','records':records,'environment':{'platform':platform.platform(),'python':platform.python_version(),'uid':os.getuid()},'inputs':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path(__file__).with_name('input_fixture.py')]},'raw_files':{str(f.relative_to(out)):{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in out.rglob('*') if f.is_file()}}
(out/'assessment.json').write_text(json.dumps(result,indent=2));print(json.dumps({'status':result['status'],'controls':len(records)}));raise SystemExit(0 if result['status']=='PASS' else 1)
