"""Load an existing trusted startup owner and original F records, without live captures."""
import copy,json
from pathlib import Path
from lore_execution.errors import require
from lore_execution.journal import canonical,digest
from lore_execution.node_profile import NodeProfile
from lore_execution.ordinary_sources import file_object,readonly
from lore_files.util import ordinary_path,identity
from lore_files.metadata import walk


def read_json(path):
 _,raw=file_object(path);value=json.loads(raw)
 require(raw==canonical(value)+b"\n","INVALID_REQUEST","original startup JSON is not canonical")
 return value

def open_existing(cls,root,config,control):
 from .startup_assets import CODE_FILES,KINDS,SLOT
 root=ordinary_path(root);c=copy.deepcopy(config)
 require(root.is_dir(),"INVALID_REQUEST","existing startup owner missing")
 require(read_json(root/'startup-inputs.json')==c,"INVALID_REQUEST","original startup configuration differs")
 host=read_json(root/'host.json');paths={k:root/n for k,n in (("artifact_root","artifacts"),("plan_root","plans"),("authority_root","authority"),("state_root","X-state"),("event_input_root","E-inputs"))}
 for path in paths.values():require(ordinary_path(path).is_dir(),"INVALID_REQUEST","original host directory missing")
 sources=host['initial_sources'];require(len(sources)==2,"INVALID_REQUEST","initial source set differs")
 with control._tx(False):
  control._authorize(c['principal'],c['namespace'])
  for domain,source in zip(('surface','workspace'),sources):
   require(set(source)=={'resource_id','domain','path','root','revision'} and source['domain']==domain and source['revision']==1
    and source['resource_id']==c['sources'][domain]['resource_id'] and source['path']==c['sources'][domain]['path']
    and set(source['root'])=={'dev','ino'} and all(type(source['root'][k]) is int and source['root'][k]>0 for k in ('dev','ino')),
    "UNAUTHORIZED","saved initial source differs from fixed configuration")
   # Read the R record, not resolve/current_resource: an unconfirmed exchange must remain queryable.
   row=control._resource(source['resource_id']);control._resource_access(row,c['principal'],'read')
   require(row['namespace']==c['namespace'] and row['kind']==domain and row['path']==source['path'],"UNAUTHORIZED","original R resource scope differs")
 profile_path=paths['artifact_root']/'node-profile.json';request_path=paths['artifact_root']/'node-request-template.json'
 profile_ref,profile_raw=file_object(profile_path);request_ref,request_raw=file_object(request_path)
 for original,ref in ((c['profile_ref'],profile_ref),(c['request_template_ref'],request_ref)):
  require(all(original[k]==ref[k] for k in ('bytes','sha256')),"INVALID_REQUEST","retained profile/template differs")
 profile=json.loads(profile_raw);request=json.loads(request_raw)
 require(profile['id']=='fixed-node-pi-session-v1' and profile['slot_reservation']==SLOT and request['schema_version']==2 and request['environment']==profile['id'],"INVALID_REQUEST","retained admitted profile differs")
 deps=copy.deepcopy(c['deps_mount']);readonly(deps)
 require(deps['role']=='dependencies' and deps['target']=='/opt' and deps['read_only'] is True,"UNAUTHORIZED","dependency mount differs")
 code=paths['artifact_root']/'code-source'
 require(set(c['code_sources'])==set(CODE_FILES) and {p.relative_to(code).as_posix() for p in code.rglob('*') if p.is_file()}==set(CODE_FILES),"INVALID_REQUEST","retained code set differs")
 for name in CODE_FILES:
  ref,raw=file_object(code/name);require(all(c['code_sources'][name][k]==ref[k] for k in ('bytes','sha256')),"INVALID_REQUEST","retained code bytes differ")
 slot_ref=dict(owner='trusted-X-configuration',slot_id='runtime-shared-slot',revision=1,plan_sha256=digest(canonical(SLOT)),role='session')
 slot=dict(slot_id=slot_ref['slot_id'],revision=1,namespace=c['namespace'],plan_sha256=slot_ref['plan_sha256'],plan=copy.deepcopy(SLOT),allowed_principals=['trusted-S'],state_root=str(paths['state_root']))
 trusted=dict(schema='lore-x-trusted-node-test-config/v1',transport_principal='trusted-S',state_root=str(paths['state_root']),profiles=[dict(id=profile['id'],**profile_ref)],slots=[slot],grants=[],references=dict(snapshots=[],F_views=[],owner_receipts=[]),read_only_roots=[],allowed_harness_entries=[dict(path='/harness/lore_session/node/entry.mts',sha256=c['code_sources']['lore_session/node/entry.mts']['sha256'],argv_modes=['--config'])],dynamic_reference_authorities=[dict(root=str(paths['authority_root']),identity='trusted-Runtime-F-S-owner',namespace=c['namespace'],allowed_kinds=list(KINDS),rule='immutable-full-ref-registration/v1')])
 config_ref,_=file_object(root/'trusted-X-config.json');require(read_json(config_ref['path'])==trusted,"UNAUTHORIZED","retained trusted config differs")
 expected=dict(principal=c['principal'],namespace=c['namespace'],**{k:str(v) for k,v in paths.items()},initial_sources=sources,authorization=dict(owner='trusted-runtime-host',namespace=c['namespace'],root=str(root)),trusted_config_ref=config_ref,profile_ref=profile_ref,request_template_ref=request_ref,deps_mount=deps,slot_ref=slot_ref,model=c['model'])
 require(host==expected,"UNAUTHORIZED","retained host differs from fixed owner configuration")
 NodeProfile(config_ref['path'],config_ref['sha256'],host['state_root'])
 name=digest(canonical(dict(kind='readonly-view',ref=deps)))+'.json'
 require(read_json(paths['authority_root']/name)==dict(kind='readonly-view',ref=deps,registered_scope=dict(namespace=c['namespace'],role='dependencies')),"UNAUTHORIZED","original dependency registration missing/different")
 value=cls.__new__(cls);value.root,value.config,value.host,value.config_ref=root,c,host,config_ref;value._reentry=True
 return value


def build_existing(owner,files):
 host=owner.host;auth=host['authorization'];root=Path(host['artifact_root'])
 def capture(path,resource,domain,original_root=None):
  binding=dict(resource_id=resource,domain=domain,path=str(path),root=original_root if original_root is not None else identity(ordinary_path(path)),revision=1,authorization=auth)
  inputs=dict(operation='capture',binding=binding,coordination=dict(owner='trusted-runtime-initial',binding=binding),base_ref=None)
  record=files.journal.get('startup-'+digest(canonical(binding)),inputs)
  require(record is not None and record.get('state')=='complete',"INVALID_REQUEST","original complete startup capture missing")
  result=record['result'];files.versions.validate_bundle(result);version=result['version_ref']
  require(version['resource_id']==resource and version['domain']==domain and json.loads(files.versions.git('cat-file','blob',version['git_ref']+':provenance.json'))==inputs,"UNAUTHORIZED","original capture provenance differs")
  return result
 versions={s['domain']:capture(s['path'],s['resource_id'],s['domain'],s['root']) for s in host['initial_sources']}
 code=capture(root/'code-source','startup-code-'+digest(str(owner.root).encode()),'surface')
 inputs=dict(operation='materialize',version_ref=code['version_ref'],target_path=str(root/'code-read'),authorization=auth,profile='host-v1')
 record=files.journal.get('startup-code-read-'+digest(str(owner.root).encode()),inputs)
 require(record is not None and record.get('state')=='complete',"INVALID_REQUEST","original code materialization missing")
 material=record['result'];_,tree,_=files.versions.load(code['version_ref']);target=ordinary_path(root/'code-read')
 require(material['path']==str(target) and material['version_ref']==code['version_ref'] and material['root']==identity(target) and walk(target,files.limits)[0]==tree,"INVALID_REQUEST","retained code materialization differs")
 def descriptor(label,body):
  path=root/(label+'-source');require(read_json(path/'descriptor.json')==body,"INVALID_REQUEST","retained descriptor differs")
  bundle=capture(path,'startup-'+label+'-'+digest(str(owner.root).encode()),'surface')
  ref=dict(owner='F',kind='file',path='descriptor.json',version_ref=bundle['version_ref'],sha256=digest(canonical(body)+b'\n'))
  require(files.read_reference(ref,auth)==canonical(body)+b'\n',"INVALID_REQUEST","original descriptor F bytes differ")
  return ref
 harness=descriptor('harness',dict(code=dict(bundle=code,materialized=material),entry='lore_session/node/entry.mts',harness_entry='harnesses/runtime/index.mts'))
 originals=copy.deepcopy(owner.config.get('original_refs',{}))
 for row in originals.values():files.read_reference(row['source_ref'],auth)
 cap=descriptor('capability',dict(targets=['runtime','workspace'],limits=owner.config['capability_limits'],original_refs=originals))
 specs=[dict(request_id='startup-register-'+digest(canonical([host['namespace'],s['resource_id']])),resource_id=s['resource_id'],namespace=host['namespace'],kind=s['domain'],path=s['path'],harness_ref=harness,grants={host['principal']:['read','write']}) for s in host['initial_sources']]
 return copy.deepcopy(dict(host=host,initial_refs=dict(harness_ref=harness,capability_ref=cap,**{d+'_version_ref':b['version_ref'] for d,b in versions.items()}),registrations_spec=specs,config_ref=owner.config_ref))
