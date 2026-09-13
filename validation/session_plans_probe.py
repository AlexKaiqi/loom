"""Five bounded, real R/E-file/F/S/X-validator checks. Never opens an Engine or NATS."""
import argparse,copy,hashlib,importlib,json,os,shutil,subprocess,sys,traceback,io,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
IDS=['SP01','SP02','SP03','SP04','SP05']
def raw(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_bytes(raw(v)+b'\n')
def fact(p):p=Path(p);return dict(path=str(p),sha256=sha(p.read_bytes()),bytes=p.stat().st_size)
def execution_id(parent,action):return 's-exec-'+sha(raw([parent,action]))
def confirmation_id(eid):return 's-'+sha(raw([eid,'s-service-final']))
def identity(p):s=Path(p).stat();return dict(dev=s.st_dev,ino=s.st_ino)
def need(v,m):
 if not v:raise AssertionError(m)
def rejected(call):
 try:call()
 except Exception as e:
  need(getattr(e,'code',None) in ('reference_invalid','denied','stale','not_found','input_invalid','invalid_snapshot','conflict','UNAUTHORIZED','INVALID_REQUEST','VERSION_CORRUPT','STALE_BINDING'),'unexpected exception '+repr(e))
  return dict(code=e.code,message=str(e))
 raise AssertionError('bad source or binding accepted')

class Fixture:
 def __init__(self,root,product):
  from validation.components.s.f_peer import Peer
  from lore_control import ControlStore
  from lore_session.snapshots import SnapshotStore
  from lore_events.input_files import packet,publish,validate
  self.root=Path(root);self.root.mkdir(parents=True);self.calls=[];self.principal='operator';self.ns='session-plan-test'
  case=self.root/'case';port=case/'peer-state/f-port';port.mkdir(parents=True)
  for role in ('surface','workspace','input','originals'):(case/role).mkdir()
  (case/'surface/template.md').write_text('Original {{notes.md}}\n');(case/'surface/notes.md').write_text('original notes\n')
  (case/'workspace/numbers.json').write_text('[2,3,5]\n');(case/'input/events.jsonl').write_bytes(b'');(case/'input/feedback.txt').write_text('original feedback\n');(case/'originals/log').write_text('original retained log\n')
  self.peer=Peer(port,dict(namespace=self.ns,principal=self.principal))
  refs=self.peer.prepare_fixture_input(surface=str(case/'surface'),workspace=str(case/'workspace'),input_dir=str(case/'input'),originals=str(case/'originals'),version='original')
  item=self.peer.lookup('inputs',refs['input_ref']);self.input_body=item['document']
  self.H=self.peer.lookup('harnesses',refs['harness_ref'])['full_ref']
  capability=copy.deepcopy(self.peer.lookup('capabilities',refs['capability_ref'])['document']);capability['original_refs']={name:dict(source_ref=row['source_ref'],read_path=row['read_path']) for name,row in self.input_body['original_refs'].items()}
  self.cap=self.peer.document('capabilities',capability)[1]['full_ref']
  self.surface=self.input_body['source_F']['surface'];self.workspace=self.input_body['workspace'];self.views={sha(raw(v['bundle']['version_ref'])):v for v in (self.surface,self.workspace)}
  self.scope=dict(namespace=self.ns,surface_id=self.surface['bundle']['version_ref']['resource_id'],session_id='session-one',session_generation=1)
  self.S=dict(owner='S',**self.scope,confirmation_request_id=None)
  self.control=ControlStore(self.root/'R.sqlite',{self.principal:dict(namespaces=[self.ns],roles=['admin','submit','runtime'])},reference_checker=self.rref)
  self.reg={}
  for role,v in [('surface',self.surface),('workspace',self.workspace)]:
   self.reg[role]=self.control.register(self.principal,'register-'+role,v['bundle']['version_ref']['resource_id'],self.ns,role,v['materialized']['path'],self.H,{self.principal:['read','write']})
  self.selector=dict(namespace=self.ns,source=self.principal,start_sequence=1,filters={},page_size=16,surface_ref=self.surface['bundle']['version_ref'],previous_session_ref=None,execution_targets=[dict(resource_id=v['bundle']['version_ref']['resource_id'],version_ref=v['bundle']['version_ref']) for v in (self.surface,self.workspace)])
  self.payload=dict(resource_id=self.reg['surface']['id'],resource_revision=1,harness_ref=self.H,input_ref=None,input_binding=self.selector,session_ref=self.S,source_result_ref=None,capability_ref=self.cap)
  self.event_root=self.root/'E-inputs';self.event_root.mkdir()
  self.accept('invocation-one',self.payload)
  plans=self.root/'plans';plans.mkdir();authority_root=plans/'authority';authority_root.mkdir();state=plans/'X-state';state.mkdir()
  self.authority_root=authority_root;self.snapshots=SnapshotStore(plans/'S-originals',self.ns,self.register)
  dp=ROOT/'original-host/dependencies-manifest.json';dm=load(dp)
  deps=dict(role='dependencies',source=dm['root'],target='/opt',read_only=True,manifest_ref=fact(dp),content_ref=dm['source_ref'])
  profile_ref=fact(ROOT/'original-host/profile.json');profile=load(profile_ref['path'])
  slot_ref=dict(owner='trusted-X-configuration',slot_id='session-plans-slot',revision=1,plan_sha256=sha(raw(profile['slot_reservation'])),role='session')
  slot=dict(slot_id=slot_ref['slot_id'],revision=1,namespace=self.ns,plan_sha256=slot_ref['plan_sha256'],plan=profile['slot_reservation'],allowed_principals=['trusted-S'],state_root=str(state))
  config=dict(schema='lore-x-trusted-node-test-config/v1',transport_principal='trusted-S',state_root=str(state),profiles=[dict(id=profile['id'],**profile_ref)],slots=[slot],grants=[],references=dict(snapshots=[],F_views=[],owner_receipts=[]),read_only_roots=[],allowed_harness_entries=[dict(path='/harness/lore_session/node/entry.mts',sha256=sha((ROOT/'lore_session/node/entry.mts').read_bytes()),argv_modes=['--config'])],dynamic_reference_authorities=[dict(root=str(authority_root),identity='trusted-SessionPlans-owner',namespace=self.ns,allowed_kinds=['snapshot','readonly-view','owner-receipt','grant','storage-charge'],rule='immutable-full-ref-registration/v1')])
  save(plans/'X-config.json',config)
  model=dict(id='faux-1',name='Faux Model',api='faux',provider='faux',reasoning=False,input=['text','image'],cost=dict(input=0,output=0,cacheRead=0,cacheWrite=0),contextWindow=128000,maxTokens=16384)
  self.host=dict(principal=self.principal,namespace=self.ns,plan_root=str(plans/'generated'),event_input_root=str(self.event_root),state_root=str(state),trusted_config_ref=fact(plans/'X-config.json'),profile_ref=profile_ref,request_template_ref=fact(ROOT/'original-host/request-template.json'),deps_mount=deps,slot_ref=slot_ref,authority_root=str(authority_root),authorization=dict(owner='trusted-generated-input',namespace=self.ns),model=model)
  self.original_auth=self.peer.store.authorization_checker;self.original_ref=self.peer.store.reference_checker
  self.peer.store.authorization_checker=self.fauth;self.peer.store.reference_checker=self.fref
  self.plans=product(self.control,self.peer.store,self.snapshots,self.host,self.resolve,self.register)
  save(self.root/'original-inputs.json',dict(payload=self.payload,selector=self.selector,host=self.host,registrations=self.reg))
 def accept(self,id,payload,bind=True):
  from lore_events.input_files import packet,publish
  self.control.accept(self.principal,dict(id=id,namespace=self.ns,kind='invocation',payload=payload))
  if bind:
   selector=payload['input_binding'];span=dict(start_sequence=1,end_sequence=0,high_water=0,next_sequence=1)
   ref=publish(self.event_root,id,packet(id,selector,span,[],[]))
   self.control.bind_input(self.principal,id,selector,ref)
 def rref(self,ref,purpose,expected):
  if purpose=='receipt':
   stored=load(self.root/'R-receipts'/ref['request_id']);return stored==ref and all(ref.get(k)==v for k,v in expected.items())
  if purpose=='harness':return ref==self.H and bool(self.peer.read_F(ref))
  if purpose=='input':
   from lore_events.input_files import validate
   validate(ref,expected['binding'],self.event_root);return ref['id']==expected['invocation_id']
  return False
 def register(self,kind,ref,scope):
  need(scope['namespace']==self.ns,'register namespace')
  row=dict(kind=kind,ref=ref,registered_scope=scope);path=self.authority_root/(sha(raw(dict(kind=kind,ref=ref)))+'.json')
  if path.exists():need(load(path)==row,'registration changed')
  else:save(path,row)
  return fact(path)
 def fauth(self,ref,purpose,context):
  if ref==self.host['authorization']:
   if purpose=='read_reference':return context['reference'].get('owner')=='F'
   if purpose=='capture':return Path(context['binding']['path']).is_relative_to(Path(self.host['plan_root'])) and context['binding']['authorization']==ref
   if purpose=='materialize':return Path(context['target_path']).is_relative_to(Path(self.host['plan_root']))
   return False
  return self.original_auth(ref,purpose,context)
 def fref(self,ref,purpose,context):
  if purpose=='coordination':
   return context['binding']['authorization']==self.host['authorization'] and ref.get('owner')=='trusted-session-plans' and ref.get('invocation_id') in ('invocation-one','owner-recovery') and Path(context['binding']['path']).is_relative_to(Path(self.host['plan_root']))
  return self.original_ref(ref,purpose,context)
 def resolve(self,ref,purpose,expected):
  self.calls.append(dict(ref=copy.deepcopy(ref),purpose=purpose,expected=copy.deepcopy(expected)))
  row=expected['invocation'];need(row==self.control.query(self.principal,row['id']),'resolver original R row')
  if purpose=='session-source':
   facility=expected['facility'];need(ref==facility['receipt_ref'],'resolver full original R receipt');return dict(facility_id=facility['id'],confirmation_request_id=confirmation_id(facility['id']))
  if purpose=='session':
   need(ref==row['payload']['session_ref'],'original Session ref differs')
   if ref.get('confirmation_request_id') is not None:
    result=self.snapshots.query(ref['confirmation_request_id']);owner=load(result['owner_record_ref']['path']);return dict(scope=owner['scope'],confirmation_request_id=owner['confirmation_request_id'])
   return dict(scope={k:ref[k] for k in self.scope},confirmation_request_id=None)
  if purpose in ('harness','capability'):
   need(ref==row['payload'][purpose+'_ref'],'original accepted descriptor differs');return self.peer.read_F(ref)
  if purpose=='F-view':
   selected=self.views.get(sha(raw(ref)));need(selected is not None,'not original permitted F version');return copy.deepcopy(selected)
  if purpose=='source-result':
   need(ref==row['payload']['source_result_ref'],'source result changed');return b'' if ref is None else self.peer.read_F(ref)
  if purpose=='original-file':return self.peer.read_F(ref)
  raise AssertionError('unfixed resolver purpose '+purpose)
 def completed(self,node,action='accept',issued=False):
  # Explicit NoEngine facility fixture: real R/S file operations; synthetic X response/CID.
  from lore_session.execution import session_reference
  from lore_control.values import encode
  eid=execution_id(node['operation_id'],action);payload=dict(parent_id=node['operation_id'],action=action,execution_id=eid,node_request=dict(node,action=action))
  self.control.accept(self.principal,dict(id=eid,namespace=self.ns,kind='execution',payload=payload));self.control.mark_dispatched(self.principal,eid,'X')
  if issued:return None
  binding=dict(session_id=self.scope['session_id'],session_scope=self.scope,**{k:node[k] for k in ('operation_id','harness_ref','input_ref','source_result_ref','capability_ref')})
  metadata=dict(id=self.scope['session_id'],cwd='/work',path='/work/session.jsonl',createdAt='2026-01-01T00:00:00Z',storageVersion=4)
  header=dict(kind='header',v=4,**{k:v for k,v in metadata.items() if k!='path'})
  data=raw(header)+b'\n'+raw(dict(seq=1,kind='value',namespace='lore.s.binding',key=node['operation_id'],op='set',value=binding))+b'\n'
  archive=io.BytesIO()
  with tarfile.open(fileobj=archive,mode='w',format=tarfile.PAX_FORMAT) as out:
   for name,body in [('.',None),('session.jsonl',data),('metadata.json',raw(metadata))]:
    item=tarfile.TarInfo(name);item.uid=item.gid=1000;item.mode=0o700 if body is None else 0o600;item.mtime=0
    if body is None:item.type=tarfile.DIRTYPE;out.addfile(item)
    else:item.size=len(body);out.addfile(item,io.BytesIO(body))
  path=self.root/(eid+'.tar');path.write_bytes(archive.getvalue())
  original=dict(execution_id=eid,object_generation=1,request_digest=sha(raw(node)),container_id='fixture-cid-'+action,exec_id='fixture-exec-'+action,volume_id='fixture-volume-'+action,freeze_generation=1,state='FROZEN')
  cp=dict(owner='X',path=str(path),size=path.stat().st_size,sha256=sha(path.read_bytes()),**{k:original[k] for k in ('execution_id','object_generation','freeze_generation','state')},source_binding=dict(original,**self.scope))
  bundle=self.snapshots.confirm(confirmation_id(eid),dict(self.scope,original_execution=original),cp,dict(binding=binding,jsonl_relative_path='session.jsonl',metadata_relative_path='metadata.json',binding_namespace='lore.s.binding',binding_key=node['operation_id']))
  facility=dict(owner='X',kind='session_execution',execution_id=eid,confirmation_request_id=confirmation_id(eid),session_confirmation=bundle,original_execution_response=dict(binding=original,fixture='NoEngine release-shaped file'),original_stopped_response=dict(binding=original,fixture='NoEngine stop-shaped file'),node_request_digest=sha(raw(payload['node_request'])))
  rrow=self.control.query(self.principal,eid);rrequest={k:rrow[k] for k in ('principal','id','namespace','kind','payload')}
  receipt=dict(owner='X',kind='delivery_receipt',request_id=eid,namespace=self.ns,source=self.principal,delivery_owner='X',request_digest=sha(encode(rrequest).encode()),outcome='positive',definite=True,facility_ref=facility)
  save(self.root/'R-receipts'/eid,receipt);self.control.confirm_delivery(self.principal,eid,receipt)
  return bundle
 def plan(self,id='invocation-one',eid='execution-one'):return self.plans.prepare(self.principal,id,execution_id=eid)
 def verify(self,plan):
  from lore_execution.node_profile import NodeProfile
  from lore_execution.ordinary_sources import snapshot,document
  node=plan['node_request'];cfg=plan['node_config'];req=plan['request']
  need(req['execution_id']=='execution-one' and req['session_binding']==self.scope and req['source_result'] is None,'original X fields differ')
  need(node['operation_id']=='invocation-one' and node['source_result_ref'] is None,'original Node binding differs')
  need(cfg['harness_ref']==node['harness_ref'] and cfg['capability_ref']==node['capability_ref'] and cfg['input']['ref']==node['input_ref'],'compact configured sources differ')
  need(cfg['harness_ref']==dict(id=sha(raw(self.H)),sha256=self.H['sha256']) and cfg['capability_ref']==dict(id=sha(raw(self.cap)),sha256=self.cap['sha256']),'compact refs not exact original full descriptors')
  validator=NodeProfile(self.host['trusted_config_ref']['path'],self.host['trusted_config_ref']['sha256'],self.host['state_root']);checked=validator.prepare(req,plan['authority']);slot=validator.role_slot(req,plan['authority'])
  need(slot['role']=='session' and slot['slot_ref']==self.host['slot_ref'],'actual slot differs')
  need(len(checked['readonly_mounts'])==4 and checked['raw_archive']==Path(plan['snapshot_bundle']['snapshot_ref']['archive_path']).read_bytes(),'actual validator missing full four mounts/source')
  input_path=Path(next(x for x in req['readonly_mounts'] if x['role']=='input')['source']['path'])
  need(load(input_path/'node-config.json')==cfg,'actual F config bytes differ')
  for path in Path(self.surface['materialized']['path']).rglob('*'):
   if path.is_file():need((input_path/'surface'/path.relative_to(self.surface['materialized']['path'])).read_bytes()==path.read_bytes(),'missing actual Surface member')
  bound=self.control.query_input(self.principal,'invocation-one');source=Path(bound['input_ref']['path'])
  for name in ('events.jsonl','invocation.json','execution-targets.json','manifest.json'):need((input_path/name).read_bytes()==(source/name).read_bytes(),'E original file changed')
  need(req['budgets']==load(self.host['request_template_ref']['path'])['budgets'],'profile budgets changed')
  need(req['command_argv'][-3:]==['/harness/lore_session/node/entry.mts','--config','/input/node-config.json'],'Node entry differs')
  ctx=cfg['runtime_context'];row=self.control.query(self.principal,'invocation-one');expected_binding=dict(session_id=self.scope['session_id'],session_scope=self.scope,**{k:node[k] for k in ('operation_id','harness_ref','input_ref','source_result_ref','capability_ref')})
  need(ctx==dict(invocation={k:row[k] for k in ('id','principal','namespace','kind','payload')},node_binding=expected_binding,input=dict(selector=self.selector,range=load(source/'manifest.json')['range']),execution_id=execution_id('invocation-one','drive'),continuation_session_ref=dict(owner='S',kind='confirmation',confirmation_request_id=confirmation_id(execution_id('invocation-one','drive')),session_scope=self.scope)),'runtime context not exact original R/E binding/locator')

  need(not any(k in cfg['model'] for k in ('apiKey','key','token','auth','baseUrl')),'key/provider endpoint leaked')
  interop=self.root/'context-interop';interop.mkdir(exist_ok=True);save(interop/'input.json',dict(config=cfg,request=req))
  nodebin='/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node';loader='/path/to/loom/research/repos/pi/node_modules/tsx/dist/loader.mjs'
  command=[nodebin,'--import',loader,str(ROOT/'validation/session_plan_context_probe.mjs'),str(interop/'input.json'),str(interop/'result.json')]
  save(interop/'command.json',command);observed=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env=dict(PATH=str(Path(nodebin).parent)+':/usr/bin:/bin',LANG='C.UTF-8'))
  (interop/'stdout').write_bytes(observed.stdout);(interop/'stderr').write_bytes(observed.stderr)
  need(observed.returncode==0,'actual Runtime context interop rejected: '+observed.stderr.decode(errors='replace'))
  need(load(interop/'result.json')['status']=='PASS','actual Runtime context interop missing result')

  return dict(node=node,actual_checked_binding=checked['binding_extra'],actual_input_files={str(q.relative_to(input_path)):sha(q.read_bytes()) for q in input_path.rglob('*') if q.is_file()})
 def close(self):
  save(self.root/'resolver-calls.json',self.calls);(self.root/'R.sql').write_text('\n'.join(self.control.db.iterdump()));self.control.close()

def case(id,root,product):
 f=Fixture(root,product);out={}
 try:
  if id=='SP01':out=f.verify(f.plan())
  elif id=='SP02':
   f.accept('unbound',f.payload,False);out['unbound']=rejected(lambda:f.plan('unbound'))
   out['principal']=rejected(lambda:f.plans.prepare('other','invocation-one',execution_id='execution-one'))
   f.control.rebind(f.principal,'rebind',f.reg['surface']['id'],1,f.H);out['stale']=rejected(f.plan)
  elif id=='SP03':
   plan=f.plan();out['positive']=f.verify(plan)
   source=Path(f.workspace['materialized']['path']);source.rename(source.with_name('retained-original'));shutil.copytree(source.with_name('retained-original'),source)
   out['replaced_source']=rejected(f.plan)
  elif id=='SP04':
   plan=f.plan();out['empty']=f.verify(plan);owner=load(plan['snapshot_bundle']['owner_record_ref']['path'])
   payload=copy.deepcopy(f.payload);payload['session_ref']['confirmation_request_id']=owner['confirmation_request_id'];f.accept('owner-recovery',payload)
   restored=f.plan('owner-recovery','execution-recovery');need(restored['snapshot_bundle']==plan['snapshot_bundle'],'healthy original S owner changed');out['healthy']=restored['snapshot_bundle']
   from lore_session.execution import session_reference
   accepted=f.completed(plan['node_request']);drive=dict(plan['node_request'],action='drive',session_ref=session_reference(accepted))
   out['selected_accept']=f.plans.session(drive,execution_id=execution_id('invocation-one','drive'))['snapshot_bundle'];need(out['selected_accept']==accepted,'drive did not restore this operation acceptance')
   out['old_owner']=rejected(lambda:f.plans.session(dict(drive,session_ref=plan['node_request']['session_ref']),execution_id=execution_id('invocation-one','drive')))
   f.completed(drive,'drive',issued=True);out['issued_no_fallback']=rejected(lambda:f.plans.session(dict(drive,action='query'),execution_id='query-original'))
   current=f.completed(drive,'drive');query=dict(drive,action='query',session_ref=session_reference(current))
   need(f.plans.session(query,execution_id='query-original')['snapshot_bundle']==current,'query did not use confirmed current operation')
   out['old_accept_after_drive']=rejected(lambda:f.plans.session(dict(query,session_ref=session_reference(accepted)),execution_id='query-original'))

   archive=Path(plan['snapshot_bundle']['snapshot_ref']['archive_path']);original=archive.read_bytes()
   try:archive.write_bytes(original[:-1]+b'X');out['corrupt_owner']=rejected(lambda:f.plan('owner-recovery','execution-recovery'))
   finally:archive.write_bytes(original)
  elif id=='SP05':
   plan=f.plan();out['positive']=f.verify(plan);again=f.plan();need(again['request']==plan['request'] and again['authority']==plan['authority'],'same original plan changed')
   other=f.plan(eid='execution-other');need(other['node_request']==plan['node_request'],'same invocation Node binding changed with X execution ID')
   accepted=f.completed(plan['node_request'])
   from lore_session.execution import session_reference
   for action in ('accept','query','drive'):
    node=copy.deepcopy(plan['node_request']);node['action']=action
    if action!='accept':node['session_ref']=session_reference(accepted)
    actual=f.plans.session(node,execution_id='action-'+action);need(actual['node_config']['input']['ref']==plan['node_request']['input_ref'],'action changed original input binding')
   node=dict(plan['node_request'],session_ref=session_reference(accepted));read_ref=f.input_body['original_refs']['log']['source_ref'];read_node=dict(node,action='export_read',read_ref=read_ref)
   f.plans.session(read_node,execution_id='execution-one')
   descriptor=dict(path='/input/originals/log',bytes=len(b'original retained log\n'),sha256=sha(b'original retained log\n'))
   resolved=f.plans.resolve_read(read_ref,descriptor);need(Path(resolved['path']).read_bytes()==b'original retained log\n' and resolved['bytes']==descriptor['bytes'] and resolved['sha256']==descriptor['sha256'],'actual authorized export read differs')
   out['read_rejections']=[rejected(lambda:f.plans.resolve_read(read_ref,dict(descriptor,path='/etc/passwd'))),rejected(lambda:f.plans.resolve_read(read_ref,dict(descriptor,sha256='0'*64)))]
   bad=[]
   for key in ('harness_ref','input_ref','capability_ref'):
    item=copy.deepcopy(node);item[key]['sha256']='0'*64;bad.append(item)
   bad.extend([dict(node,operation_id='missing'),dict(node,source_result_ref={'owner':'made-up'}),dict(node,session_ref=dict(node['session_ref'],namespace='other')),dict(node,action='shell'),dict(node,action='export_read',read_ref={'path':'/etc/passwd'})])
   out['bad_bindings']=[rejected(lambda item=item:f.plans.session(item,execution_id='execution-one')) for item in bad]
  return out
 finally:f.close()

def main():
 a=argparse.ArgumentParser();a.add_argument('--batch',required=True);a.add_argument('--worker',action='store_true');a.add_argument('--bad',action='store_true');args=a.parse_args()
 if args.worker:
  batch=Path(args.batch)
  if args.bad:
   class product:
    def __init__(self,*a):pass
    def prepare(self,*a,**kw):return {'status':'PASS'}
  else:
   try:product=importlib.import_module('lore_runtime.session_plans').SessionPlans
   except ModuleNotFoundError:save(batch/'result.json',dict(status='MISSING',actual_runs=0));return 2
  rows=[]
  for id in IDS:
   try:rows.append(dict(id=id,status='PASS',result=case(id,batch/'actual'/id,product)))
   except BaseException as exc:rows.append(dict(id=id,status='FAIL',error=repr(exc),traceback=traceback.format_exc()))
   save(batch/'assessment.json',dict(cases=rows))
  result=dict(status='PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL',actual_runs=len(rows),candidate_source='explicit-always-green-control' if args.bad else importlib.import_module('lore_runtime.session_plans').__file__);save(batch/'result.json',result);return 0 if result['status']=='PASS' else 1
 batch=ROOT/'validation/session-plan-evidence'/args.batch;batch.mkdir(parents=True);work=batch/'workspace';work.mkdir()
 names=[]
 for package in ('lore_control','lore_files','lore_execution','lore_events'):
  names.extend(q.relative_to(ROOT) for q in (ROOT/package).iterdir() if q.is_file() and q.suffix in ('.py','.json'))
 names.extend(Path(n) for n in ['validation/session_plan_context_probe.mjs','harnesses/runtime/index.mts','design/g3/x-node-profile/profile.json','design/g3/x-node-profile/request-template.json','validation/components/x_node_profile/evidence/node-independent-full-001/actual/shared/dependencies-manifest.json','lore_session/snapshots.py','lore_session/snapshot_files.py','lore_session/execution.py','validation/components/s/f_peer.py','validation/session_plans_probe.py','design/g3/session-plans/contract.md'])
 for prefix,files in [('lore_session/node',['entry','adapter','session','callbacks','stdio','common']),('harnesses/minimal',['index','projection'])]:names.extend(Path(prefix)/(n+'.mts') for n in files)
 for n in ('session_plans.py','session_plan_files.py'):
  if (ROOT/'lore_runtime'/n).exists():names.append(Path('lore_runtime')/n)
 before={str(n):sha((ROOT/n).read_bytes()) for n in names}
 for n in names:(work/n).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,work/n)
 host=work/'original-host';host.mkdir()
 dp=work/'validation/components/x_node_profile/evidence/node-independent-full-001/actual/shared/dependencies-manifest.json'
 shutil.copy2(dp,host/'dependencies-manifest.json')
 for n in ('profile.json','request-template.json'):shutil.copy2(work/'design/g3/x-node-profile'/n,host/n)
 command=[sys.executable,'-B',str(work/'validation/session_plans_probe.py'),'--worker','--batch',str(batch)]+(['--bad'] if args.bad else [])
 save(batch/'source-before.json',before);save(batch/'command.json',dict(argv=command,cwd=str(work)))
 with (batch/'stdout').open('wb') as o,(batch/'stderr').open('wb') as e:r=subprocess.run(command,cwd=work,env=dict(os.environ,PYTHONPATH=str(work),PYTHONDONTWRITEBYTECODE='1'),stdout=o,stderr=e,timeout=180)
 after={str(n):sha((ROOT/n).read_bytes()) for n in names};copied={str(n):sha((work/n).read_bytes()) for n in names};result=load(batch/'result.json') if (batch/'result.json').exists() else dict(status='FAIL',actual_runs=0)
 result.update(exit_code=r.returncode,source_unchanged=before==after,copied_source=before==copied)
 if before!=after or before!=copied:result['status']='FAIL'
 save(batch/'result.json',result);print(json.dumps(result));return r.returncode if before==after==copied else 1
if __name__=='__main__':raise SystemExit(main())
