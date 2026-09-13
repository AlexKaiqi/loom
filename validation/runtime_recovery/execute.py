"""Finite parent process: original services survive the killed Runtime child."""
import asyncio,json,os,signal,subprocess,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace
from validation.runtime_security.fixtures import save
from validation.runtime_security.exercise import cleanup
from .facts import snapshot,assess
from .fixtures import durable,ROOT

def launch(sample,config,mode,out):
    out.mkdir();stdout=(out/'stdout.txt').open('wb');stderr=(out/'stderr.txt').open('wb')
    argv=[sys.executable,'-B',str(ROOT/'validation/runtime_recovery/worker.py'),'--fixture',str(Path(sample['out'])/'fixture.json'),'--config',str(config),'--mode',mode,'--out',str(out)]
    p=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,start_new_session=True,close_fds=True)
    save(out/'process.json',dict(argv=argv,pid=p.pid,pgid=os.getpgid(p.pid),started=time.monotonic()))
    return p,stdout,stderr

def wait_cut(process,out,deadline):
    p,stdout,stderr=process;cut_path=out/'cut.json'
    try:
        while time.monotonic()<deadline:
            if cut_path.exists():
                cut=json.loads(cut_path.read_bytes())
                if cut['pid']!=p.pid or cut['pgid']!=p.pid or os.getpgid(p.pid)!=p.pid:raise AssertionError('cut process identity differs')
                proc=Path('/proc')/str(p.pid);save(out/'actual-process-before-kill.json',dict(status=(proc/'status').read_text(),stat=(proc/'stat').read_text()))
                sent=time.monotonic();os.killpg(p.pid,signal.SIGKILL);code=p.wait(timeout=5)
                result=dict(pid=p.pid,returncode=code,cut=cut,sigkill_sent=sent,reaped=time.monotonic());save(out/'external-kill.json',result);return result
            if p.poll() is not None:raise RuntimeError('original child exited before requested cut: '+str(p.returncode))
            time.sleep(.02)
        raise TimeoutError('original cut was not reached within its finite bound')
    finally:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
        stdout.close();stderr.close()

def finish(process,out,timeout):
    p,stdout,stderr=process
    try:
        code=p.wait(timeout=timeout)
        save(out/'actual-exit.json',dict(pid=p.pid,returncode=code,finished=time.monotonic()))
        if code!=0:raise RuntimeError('new process failed: '+str(code)+'; see '+str(out))
        return json.loads((out/'result.json').read_bytes())
    finally:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
        stdout.close();stderr.close()

async def one(sample,spec):
    from validation.components.e.support import Server
    from validation.session_service.live import HTTPFixture
    from validation.system.m01_run import configuration
    from lore_execution.engine import Engine
    out=Path(sample['out']);server=Server(out/'nats');http=None;config=None;result=dict(id=sample['id'],status='FAIL',checks=[])
    deadline=time.monotonic()+180
    try:
        response=out/'response.body';http=HTTPFixture(out/'http',[response.read_bytes()] if response.exists() else [])
        config=configuration(sample,server.url,http.endpoint);config_path=out/'config.json';durable(config_path,config)
        await server.start();initial=out/'initial'
        killed=await asyncio.to_thread(wait_cut,launch(sample,config_path,'initial',initial),initial,deadline-50)
        before=snapshot(config,sample,http,out/'before-query')
        query_dir=out/'query';query=await asyncio.to_thread(finish,launch(sample,config_path,'query',query_dir),query_dir,min(35,deadline-time.monotonic()))
        after=snapshot(config,sample,http,out/'after-query');recovered=after;drive={}
        if sample['cut']!='accept':
            parent=next(x for x in after['state']['R']['requests'] if x['id']==sample['id']+'-invocation')
            lease=parent['lease_until']
            if type(lease) not in (int,float) or lease>deadline-35:raise AssertionError('original finite lease unavailable')
            observed=time.monotonic();await asyncio.sleep(max(0,lease-observed)+.02)
            save(out/'actual-lease-wait.json',dict(original_lease=lease,started=observed,finished=time.monotonic()))
            drive_dir=out/'drive';drive=await asyncio.to_thread(finish,launch(sample,config_path,'drive',drive_dir),drive_dir,min(40,deadline-time.monotonic()))
            recovered=snapshot(config,sample,http,out/'after-drive')
        dispatch_file=initial/'actual-Engine-at-dispatch.json';dispatches=json.loads(dispatch_file.read_bytes()) if dispatch_file.exists() else []
        original_request=json.loads((initial/'original-request.json').read_bytes())
        query_dispatches=json.loads((query_dir/'actual-Engine-at-dispatch.json').read_bytes())
        drive_dispatches=json.loads((out/'drive/actual-Engine-at-dispatch.json').read_bytes()) if sample['cut']!='accept' else []
        checks=assess(sample,spec,killed,before,after,recovered,query,drive,dispatches,original_request,query_dispatches,drive_dispatches)
        checks.append(dict(check='original 180 second cut bound',passed=time.monotonic()<=deadline))
        result.update(checks=checks,status='PASS' if checks and all(c['passed'] for c in checks) else 'FAIL')
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    finally:
        save(out/'assessment-before-cleanup.json',result)
        if config is not None:
            try:
                # Original exact owner/CID/volume cleanup from the existing M02 helper.
                cleanup(SimpleNamespace(execution=SimpleNamespace(engine=Engine(config['runtime']['engine_endpoint']))),config,out)
            except Exception as exc:result['cleanup_error']=repr(exc);result['status']='FAIL'
        if http is not None:
            try:http.close()
            except Exception as exc:result['HTTP_close_error']=repr(exc);result['status']='FAIL'
        server.close();result['NATS_reaped']=server.proc is None or server.proc.poll() is not None
        if not result['NATS_reaped']:result['status']='FAIL'
        save(out/'result.json',result)
    return result
