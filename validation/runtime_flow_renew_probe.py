"""One deterministic real-R lock/event-loop renewal regression; no Engine/network."""
import argparse, asyncio, concurrent.futures, hashlib, json, os, shutil, subprocess, sys, threading, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def need(v,m):
    if not v:raise AssertionError(m)
def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--child',action='store_true');p.add_argument('--out');a=p.parse_args();assert a.batch and all(x.isalnum() or x in '-_' for x in a.batch)
    out=Path(a.out) if a.out else ROOT/'validation/runtime-flow-renew-evidence'/a.batch
    if not a.child:
        out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';workspace.mkdir()
        files=[ROOT/'lore_runtime/flow.py',ROOT/'lore_runtime/__init__.py',Path(__file__),ROOT/'design/g4/runtime-flow-renew-001/protocol.md']
        files += [p for package in ('lore_control','lore_execution') for p in (ROOT/package).glob('*.py')]
        files += [ROOT/'lore_execution/profile.json']
        hashes={str(p.relative_to(ROOT)):sha(p) for p in files}
        for name in hashes:
            dest=workspace/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
        save(out/'sources.json',hashes);start=time.monotonic()
        proc=subprocess.Popen([sys.executable,'-B',str(workspace/'validation/runtime_flow_renew_probe.py'),'--child','--batch',a.batch,'--out',str(out)],cwd=workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        timeout=False
        try:stdout,stderr=proc.communicate(timeout=7)
        except subprocess.TimeoutExpired:
            timeout=True;proc.kill();stdout,stderr=proc.communicate(timeout=2)
        (out/'stdout').write_text(stdout);(out/'stderr').write_text(stderr)
        result=json.loads((out/'child-result.json').read_bytes()) if (out/'child-result.json').exists() else dict(status='FAIL',error='external 7 second timeout' if timeout else 'child result missing')
        result.update(child_pid=proc.pid,child_reaped=proc.poll() is not None,returncode=proc.returncode,external_timeout=timeout,elapsed=time.monotonic()-start,
                      source_unchanged=all(sha(ROOT/n)==h and sha(workspace/n)==h for n,h in hashes.items()),source_count=len(hashes))
        if timeout or proc.returncode!=0 or not result['source_unchanged']:result['status']='FAIL'
        save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 1
    from lore_control import ControlStore
    from lore_runtime.flow import RuntimeFlow
    main_thread=threading.get_ident();trace_lock=threading.Lock();trace=[]
    def note(name,**values):
        row=dict(event=name,pid=os.getpid(),thread=threading.get_ident(),time=time.monotonic(),**values)
        with trace_lock:
            trace.append(row)
            with (out/'trace.jsonl').open('ab') as f:
                f.write(json.dumps(row).encode()+b'\n');f.flush();os.fsync(f.fileno())
    c=ControlStore(out/'R.sqlite',{'runtime':{'namespaces':['n'],'roles':['runtime','submit']}},lease_seconds=3)
    c.accept('runtime',dict(id='original',namespace='n',kind='invocation',payload={}))
    row=c.claim('worker',time.monotonic());original_lease=c.db.execute('SELECT lease_until FROM requests WHERE id=?',(row['id'],)).fetchone()[0];marker=out/'readonly-original';marker.write_bytes(b'original-main-thread-read\n')
    old=c.renew
    def renew(*args):
        note('renew_enter',request_id=args[0]);value=old(*args);note('renew_exit',request_id=args[0],lease_until=value['lease_until']);return value
    c.renew=renew
    class Delivery:
        def __init__(self,loop):self.loop=loop
        def execute(self,row,deadline):
            note('execute_enter')
            with c._tx():
                note('R_transaction_held',in_transaction=c.db.in_transaction)
                time.sleep(1.1)
                done=concurrent.futures.Future()
                def complete():
                    note('callback_run',bytes_sha256=sha(marker));done.set_result(marker.read_bytes())
                note('callback_queued');self.loop.call_soon_threadsafe(complete)
                actual=done.result()
                need(actual==b'original-main-thread-read\n','original callback bytes changed');note('worker_callback_received')
            note('R_transaction_released');return {'owner':'S','fixture':'original-delivery'}
    async def run():
        flow=RuntimeFlow(c,None,Delivery(asyncio.get_running_loop()),'worker')
        actual=await flow._deliver(row,time.monotonic()+6)
        need(actual=={'owner':'S','fixture':'original-delivery'},'original delivery result changed')
        current=c.query('runtime','original');saved=c.db.execute('SELECT token,lease_until FROM requests WHERE id=?',(row['id'],)).fetchone();need(current['phase']=='issued' and saved['token']==row['token'] and saved['lease_until']>original_lease,'original lease renewal/token differ')
    result=dict(status='FAIL',scope='actual R transaction/renewal plus readonly ordinary callback; no F/Engine/model claims')
    try:
        asyncio.run(run())
        names=[r['event'] for r in trace]
        need(names.count('execute_enter')==names.count('callback_run')==names.count('renew_exit')==1,'duplicate or absent original call')
        selected={r['event']:r for r in trace}
        need(selected['callback_run']['thread']==main_thread and selected['renew_enter']['thread']!=main_thread,'renew blocks original main loop')
        need(names.index('renew_enter')<names.index('callback_queued')<names.index('callback_run')<names.index('worker_callback_received')<names.index('renew_exit'),'lock cut did not occur in preregistered order')
        result.update(status='PASS',case='FRN01',main_thread=main_thread,trace=trace)
    except Exception as ex:result.update(error=repr(ex),traceback=traceback.format_exc())
    finally:
        (out/'R.sql').write_text('\n'.join(c.db.iterdump()));c.close()
    save(out/'child-result.json',result);return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
