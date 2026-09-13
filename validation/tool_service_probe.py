"""Original ToolPlans/ToolService finite entry. Engine work requires --engine explicitly."""
import argparse,base64,copy,hashlib,importlib,io,json,os,shutil,subprocess,sys,tarfile,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validation.session_plans_probe import Fixture,raw,sha,load,save,fact,identity,need,execution_id
def rejected(fn):
    try:fn()
    except Exception as e:
        if getattr(e,"code",None) in {"reference_invalid","denied","stale","not_found","input_invalid","invalid_snapshot","conflict","UNAUTHORIZED","INVALID_REQUEST","VERSION_CORRUPT","STALE_BINDING","invalid_frame","unauthorized_target","invalid_request"}:return dict(code=e.code,error=str(e))
        raise
    raise AssertionError("invalid input accepted")
NO_ENGINE=['TP01','TP02','TP03'];ENGINE=['TS04','TS05','TS06']

class BoundaryReached(RuntimeError):pass
class NoEngine:
    calls=[]
    def __init__(self,*a,**kw):pass
    def call(self,*a,**kw):self.calls.append([a,kw]);raise AssertionError('Engine forbidden in NoEngine group')

class ToolFixture:
    def __init__(self,root,ToolPlans,ToolService):
        from lore_runtime.session_plans import SessionPlans
        from lore_runtime.file_publication import FilePublication
        self.f=Fixture(root,SessionPlans);self.root=Path(root);self.plans=ToolPlans(self.f.plans,self.f.snapshots)
        self.ToolService=ToolService;self.execution=None
        old=self.f.control.reference_checker
        def refs(ref,purpose,expected):
            if purpose=='base':
                self.f.peer.store.versions.load(ref);return ref['resource_id']==expected['resource_id']
            if purpose=='receipt' and hasattr(self,'service'):return self.service.control_reference(ref,purpose,expected)
            if hasattr(self,'publication') and self.publication.control_reference(ref,purpose,expected):return True
            return old(ref,purpose,expected)
        self.f.control.reference_checker=refs
    def pending(self,target='runtime',script="printf 'changed\n' > tool.txt; printf 'tool-original\n'",parent='invocation-one'):
        from lore_session.execution import session_reference
        plan=self.f.plans.prepare(self.f.principal,parent,execution_id=execution_id(parent,'accept'));node=plan['node_request']
        binding=dict(session_id=self.f.scope['session_id'],session_scope=self.f.scope,**{k:node[k] for k in ('operation_id','harness_ref','input_ref','source_result_ref','capability_ref')})
        reserved='reserved-tool-1';frame=dict(type='tool.request',session_id=binding['session_id'],operation_id=parent,effect_id='s-tool-'+sha(raw([self.f.scope,parent,reserved])),invocation_id=reserved,source_result_ref=binding['source_result_ref'],request=dict(target=target,script=script))
        metadata=dict(id=self.f.scope['session_id'],cwd='/work',path='/work/session.jsonl',createdAt='2026-01-01T00:00:00Z',storageVersion=4)
        header=dict(kind='header',v=4,**{k:v for k,v in metadata.items() if k!='path'})
        values=[('lore.s.binding',parent,binding),('pi.op.meta',parent,dict(operationId=parent,lane='main')),('pi.lane.state','main',dict(currentOperationId=parent)),('pi.op.state',parent,dict(at='tools',batch=dict(calls=[dict(status='effect_pending',resultEntryId=reserved,sourceIndex=0)],assistantEntryId='assistant-one',turnId='turn-one'))),('pi.op.tool_args',parent+':turn-one:0',frame['request'])]
        rows=[dict(seq=i+1,kind='value',namespace=ns,key=key,op='set',value=value) for i,(ns,key,value) in enumerate(values)]
        rows.append(dict(seq=len(rows)+1,kind='entry',id='assistant-one',parentId=None,message=dict(role='assistant',stopReason='toolUse',content=[dict(type='toolCall',id='native-tool-one',name='shell',arguments=frame['request'])])))
        data=raw(header)+b'\n'+b''.join(raw(row)+b'\n' for row in rows)
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w',format=tarfile.PAX_FORMAT) as out:
            for name,body in [('.',None),('session.jsonl',data),('metadata.json',raw(metadata))]:
                item=tarfile.TarInfo(name);item.uid=item.gid=1000;item.mode=0o700 if body is None else 0o600;item.mtime=0
                if body is None:item.type=tarfile.DIRTYPE;out.addfile(item)
                else:item.size=len(body);out.addfile(item,io.BytesIO(body))
        path=self.root/('pending-'+parent+'.tar');path.write_bytes(archive.getvalue())
        original=dict(execution_id='fixture-S-'+parent,object_generation=1,request_digest=sha(raw(binding)),container_id='fixture-noengine-CID',exec_id='fixture-noengine-exec',volume_id='fixture-noengine-volume',freeze_generation=1,state='FROZEN')
        cp=dict(owner='X',path=str(path),size=path.stat().st_size,sha256=sha(path.read_bytes()),**{k:original[k] for k in ('execution_id','object_generation','freeze_generation','state')},source_binding=dict(original,**self.f.scope))
        bundle=self.f.snapshots.confirm('pending-'+parent,dict(self.f.scope,original_execution=original),cp,dict(binding=binding,jsonl_relative_path='session.jsonl',metadata_relative_path='metadata.json',binding_namespace='lore.s.binding',binding_key=parent))
        save(self.root/('original-pending-'+parent+'.json'),dict(scope='FINITE_S_FORMAT_AND_X_SHAPED_OWNER_FIXTURE_NO_NODE_EXECUTION',binding=binding,frame=frame,confirmation=bundle))
        return binding,frame,session_reference(bundle)
    def service_with(self,no_engine=False):
        from lore_execution import ExecutionStore
        from lore_runtime.file_publication import FilePublication
        def cut(label,binding):
            if label=='slot_reserved_before_engine_create':
                save(self.root/'actual-precreate.json',binding);raise BoundaryReached(label)
        host=self.f.host
        if no_engine:
            self.engine_patch=patch('lore_execution.store.Engine',NoEngine);self.engine_patch.start();NoEngine.calls=[]
        self.execution=ExecutionStore(host['state_root'],checkpoint=cut if no_engine else None,trusted_config=host['trusted_config_ref']['path'],trusted_config_sha256=host['trusted_config_ref']['sha256'])
        self.publication=FilePublication(self.f.control,self.f.peer.store,self.stopped)
        self.service=self.ToolService(self.f.control,self.f.peer.store,self.execution,self.publication,self.plans,self.stopped)
        old_auth=self.f.peer.store.authorization_checker;old_ref=self.f.peer.store.reference_checker
        self.f.peer.store.authorization_checker=lambda ref,purpose,context:self.service.file_authorization(ref,purpose,context) or old_auth(ref,purpose,context)
        self.f.peer.store.reference_checker=lambda ref,purpose,context:self.service.file_reference(ref,purpose,context) or self.publication.file_reference(ref,purpose,context) or old_ref(ref,purpose,context)
        return self.service
    def stopped(self,ref,purpose,scope):
        return self.service.validate_stopped(ref,purpose,scope)
    def close(self):
        if self.execution:self.execution.journal.close()
        if hasattr(self,'engine_patch'):self.engine_patch.stop()
        self.f.close()

def no_engine_case(id,root,ToolPlans,ToolService):
    f=ToolFixture(root,ToolPlans,ToolService)
    try:
        binding,frame,original=f.pending();plan=f.plans.prepare(binding,frame,original)
        if id=='TP01':
            from lore_execution.requests import validate
            from lore_execution.node_profile import NodeProfile
            result=[]
            for target in ['runtime','workspace']:
                if target!='runtime':
                    f.f.accept('owner-recovery',f.f.payload)
                    binding,frame,original=f.pending(target=target,parent='owner-recovery')
                plan=f.plans.prepare(binding,frame,original);r=plan['request'];a=plan['authority']
                need(base64.b64decode(r['script_base64']).decode()==frame['request']['script'],'script rewritten')
                need(r['domain']==('runtime' if target=='runtime' else 'task') and r['budgets']['cpu']==.25,'target/budget differs')
                checked=validate(r,a,f.f.host['state_root'])
                source_plan=f.f.plans.prepare(f.f.principal,binding['operation_id'],execution_id=execution_id(binding['operation_id'],'accept'))
                input_mount=[m for m in source_plan['request']['readonly_mounts'] if m['role']=='input']
                need(len(input_mount)==1,'accepted Session input ambiguous')
                need(r.get('readonly_mounts')==input_mount if target=='runtime' else 'readonly_mounts' not in r,'ordinary tool lost exact authorized history input or added it to workspace')
                rejected(lambda: f.plans.grant(plan))
                accepted=dict(id=frame['effect_id'],namespace=f.f.ns,kind='execution',payload=dict(parent_id=binding['operation_id'],binding=binding,frame=frame,original_session_snapshot_ref=original,plan=plan))
                f.f.control.accept(f.f.principal,accepted)
                f.f.control.acquire(plan['resource']['id'],frame['effect_id'],plan['base_ref'])
                role=f.plans.grant(plan);need(role['role']=='tool' and role['slot_ref']==a['slot_ref'],'real shared tool grant differs')
                if target=='runtime':
                    validator=NodeProfile(f.f.host['trusted_config_ref']['path'],f.f.host['trusted_config_ref']['sha256'],f.f.host['state_root'])
                    checked_input=validator.runtime_input(r,a)
                    save(Path(root)/'original-runtime-input.json',dict(accepted_input=input_mount,request=r,authority=a,validated=checked_input))
                result.append({k:(dict(bytes=len(v),sha256=sha(v)) if isinstance(v,bytes) else v) for k,v in checked.items()})
            return result
        if id=='TP02':
            bad=[]
            for key,value in [('effect_id','wrong-effect'),('invocation_id','wrong-slot'),('source_result_ref',{'owner':'wrong'})]:
                bad.append(rejected(lambda key=key,value=value:f.plans.prepare(binding,dict(frame,**{key:value}),original)))
            for request in [dict(target='session',script='true'),dict(frame['request'],script='different script')]:bad.append(rejected(lambda request=request:f.plans.prepare(binding,dict(frame,request=request),original)))
            need(f.f.control.db.execute("SELECT count(*) FROM requests WHERE kind='execution'").fetchone()[0]==0,'invalid request reached facility')
            return bad
        service=f.service_with(no_engine=True)
        mark=f.f.control.mark_dispatched
        def before_X(*args):
            value=mark(*args)
            tree_before={str(p.relative_to(f.execution.journal.root)):p.read_bytes() for p in f.execution.journal.root.rglob('*') if p.is_file()}
            dirs_before={str(p.relative_to(f.execution.journal.root)) for p in f.execution.journal.root.rglob('*') if p.is_dir()}
            need(service.query(frame['effect_id'],binding)['status']=='UNKNOWN','R accepted but absent X became positive')
            need(tree_before=={str(p.relative_to(f.execution.journal.root)):p.read_bytes() for p in f.execution.journal.root.rglob('*') if p.is_file()} and dirs_before=={str(p.relative_to(f.execution.journal.root)) for p in f.execution.journal.root.rglob('*') if p.is_dir()},'read query created original X state')
            return value
        f.f.control.mark_dispatched=before_X
        result=service.execute(binding,frame,original)
        need(result['status']=='UNKNOWN','precreate cut became positive receipt')
        row=f.f.control.query(f.f.principal,frame['effect_id']);record=f.execution.journal.get(frame['effect_id'])
        need(row['phase']=='issued' and row['receipt_ref'] is None,'original R responsibility lost')
        need(record['issued'] is False and record['result']['execution_state']=='NOT_STARTED' and 'container_id' not in record['binding'],'not original precreate X acceptance')
        before=raw(record);sql='\n'.join(f.f.control.db.iterdump())
        observed=service.query(frame['effect_id'],binding)
        need(observed['status']=='UNKNOWN' and raw(f.execution.journal.get(frame['effect_id']))==before and '\n'.join(f.f.control.db.iterdump())==sql,'query modified original state')
        again=service.execute(binding,frame,original);need(again['status']=='UNKNOWN' and NoEngine.calls==[],'unknown execution redispatched')
        # Exact S callback interoperation; fixture reply only, not an unrun tool success.
        from types import SimpleNamespace
        from lore_session.service import _Invocation
        wire=[];artifact=f.execution.journal.blob(frame['effect_id'],'transport-stdout-fixture',b'ordinary stdout\n')
        stdout=service.stdout_reference(artifact)
        reply=dict(status='RECEIVED',fresh=True,result_ref={'scope':'transport-fixture-only'},stdout_ref=stdout,publication_ref={'scope':'transport-fixture-only'})
        invocation=object.__new__(_Invocation)
        invocation.service=SimpleNamespace(snapshots=f.f.snapshots,tools=SimpleNamespace(execute=lambda *a:reply))
        invocation.request={'action':'drive'};invocation.binding=binding;invocation.counts={'provider':0,'tool':0};invocation.evidence={}
        invocation.save=lambda label:dict(original_session_snapshot_ref=original);invocation.hook=lambda *a:None;invocation.resume=lambda:None
        invocation.channel=SimpleNamespace(write=wire.append)
        invocation.callback(frame)
        need(base64.b64decode(wire[0]['stdout']['data_b64'])==b'ordinary stdout\n' and wire[0]['result_ref']==reply['result_ref'] and wire[0]['publication_ref']==reply['publication_ref'],'actual S callback changed original tool refs/bytes')
        save(Path(root)/'actual-S-callback.json',dict(scope='actual S callback, actual X blob, controlled reply only; no tool execution',original_X_stdout=artifact,projected=stdout,wire=wire))
        save(Path(root)/'actual-X-accepted.json',record)
        return dict(original_R=row,original_X=record,result=result,query=observed,again=again,engine_calls=NoEngine.calls)
    finally:f.close()

def engine_case(id,root,ToolPlans,ToolService):
    f=ToolFixture(root,ToolPlans,ToolService)
    try:
        target='workspace' if id=='TS05' else 'runtime'
        binding,frame,original=f.pending(target=target)
        service=f.service_with();plan=f.plans.prepare(binding,frame,original)
        source=Path(plan['resource']['path']);before={p.relative_to(source).as_posix():sha(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
        exchanges=[];old_hook=f.f.peer.store.checkpoint
        def hook(label,record):
            old_hook(label,record)
            if label=='after_exchange_before_record':
                exchanges.append(record)
                if id=='TS06' and len(exchanges)==1:raise BoundaryReached('actual F exchange before original confirmation')
        f.f.peer.store.checkpoint=hook
        first=service.execute(binding,frame,original)
        save(Path(root)/'original-first-response.json',first)
        if id=='TS06':
            need(first['status']=='UNKNOWN' and len(exchanges)==1,'actual installation cut absent')
            raw_before=raw(f.execution.journal.get(frame['effect_id']));sql='\n'.join(f.f.control.db.iterdump())
            need(service.query(frame['effect_id'],binding)['status']=='UNKNOWN','query completed installation')
            need(raw_before==raw(f.execution.journal.get(frame['effect_id'])) and sql=='\n'.join(f.f.control.db.iterdump()),'query mutated cut state')
            result=service.reconcile(frame['effect_id'],binding)
            save(Path(root)/'original-reconcile-response.json',result)
        else:result=first
        need(result['status']=='RECEIVED' and len(exchanges)==1,'original tool publication incomplete/repeated')
        pub=result['publication_ref'];version=pub['F_query']['version_ref'];cp=f.execution.journal.get(frame['effect_id'])['checkpoints']['s-tool-final']['artifact']
        need(f.f.peer.store.versions.load(version)[0]==Path(cp['path']).read_bytes(),'F version did not retain original X archive bytes')
        need((source/'tool.txt').read_bytes()==b'changed\n','actual published file differs')
        need(all(sha((source/name).read_bytes())==value for name,value in before.items()),'untouched original file lost')
        stdout=Path(result['stdout_ref']['path']).read_bytes();need(len(stdout)==result['stdout_ref']['bytes'] and sha(stdout)==result['stdout_ref']['sha256'],'stdout projection invalid');need(stdout==b'tool-original\n','original stdout differs')
        record=f.execution.journal.get(frame['effect_id']);need(record.get('released') is True,'original X release missing')
        need(f.execution.engine.inspect(record['binding']['container_id']) is None,'original container remains')
        need(f.execution.engine.call('GET','/volumes/'+record['binding']['volume_id'],missing=True) is None,'original volume remains')
        sql='\n'.join(f.f.control.db.iterdump());rec=raw(record)
        queried=service.query(frame['effect_id'],binding)
        need(queried['result_ref']==result['result_ref'] and queried['publication_ref']==pub,'query altered original refs')
        need(service.validate_publication(pub,binding)==pub,'original publication not independently readable')
        need(sql=='\n'.join(f.f.control.db.iterdump()) and rec==raw(f.execution.journal.get(frame['effect_id'])),'confirmed query changed original owners')
        need(service.execute(binding,frame,original)['publication_ref']==pub and len(exchanges)==1,'duplicate tool replayed')
        release=load(Path(plan['directory'])/'original-X-released.json')
        slot=load(release['artifacts']['slot']['path']);reserved=slot['reservations'][record['binding']['slot_reservation_id']]
        directory=f.execution.journal.root/sha(frame['effect_id'].encode());seen={}
        for p in [directory,*directory.rglob('*')]:
            st=p.lstat();seen[st.st_dev,st.st_ino]=st.st_blocks*512
        for fd in Path('/proc/self/fd').iterdir():
            try:
                name=os.readlink(fd)
                if name.startswith(str(directory)+'/') and name.endswith(' (deleted)'):
                    st=fd.stat();seen[st.st_dev,st.st_ino]=st.st_blocks*512
            except FileNotFoundError:pass
        debt=reserved['retained_spool']
        need(reserved['state']=='RELEASED' and all(reserved[k]==record['binding'][k] for k in ('execution_id','object_generation','request_digest')),'retired reservation association differs')
        need(debt['root']==identity(directory) and debt['allocated_bytes']>=sum(seen.values())>0 and debt['inodes']>=len(seen)>0,'original retained bytes/inodes not charged')
        save(Path(root)/'actual-retained-spool.json',dict(reservation=reserved,actual=dict(allocated_bytes=sum(seen.values()),inodes=len(seen))))
        if id=='TS06':
            # A later explicit accepted parent names the actual newly installed version/revision.
            bundle=f.f.peer.store.journal.get('tool-import-'+frame['effect_id'])['result']
            updated=dict(bundle=bundle,materialized=dict(path=pub['registration']['path'],root=pub['F_query']['current_root'],version_ref=version))
            f.f.views[sha(raw(version))]=updated
            payload=copy.deepcopy(f.f.payload);payload['resource_revision']=pub['registration']['revision']
            payload['input_binding']['surface_ref']=version
            for t in payload['input_binding']['execution_targets']:
                if t['resource_id']==version['resource_id']:t['version_ref']=version
            f.f.accept('owner-recovery',payload)
            b2,fr2,o2=f.pending(parent='owner-recovery',script="printf 'later\\n' > later.txt")
            second=service.execute(b2,fr2,o2);need(second['status']=='RECEIVED','next same-slot explicit tool failed')
            need(service.validate_publication(pub,binding)==pub and Path(cp['path']).read_bytes()==f.f.peer.store.versions.load(version)[0],'later legitimate installation invalidated old original publication')
            second_release=load(Path(f.plans.host['plan_root'])/('tool-'+sha(fr2['effect_id'].encode()))/'original-X-released.json')
            new_slot=load(second_release['artifacts']['slot']['path'])
            need(new_slot['reservations'][record['binding']['slot_reservation_id']]['retained_spool']['allocated_bytes']>=debt['allocated_bytes'],'next tool erased old archive debt')
            save(Path(root)/'later-original-publication.json',second)
        for key in ['object_generation','request_digest']:
            bad=copy.deepcopy(pub);bad['R_intent']['staged_ref']['publication']['stopped_ref'][key]='wrong'
            rejected(lambda bad=bad:service.validate_publication(bad,binding))
        return dict(first=first,result=result,query=queried,actual_X=record,archive=fact(cp['path']),exchange_count=len(exchanges))
    finally:
        # Preserve failures and remove only this fixture's original identities. No inventory-difference cleanup.
        if f.execution:
            for path in f.execution.journal.root.glob('*/record.json'):
                record=load(path);b=record.get('binding',{})
                if b.get('container_id'):
                    f.execution.engine.call('DELETE','/containers/'+b['container_id']+'?force=1',missing=True)
                    need(f.execution.engine.inspect(b['container_id']) is None,'cleanup original CID remains')
                if b.get('volume_id'):
                    f.execution.engine.call('DELETE','/volumes/'+b['volume_id'],missing=True)
                    need(f.execution.engine.call('GET','/volumes/'+b['volume_id'],missing=True) is None,'cleanup original volume remains')
        f.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--worker',action='store_true');p.add_argument('--engine',action='store_true');a=p.parse_args()
    if a.worker:
        out=Path(a.batch)
        try:
            ToolPlans=importlib.import_module('lore_runtime.tool_plans').ToolPlans;ToolService=importlib.import_module('lore_runtime.tool_service').ToolService
        except ModuleNotFoundError:save(out/'result.json',dict(status='MISSING',actual_runs=0));return 2
        # Physical groups retain their original criteria and require an explicitly scheduled Engine window.
        rows=[]
        for id in (ENGINE if a.engine else NO_ENGINE):
            try:rows.append(dict(id=id,status='PASS',result=(engine_case if a.engine else no_engine_case)(id,out/'actual'/id,ToolPlans,ToolService)))
            except BaseException as e:rows.append(dict(id=id,status='FAIL',error=repr(e),traceback=traceback.format_exc()))
            save(out/'assessment.json',dict(cases=rows))
        status=('PASS_ENGINE_TOOL_SEAM_ONLY' if a.engine else 'PASS_NOENGINE_ONLY') if all(x['status']=='PASS' for x in rows) else 'FAIL'
        save(out/'result.json',dict(status=status,actual_runs=len(rows)));return 0 if status!='FAIL' else 1
    out=ROOT/'validation/tool-service-evidence'/a.batch;out.mkdir(parents=True);work=out/'workspace';work.mkdir()
    names=[]
    for package in ['lore_control','lore_files','lore_execution','lore_events','lore_runtime','lore_session']:
        names += [q.relative_to(ROOT) for q in (ROOT/package).glob('*') if q.is_file() and q.suffix in ('.py','.json')]
    names += [Path(n) for n in ['validation/session_plans_probe.py','validation/tool_service_probe.py','validation/session_plan_context_probe.mjs','validation/components/s/f_peer.py','design/g3/tool-service/contract.md','harnesses/runtime/index.mts']]
    for prefix,files in [('lore_session/node',['entry','adapter','session','callbacks','stdio','common']),('harnesses/minimal',['index','projection'])]:names += [Path(prefix)/(n+'.mts') for n in files]
    host_sources=[Path('design/g3/x-node-profile')/n for n in ('profile.json','request-template.json')]+[Path('validation/components/x_node_profile/evidence/node-independent-full-001/actual/shared/dependencies-manifest.json')]
    names += host_sources;before={str(n):sha((ROOT/n).read_bytes()) for n in names}
    for n in names:(work/n).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,work/n)
    host=work/'original-host';host.mkdir()
    for n in host_sources:shutil.copy2(work/n,host/n.name)
    command=[sys.executable,'-B',str(work/'validation/tool_service_probe.py'),'--worker','--batch',str(out)]+(['--engine'] if a.engine else [])
    save(out/'source-before.json',before);save(out/'command.json',dict(argv=command,cwd=str(work)))
    with (out/'stdout').open('wb') as o,(out/'stderr').open('wb') as e:r=subprocess.run(command,cwd=work,env=dict(os.environ,PYTHONPATH=str(work),PYTHONDONTWRITEBYTECODE='1'),stdout=o,stderr=e,timeout=300)
    result=load(out/'result.json') if (out/'result.json').exists() else dict(status='FAIL',actual_runs=0)
    result.update(exit_code=r.returncode,source_unchanged=before=={str(n):sha((ROOT/n).read_bytes()) for n in names},copied_source=before=={str(n):sha((work/n).read_bytes()) for n in names})
    save(out/'result.json',result);print(json.dumps(result));return r.returncode if result['source_unchanged'] and result['copied_source'] else 1
if __name__=='__main__':raise SystemExit(main())
