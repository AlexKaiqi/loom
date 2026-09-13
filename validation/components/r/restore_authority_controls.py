"""R22 authority rejection preparation. Actual files/layouts, not R/F/X behavior."""
import copy,hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
from restore_fixture import add_ref,check,root_record,tree_digest
root=Path(__file__).resolve().parents[3];out=Path(__file__).parent/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False);originals=out/'originals';originals.mkdir();f=SimpleNamespace(refroot=originals,refs={});rows=[]
current=out/'current';current.mkdir();(current/'content').write_text('actual historical bytes');retired=out/'retired';retired.mkdir();(retired/'content').write_text('previous current bytes')
fields={'restore_plan_id':'plan1','request_id':'install1','resource_id':'s1','domain':'surface','execution_id':'exec1','generation':'g1','base_ref':{'fixture':'base1'},'version_ref':{'fixture':'historical1'}}
stop_fields={k:fields[k] for k in ['resource_id','execution_id','generation','base_ref']};stop=add_ref(f,'rp-stop','stopped','X',**stop_fields)
staged=add_ref(f,'rp-stage','staged','F',**fields,root=root_record(current),tree_sha256=tree_digest(current),stopped_ref=stop)
receipt=add_ref(f,'rp-receipt','installation','F',**fields,current=root_record(current),retired=root_record(retired),tree_sha256=tree_digest(current),stopped_ref=stop)
def record(name,ref,purpose,expected,want):
 actual=check(ref,purpose,expected,f.refs,f.refroot);rows.append({'name':name,'ref':copy.deepcopy(ref),'purpose':purpose,'expected_binding':expected,'want':want,'actual':actual,'matched':actual is want})
record('actual-staged-root',staged,'staged',fields,True);record('actual-installed-layout',receipt,'installation',fields,True)
wrong_stop=add_ref(f,'rp-other-stop','stopped','X',**{**stop_fields,'generation':'g2'});record('genuine-other-generation-stop',wrong_stop,'stopped',None,True);record('reject-other-generation-stop',wrong_stop,'stopped',stop_fields,False)
wrong=add_ref(f,'rp-other-receipt','installation','F',**{**fields,'generation':'g2'},current=root_record(current),retired=root_record(retired),tree_sha256=tree_digest(current),stopped_ref=stop);record('genuine-other-generation-receipt',wrong,'installation',None,True);record('reject-other-generation-receipt',wrong,'installation',fields,False)
original=(originals/'rp-receipt').read_bytes();(originals/'rp-receipt').write_bytes(b'X'+original[1:]);(out/'corrupted-receipt.raw').write_bytes((originals/'rp-receipt').read_bytes());record('same-length-corrupt-receipt',receipt,'installation',fields,False);(originals/'rp-receipt').write_bytes(original)
missing=add_ref(f,'rp-missing-receipt','installation','F',**fields,current=root_record(current),retired=root_record(retired),tree_sha256=tree_digest(current),stopped_ref=stop);(originals/'rp-missing-receipt').rename(out/'missing-original.raw');record('missing-original-receipt',missing,'installation',fields,False)
original_tree=(current/'content').read_bytes();(current/'content').write_bytes(b'X'+original_tree[1:]);(out/'changed-tree.raw').write_bytes((current/'content').read_bytes());record('same-object-tree-bytes-changed',receipt,'installation',fields,False);(current/'content').write_bytes(original_tree)
current.rename(out/'saved-current');current.mkdir();(current/'content').write_text('actual historical bytes');record('different-actual-root',receipt,'installation',fields,False)
result={'scope':'authority fixture only; no R/X/F implementation passed','status':'PASS' if all(x['matched'] for x in rows) else 'FAIL','records':rows,'sources':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('restore_fixture.py')]},'raw_files':{str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file()}}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({'status':result['status'],'controls':len(rows)}));raise SystemExit(0 if result['status']=='PASS' else 1)
