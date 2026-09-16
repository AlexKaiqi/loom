"""M05-only worker modes: 'run' completes without a cut; query/drive reuse M03."""
import argparse,asyncio,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from validation.runtime_recovery.fixtures import durable
from validation.runtime_security.exercise import invocation

async def run(sample,config,mode,out):
    if mode in ('initial','query','drive'):
        from validation.runtime_recovery.worker import run as original_worker
        return await original_worker(sample,config,mode,out)
    if mode=='run':
        import copy,time
        from lore_runtime.bootstrap import assemble
        rt=assemble(config,credential_provider=None);rt.bootstrap_config=copy.deepcopy(config)
        try:
            await rt.open();request=invocation(rt,sample);durable(out/'original-request.json',request)
            rt.start('operator',request)
            # The compaction re-drive extends the chain beyond one await window; a
            # paused reply with pending work resumes by the documented original
            # drive_until action (bounded, no alternate owner).
            # One drive action: the compaction fires mid-drive and the recorded
            # single-step effect budget (1 provider effect per drive) pauses the
            # continuation - R retains the pending responsibility by design.
            reply=await rt.drive_until('operator',request['id'],deadline_monotonic=time.monotonic()+150)
            phases=[(x.get('kind'),x.get('phase'),str(x.get('reason'))[:120]) for x in reply.get('requests',[]) if x.get('kind')=='invocation']
            durable(out/'result.json',dict(status='OBSERVED_RUN',reply=reply,phases=phases,pid=os.getpid()));return 0
            durable(out/'result.json',dict(status='OBSERVED_RUN',reply=reply,attempts=attempts,pid=os.getpid()));return 0
        finally:await rt.close()
    raise AssertionError('unknown M05 mode: '+mode)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fixture',required=True);ap.add_argument('--config',required=True);ap.add_argument('--mode',choices=('run','initial','query','drive'),required=True);ap.add_argument('--out',required=True);a=ap.parse_args();out=Path(a.out);out.mkdir(exist_ok=True)
    try:return asyncio.run(run(json.loads(Path(a.fixture).read_bytes()),json.loads(Path(a.config).read_bytes()),a.mode,out))
    except Exception as exc:
        durable(out/'error.json',dict(type=type(exc).__name__,message=str(exc),pid=os.getpid()));return 1
if __name__=='__main__':raise SystemExit(main())
