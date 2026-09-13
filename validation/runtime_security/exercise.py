"""One actual assembled M02 fixture. Called only by the explicitly admitted runner."""
import asyncio,copy,hashlib,json,os,time,traceback
from pathlib import Path
from urllib.parse import quote
from .fixtures import save,sha,raw
from .observations import files,original_state,engine_hook,events,tool_originals,EngineRead
from .attacks import note,trusted_ports,capture_emit,physical

def invocation(rt,sample):
    ns=sample['id'];refs=rt.initial_refs;registered={}
    for domain in ('surface','workspace'):
        registered[domain]=rt.register('operator',request_id=ns+'-register-'+domain,resource_id=ns+'-'+domain,
            namespace=ns,kind=domain,path=sample[domain],harness_ref=refs['harness_ref'],grants={'operator':['read','write']})
    selector=dict(namespace=ns,source='operator',start_sequence=1,filters={},page_size=16,
        surface_ref=refs['surface_ref'],previous_session_ref=refs['previous_session_ref'],execution_targets=refs['execution_targets'])
    return dict(id=ns+'-invocation',namespace=ns,kind='invocation',payload=dict(resource_id=ns+'-surface',
        resource_revision=registered['surface']['revision'],harness_ref=refs['harness_ref'],input_ref=None,input_binding=selector,
        **{k:refs[k] for k in ('session_ref','source_result_ref','capability_ref')}))

def cleanup(rt,config,out):
    # Post-assessment only; disappearance requires direct original-ID GET404.
    root=Path(config['runtime']['execution_dir']);owner=hashlib.sha256(str(root).encode()).hexdigest()
    bindings=[json.loads(p.read_bytes())['binding'] for p in root.glob('*/record.json')]
    known={b['execution_id'] for b in bindings};log=[];save(out/'cleanup-after-assessment.json',log)
    reader=EngineRead(config['runtime']['engine_endpoint'])
    def get(row,key,path):
        row[key+'_request']=dict(method='GET',path=path)
        try:row[key]=reader.get(path)
        except Exception as exc:
            row[key+'_error']=dict(type=type(exc).__name__,message=str(exc));save(out/'cleanup-after-assessment.json',log);raise
        save(out/'cleanup-after-assessment.json',log)
        if row[key]['status'] not in (200,404):raise AssertionError('non-200/404 cleanup observation')
        return row[key]
    filtered=dict(kind='original-slot-list');log.append(filtered)
    listed=get(filtered,'actual','/containers/json?all=true&filters='+quote(json.dumps({'label':['lore.x.slot_owner='+owner]})))
    if listed['status']!=200:raise AssertionError('original slot enumeration unavailable')
    ids={b['container_id'] for b in bindings if b.get('container_id')}
    for item in listed['body']:
        if item.get('Labels',{}).get('lore.x.slot_owner')!=owner or item.get('Labels',{}).get('lore.x.execution_id') not in known:raise AssertionError('cleanup scope differs')
        ids.add(item['Id'])
    for cid in sorted(ids):
        row=dict(kind='container',id=cid);log.append(row);actual=get(row,'original_GET','/containers/'+cid+'/json')
        if actual['status']==404:continue
        labels=actual['body'].get('Config',{}).get('Labels',{})
        if actual['body']['Id']!=cid or labels.get('lore.x.slot_owner')!=owner or labels.get('lore.x.execution_id') not in known:raise AssertionError('original container scope differs')
        row['original_labels']=labels;rt.execution.engine.call('DELETE','/containers/'+cid+'?force=1',missing=True)
        if get(row,'after_GET','/containers/'+cid+'/json')['status']!=404:raise AssertionError('original container remains after cleanup')
    for b in bindings:
        volume=b.get('volume_id')
        if not volume:continue
        row=dict(kind='volume',id=volume,execution_id=b['execution_id']);log.append(row);actual=get(row,'original_GET','/volumes/'+volume)
        if actual['status']==404:continue
        if actual['body'].get('Labels',{}).get('lore.x.execution_id')!=b['execution_id']:raise AssertionError('original volume scope differs')
        rt.execution.engine.call('DELETE','/volumes/'+volume,missing=True)
        if get(row,'after_GET','/volumes/'+volume)['status']!=404:raise AssertionError('original volume remains after cleanup')
    save(out/'cleanup-after-assessment.json',log)


async def one(sample):
    # Existing servers, actual assembly and independent source readers; no alternate owners.
    from validation.system.m01_run import configuration
    from validation.components.e.support import Server
    from validation.session_service.live import HTTPFixture
    from lore_runtime.bootstrap import assemble
    out=Path(sample['out']);checks=[];seen=[];rt=http=None;server=Server(out/'nats');fd=None
    old_env=os.environ.get('LORE_M02_CANARY');result=dict(id=sample['id'],family=sample['family'],repeat=sample['repeat'],status='FAIL',checks=checks)
    protected=files(Path(sample['private']));source=Path(sample['canary']).stat()
    result['protected_before']=dict(files=protected,canary_inode=[source.st_dev,source.st_ino])
    try:
        responses=[p.read_bytes() for p in sorted(out.glob('response-*.body'))]
        http=HTTPFixture(out/'http',responses)
        config=configuration(sample,server.url,http.endpoint);save(out/'config.json',config)
        await server.start();rt=assemble(config,credential_provider=None)
        trusted_ref=copy.deepcopy(rt.startup.config_ref);save(out/'trusted-config-original.json',trusted_ref)
        rt.execution.checkpoint_hook=engine_hook(config,out,seen)
        await rt.open();request=invocation(rt,sample);save(out/'invocation-original.json',request)
        initial=original_state(config);save(out/'original-owners-before.json',initial)
        if sample['family'] in ('target','identity'):
            await trusted_ports(rt,sample,config,request,checks)
            note(checks,'no actual X dispatch',not seen and not list(Path(config['runtime']['execution_dir']).glob('*/record.json')))
            note(checks,'no HTTP at trusted denial boundary',len(http.records)==0 and not http.errors)
            _,residual=tool_originals(config,out,seen)
            note(checks,'no original slot objects at trusted denial boundary',not residual)
        else:
            emit_calls=capture_emit(rt,out) if sample['family']=='event' else []
            if sample['family']=='event':
                result['same_name_positive_reply']=await rt.events.submit('operator',sample['id']+'-positive',sample['id'],'surface.registered',{'ordinary_data':True})
            if sample['family']=='fd':
                fd=os.open(sample['canary'],os.O_RDONLY);os.set_inheritable(fd,True)
                os.environ['LORE_M02_CANARY']=Path(sample['canary']).read_text()
                save(out/'host-inheritable-descriptor.json',dict(pid=os.getpid(),fd=fd,inheritable=os.get_inheritable(fd),canary_sha256=sha(sample['canary'])))
            deadline=time.monotonic()+300;result['accepted']=rt.start('operator',request)
            result['drive']=await asyncio.wait_for(rt.drive_until('operator',request['id'],deadline_monotonic=deadline),300)
            result['elapsed_seconds']=300-(deadline-time.monotonic())
            before_query=original_state(config);calls_before=len(http.records)
            result['query']=rt.query('operator',request['id'])
            note(checks,'query writes neither R/X nor HTTP',before_query==original_state(config) and calls_before==len(http.records))
            tools,residual=tool_originals(config,out,seen);public=await events(config);save(out/'original-NATS-messages.json',public)
            state=original_state(config);save(out/'original-owners-after.json',state)
            physical(sample,config,checks,tools,public,state['R'],http,emit_calls)
            note(checks,'actual containers and volumes absent before cleanup',not residual)
            note(checks,'original 300 second fixture bound',result['elapsed_seconds']<=300)
        after=Path(sample['canary']).stat()
        note(checks,'protected host files and identity unchanged',files(Path(sample['private']))==protected and [after.st_dev,after.st_ino]==[source.st_dev,source.st_ino])
        note(checks,'trusted control configuration bytes unchanged',sha(trusted_ref['path'])==trusted_ref['sha256'])
        state=original_state(config)
        expected={sample['id']+'-'+d for d in ('surface','workspace')}
        note(checks,'R original resources and grants unchanged',{q['id'] for q in state['R']['resources']}==expected and all(q['namespace']==sample['id'] and q['grants']=={'operator':['read','write']} and q['active']==1 for q in state['R']['resources']))
        result['status']='PASS' if checks and all(c['passed'] for c in checks) else 'FAIL'
    except Exception as exc:
        result['error']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc());result['status']='FAIL'
    finally:
        if fd is not None:os.close(fd)
        if old_env is None:os.environ.pop('LORE_M02_CANARY',None)
        else:os.environ['LORE_M02_CANARY']=old_env
        save(out/'assessment-before-cleanup.json',result)
        if rt is not None:
            try:cleanup(rt,config,out)
            except Exception as exc:result['cleanup_error']=repr(exc);result['status']='FAIL'
            try:await rt.close()
            except Exception as exc:result['close_error']=repr(exc);result['status']='FAIL'
        if http is not None:
            try:http.close()
            except Exception as exc:result['HTTP_close_error']=repr(exc);result['status']='FAIL'
        server.close();result['NATS_reaped']=server.proc is None or server.proc.poll() is not None
        if not result['NATS_reaped']:result['status']='FAIL'
        save(out/'result.json',result)
    return result
