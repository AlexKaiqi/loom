"""Finite host original-file authority preparation; real F/R, no Engine or model."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args();assert a.batch and all(x.isalnum() or x in '-_' for x in a.batch)
 out=ROOT/'validation/host-files-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
 candidate=ROOT/'lore_runtime/host_files.py';result={'status':'MISSING','cases':[],'scope':'real F/R original-file authority; no Engine/model/NATS'}
 if candidate.exists():
  from lore_runtime.host_files import HostFiles
  from lore_files import FileStore
  from lore_control import ControlStore
  from lore_files.util import identity
  principal='runtime';namespace='host-files';resource='surface';source=out/'source';source.mkdir();(source/'notes.md').write_text('original notes\n');artifacts=out/'artifacts';artifacts.mkdir();plans=out/'plans';plans.mkdir()
  host={'principal':principal,'namespace':namespace,'authorization':{'owner':'trusted-runtime-files','namespace':namespace},'artifact_root':str(artifacts),'plan_root':str(plans),'initial_sources':[{'resource_id':resource,'domain':'surface','path':str(source),'root':identity(source),'revision':1}]}
  control=ControlStore(out/'R.sqlite',{principal:{'namespaces':[namespace],'roles':['runtime','admin','submit']}},reference_checker=lambda *a:False)
  authority=HostFiles(control,host);files=FileStore(out/'F',authority.authorization,authority.reference);authority.files=files
  binding=dict(host['initial_sources'][0],authorization=host['authorization']);coordination={'owner':'trusted-runtime-initial','binding':binding}
  before=hashlib.sha256(candidate.read_bytes()).hexdigest()
  def need(v,m):
   if not v:raise AssertionError(m)
  try:
   bundle=files.capture('initial-source',binding,coordination);version=bundle['version_ref'];ref={'owner':'F','kind':'file','path':'notes.md','version_ref':version,'sha256':hashlib.sha256(b'original notes\n').hexdigest()}
   need(files.read_reference(ref,host['authorization'])==b'original notes\n','original authorized read differs');result['cases'].append({'id':'HF01','status':'PASS'})
   bad=dict(binding,path=str(artifacts));denied=False
   try:files.capture('bad-source',bad,{'owner':'trusted-runtime-initial','binding':bad})
   except Exception:denied=True
   need(denied,'changed initial binding admitted');need(not authority.control_reference(ref,'harness',None),'ordinary notes treated as Harness');result['cases'].append({'id':'HF02','status':'PASS'})
   (source/'notes.md').write_text('changed mutable notes\n');need(files.read_reference(ref,host['authorization'])==b'original notes\n','historical read used changed current path');bad=dict(ref,sha256='0'*64);denied=False
   try:files.read_reference(bad,host['authorization'])
   except Exception:denied=True
   need(denied,'bad historical digest admitted');result['cases'].append({'id':'HF03','status':'PASS'})
   from validation import session_plans_probe as sp
   from lore_runtime.session_plans import SessionPlans
   sp.ROOT=ROOT/'validation/session-plan-evidence/context-independent-001/workspace'
   authorities=[]
   def product(c,f,s,h,resolver,register):
    capref=c.query(h['principal'],'invocation-one')['payload']['capability_ref']
    _,_,contents=f.versions.load(capref['version_ref']);cap=json.loads(contents[capref['path']]);sources=[]
    for item in cap['original_refs'].values():
     ref=item['source_ref'];prov=json.loads(f.versions.git('cat-file','blob',ref['version_ref']['git_ref']+':provenance.json'));binding=prov['binding']
     assert Path(binding['path'])==f.control.parents[2]/'originals'
     sources.append({k:binding[k] for k in ('resource_id','domain','path','root','revision')})
    config=dict(h,artifact_root=str(f.control.parent),initial_sources=sources)
    hf=HostFiles(c,config);hf.files=f;hf.session_resolver=resolver
    authorities.append(hf);f.authorization_checker=hf.authorization;f.reference_checker=hf.reference
    return SessionPlans(c,f,s,config,hf.resolve,register)
   fixture=sp.Fixture(out/'HF04',product)
   try:
    item=fixture.verify(fixture.plan());need(item is not None,'actual R/F/SessionPlans integration absent');result['cases'].append({'id':'HF04','status':'PASS','original_group':'SP01 original full-source verification'})
    hf=authorities[0];need(hf.control_reference(fixture.H,'harness',None),'real Harness invalid')
    wrong_owner=hf.control_reference(dict(fixture.H,owner='S'),'harness',None)
    original=fixture.control.query(fixture.principal,'invocation-one');capbytes=hf.resolve(fixture.cap,'capability',{'invocation':original});need(capbytes==fixture.peer.store.read_reference(fixture.cap,fixture.host['authorization']),'true F capability rejected')
    capbody=json.loads(capbytes);original_ref=next(iter(capbody['original_refs'].values()))['source_ref']
    original_bytes=hf.resolve(original_ref,'original-file',{'invocation':original});need(original_bytes==fixture.peer.store.read_reference(original_ref,fixture.host['authorization']),'true F original-file rejected')
    prior_reference=fixture.control.reference_checker
    fixture.control.reference_checker=lambda ref,purpose,expected: hf.control_reference(ref,purpose,expected) if purpose=='harness' else prior_reference(ref,purpose,expected)
    typed=[]
    for key,value in [('owner','S'),('kind','directory')]:
     bad=dict(fixture.cap,**{key:value});payload=dict(fixture.payload,capability_ref=bad)
     parent=fixture.control.accept(fixture.principal,{'id':'typed-capability-'+key,'namespace':fixture.ns,'kind':'invocation','payload':payload})
     accepted=True
     try:hf.resolve(bad,'capability',{'invocation':parent})
     except Exception:accepted=False
     direct=hf.authorization(fixture.host['authorization'],'read_reference',{'reference':bad})
     typed.append({'purpose':'capability','changed_field':key,'resolve_accepted':accepted,'read_authorized':direct})
     bad=dict(original_ref,**{key:value});accepted=True
     try:hf.resolve(bad,'original-file',{'invocation':original})
     except Exception:accepted=False
     direct=hf.authorization(fixture.host['authorization'],'read_reference',{'reference':bad})
     typed.append({'purpose':'original-file','changed_field':key,'resolve_accepted':accepted,'read_authorized':direct})
    version=fixture.surface['bundle']['version_ref'];_,_,contents=fixture.peer.store.versions.load(version)
    full_surface_ref={'owner':'F','kind':'file','version_ref':version,'path':'notes.md','sha256':hashlib.sha256(contents['notes.md']).hexdigest()}
    need(hf.authorization(fixture.host['authorization'],'read_reference',{'reference':full_surface_ref}),'active original full F reference rejected')
    fixture.control.db.execute('UPDATE resources SET active=0 WHERE id=?',(version['resource_id'],))
    inactive=hf.authorization(fixture.host['authorization'],'read_reference',{'reference':full_surface_ref})
    result['owner_controls']={'wrong_harness_owner_accepted':wrong_owner,'inactive_resource_read_accepted':inactive,'non_harness_typed_references':typed}
    need(not wrong_owner and not inactive,'wrong owner or inactive original R grant accepted')
    need(all(not item['resolve_accepted'] and not item['read_authorized'] for item in typed),'non-F owner/kind accepted in an F file entry')
    result['cases'].append({'id':'HF05','status':'PASS'})
   finally:fixture.close()
   result['status']='PASS'
  except Exception as ex:
   import traceback
   result.update(status='FAIL',error=repr(ex),traceback=traceback.format_exc())
  finally:control.close()
  result.update(source_sha256=before,source_unchanged=before==hashlib.sha256(candidate.read_bytes()).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return 0 if result['status']=='PASS' else 2 if result['status']=='MISSING' else 1
if __name__=='__main__':raise SystemExit(main())
