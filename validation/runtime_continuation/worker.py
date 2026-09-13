"""M04-only worker; existing M03 implements fresh read-only query and recovery drive."""
import argparse,asyncio,copy,hashlib,json,os,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from validation.runtime_recovery.fixtures import durable
from validation.runtime_security.exercise import invocation
from validation.runtime_security.observations import engine_hook

async def run(sample,config,mode,out):
    if mode in ('query','drive'):
        from validation.runtime_recovery.worker import run as original_worker
        return await original_worker(sample,config,mode,out)
    from lore_runtime.bootstrap import assemble
    from lore_runtime.session_delivery import execution_id,confirmation_id
    from lore_session.execution import session_reference
    rt=assemble(config,credential_provider=None);rid=sample['id']+'-invocation';seen=[]
    rt.execution.checkpoint_hook=engine_hook(config,out,seen)
    durable(out/'actual-Engine-at-dispatch.json',seen)
    try:
        await rt.open()
        if mode=='initial':
            request=invocation(rt,sample);durable(out/'original-request.json',request);wait=threading.Event()
            def stop(label,value):
                if label=='result_saved' and value.get('id')==rid:
                    durable(out/'cut.json',dict(owner='Flow',label=label,value=value,pid=os.getpid(),pgid=os.getpgrp(),monotonic=time.monotonic()))
                    wait.wait()
            rt.flow.checkpoint=stop;rt.start('operator',request)
            reply=await rt.drive_until('operator',rid,deadline_monotonic=time.monotonic()+150)
            durable(out/'result.json',dict(status='FAIL_CUT_NOT_REACHED',reply=reply,pid=os.getpid()));return 1
        original_row=rt.control.query('operator',execution_id(rid,'drive'))
        if original_row['phase']!='confirmed':raise AssertionError('original normal drive facility is not confirmed')
        original=rt.snapshots.query(confirmation_id(original_row['id']))
        request=copy.deepcopy(original_row['payload']['node_request']);request.update(action='query',session_ref=session_reference(original))
        eid='m04-query-'+hashlib.sha256(rid.encode()).hexdigest();callbacks=[]
        def observe(label,value):
            if label in ('before_dispatch','before_query','effect_received','effect_queried'):
                callbacks.append(dict(label=label,value=value));durable(out/'actual-callbacks.json',callbacks)
        rt.session_service.checkpoint=observe;durable(out/'actual-callbacks.json',callbacks)
        before=rt.query('operator',rid)
        durable(out/'original-node-query-request.json',dict(node_request=request,execution_id=eid,selected_drive=original_row,selected_confirmation=original))
        evidence=await asyncio.to_thread(rt.session_service.invoke,request,execution_id=eid,deadline_monotonic=time.monotonic()+60)
        durable(out/'result.json',dict(status='OBSERVED_SESSION_QUERY',pid=os.getpid(),pgid=os.getpgrp(),execution_id=eid,evidence=evidence,callbacks=callbacks,query_before=before,query_after=rt.query('operator',rid),monotonic=time.monotonic()))
        return 0
    finally:await rt.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fixture',required=True);ap.add_argument('--config',required=True);ap.add_argument('--mode',choices=('initial','query','session_query','drive'),required=True);ap.add_argument('--out',required=True);a=ap.parse_args();out=Path(a.out);out.mkdir(exist_ok=True)
    try:return asyncio.run(run(json.loads(Path(a.fixture).read_bytes()),json.loads(Path(a.config).read_bytes()),a.mode,out))
    except Exception as exc:
        durable(out/'error.json',dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc(),pid=os.getpid()));return 1
if __name__=='__main__':raise SystemExit(main())
