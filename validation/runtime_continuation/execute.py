"""Only the three original M04 sequences; no Engine work during import/preparation."""
import asyncio,hashlib,json,os,subprocess,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace
from validation.runtime_recovery.execute import wait_cut,finish
from validation.runtime_recovery.fixtures import durable,ROOT
from validation.runtime_security.exercise import cleanup
from validation.runtime_security.fixtures import save
from .facts import snapshot,parent,saved,absent,assess

def launch(sample,config,mode,out):
    out.mkdir();stdout=(out/'stdout.txt').open('wb');stderr=(out/'stderr.txt').open('wb')
    argv=[sys.executable,'-B',str(ROOT/'validation/runtime_continuation/worker.py'),'--fixture',str(Path(sample['out'])/'fixture.json'),'--config',str(config),'--mode',mode,'--out',str(out)]
    p=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,start_new_session=True,close_fds=True)
    save(out/'process.json',dict(argv=argv,pid=p.pid,pgid=os.getpgid(p.pid),started=time.monotonic()));return p,stdout,stderr

def dispatch(out):return json.loads((out/'actual-Engine-at-dispatch.json').read_bytes())

async def one(sample):
    from validation.components.e.support import Server
    from validation.session_service.live import HTTPFixture
    from validation.system.m01_run import configuration
    from lore_execution.engine import Engine
    from lore_runtime.session_delivery import execution_id
    out=Path(sample['out']);server=Server(out/'nats');http=None;config=None;result=dict(id=sample['id'],status='FAIL',checks=[])
    deadline=time.monotonic()+180;rid=sample['id']+'-invocation'
    try:
        http=HTTPFixture(out/'http',[(out/'response.body').read_bytes()]);config=configuration(sample,server.url,http.endpoint);cfg=out/'config.json';durable(cfg,config);await server.start()
        initial=out/'initial';killed=await asyncio.to_thread(wait_cut,launch(sample,cfg,'initial',initial),initial,deadline-70)
        before=snapshot(config,sample,http,out/'before-query')
        if not absent(before):raise AssertionError('original objects not released before new Runtime; do not test-cleanup into success')
        original=parent(before,rid);source=original['result_ref']
        facility=next(row for row in before['state']['R']['requests'] if row['id']==execution_id(rid,'drive'))
        bundle=facility['receipt_ref']['facility_ref']['session_confirmation'];old_pi=saved(config,bundle,source,out/'original-Pi')
        if original['phase']!='decide' or set(old_pi['boundary']['decision_proposal']['control']['body'])!={'stop_ref'}:raise AssertionError('original saved final/stop boundary not reached')
        qdir=out/'query';read=await asyncio.to_thread(finish,launch(sample,cfg,'query',qdir),qdir,min(30,deadline-time.monotonic()));after_read=snapshot(config,sample,http,out/'after-query')
        sdir=out/'session-query';node=await asyncio.to_thread(finish,launch(sample,cfg,'session_query',sdir),sdir,min(65,deadline-time.monotonic()));after_node=snapshot(config,sample,http,out/'after-session-query')
        envelope=node['evidence']['original_session_snapshot_ref'];new_bundle={k:envelope[k] for k in ('snapshot_ref','owner_record_ref','storage_charge_ref')}
        new_pi=saved(config,new_bundle,source,out/'restored-Pi')
        lease=parent(after_node,rid)['lease_until'];now=time.monotonic()
        if type(lease) not in (int,float) or lease>deadline-35:raise AssertionError('original finite lease missing/outside deadline')
        await asyncio.sleep(max(0,lease-now)+.02);save(out/'actual-lease-wait.json',dict(original_lease=lease,started=now,finished=time.monotonic()))
        ddir=out/'drive';drive=await asyncio.to_thread(finish,launch(sample,cfg,'drive',ddir),ddir,min(40,deadline-time.monotonic()));after_drive=snapshot(config,sample,http,out/'after-drive')
        checks=assess(rid,killed,before,after_read,after_node,after_drive,read,node,drive,old_pi,new_pi,dispatch(initial),dispatch(sdir),dispatch(qdir),dispatch(ddir))
        checks.extend([dict(check='one complete original fixed HTTP/no HTTP errors',passed=len(http.records)==1 and not http.errors and all(x.get('request_complete') and x.get('response_complete') for x in http.records)),dict(check='original finite 180 second envelope',passed=time.monotonic()<=deadline)])
        result.update(checks=checks,status='PASS' if checks and all(c['passed'] for c in checks) else 'FAIL')
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    finally:
        save(out/'assessment-before-cleanup.json',result)
        if config is not None:
            try:cleanup(SimpleNamespace(execution=SimpleNamespace(engine=Engine(config['runtime']['engine_endpoint']))),config,out)
            except Exception as exc:result['cleanup_error']=repr(exc);result['status']='FAIL'
        if http is not None:
            try:http.close()
            except Exception as exc:result['HTTP_close_error']=repr(exc);result['status']='FAIL'
        server.close();result['NATS_reaped']=server.proc is None or server.proc.poll() is not None
        if not result['NATS_reaped']:result['status']='FAIL'
        save(out/'result.json',result)
    return result
