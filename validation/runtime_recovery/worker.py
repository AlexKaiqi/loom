"""One fresh Runtime process. Parent alone performs the actual SIGKILL."""
import argparse,asyncio,copy,json,os,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from validation.runtime_recovery.fixtures import durable
from validation.runtime_security.exercise import invocation
from validation.runtime_security.observations import engine_hook

def hooks(rt,sample,out):
    cut=sample['cut'];rid=sample['id']+'-invocation';wait=threading.Event();selected=False
    def observed(owner,label,value):
        nonlocal selected
        matches=(cut=='accept' and owner=='R' and label=='after_commit_before_reply' and value.get('id')==rid or
            cut in ('provider','tool') and owner=='S' and label=='effect_received' and value.get('binding',{}).get('operation_id')==rid and value.get('callback',{}).get('type')==cut+'.request' or
            cut=='decision' and owner=='Flow' and label=='decision_accepted' and value.get('parent_id')==rid or
            cut=='install' and owner=='F' and label=='after_exchange_before_record' and value.get('request_id','').startswith('tool-install-'))
        if not matches or selected:return
        selected=True
        durable(out/'cut.json',dict(owner=owner,label=label,value=value,pid=os.getpid(),pgid=os.getpgrp(),monotonic=time.monotonic()))
        wait.wait()  # No exception unwinding or cleanup; external parent kills this process group.
    rt.control.checkpoint=lambda label,value:observed('R',label,value)
    rt.session_service.checkpoint=lambda label,value:observed('S',label,value)
    rt.flow.checkpoint=lambda label,value:observed('Flow',label,value)
    rt.files.checkpoint=lambda label,value:observed('F',label,value)
    seen=[];rt.execution.checkpoint_hook=engine_hook(rt.bootstrap_config,out,seen)

async def run(sample,config,mode,out):
    from lore_runtime.bootstrap import assemble
    if mode!='initial':
        from lore_runtime.startup_assets import StartupAssets
        if not callable(getattr(StartupAssets,'open_existing',None)):
            durable(out/'result.json',dict(status='MISSING',dependency='StartupAssets.open_existing',pid=os.getpid()));return 2
    rt=assemble(config,credential_provider=None);rt.bootstrap_config=copy.deepcopy(config)
    try:
        if mode=='initial':
            await rt.open();request=invocation(rt,sample);durable(out/'original-request.json',request);hooks(rt,sample,out)
            rt.start('operator',request)
            result=await rt.drive_until('operator',request['id'],deadline_monotonic=time.monotonic()+150)
            durable(out/'result.json',dict(status='FAIL_CUT_NOT_REACHED',reply=result,pid=os.getpid()));return 1
        rid=sample['id']+'-invocation'
        seen=[];durable(out/'actual-Engine-at-dispatch.json',seen)
        rt.execution.checkpoint_hook=engine_hook(config,out,seen)
        if mode=='query':
            result=rt.query('operator',rid)
            durable(out/'result.json',dict(status='OBSERVED_QUERY',reply=result,pid=os.getpid(),pgid=os.getpgrp(),monotonic=time.monotonic()));return 0
        # Explicit recovery drive is a separate action, never hidden inside query.
        await rt.open()
        from validation.system.runtime_observer_sources import sql
        original=next(row for row in sql(config['runtime']['control_db'])['requests'] if row['id']==rid);lease=original['lease_until']
        now=time.monotonic()
        if type(lease) not in (int,float) or lease>now:
            durable(out/'result.json',dict(status='FAIL_LEASE_NOT_EXPIRED',original_lease=lease,actual_now=now,pid=os.getpid()));return 1
        reply=await rt.drive_until('operator',rid,deadline_monotonic=time.monotonic()+35)
        durable(out/'result.json',dict(status='OBSERVED_DRIVE',reply=reply,pid=os.getpid(),lease_before=lease,actual_start=now,actual_finish=time.monotonic()));return 0
    finally:await rt.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fixture',required=True);ap.add_argument('--config',required=True);ap.add_argument('--mode',choices=('initial','query','drive'),required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    out=Path(a.out);out.mkdir(exist_ok=True)
    try:return asyncio.run(run(json.loads(Path(a.fixture).read_bytes()),json.loads(Path(a.config).read_bytes()),a.mode,out))
    except Exception as exc:
        durable(out/'error.json',dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc(),pid=os.getpid()));return 1
if __name__=='__main__':raise SystemExit(main())
