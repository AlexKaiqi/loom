"""Actual fixed-source NATS mechanism experiment; preconditions in protocol-001.json."""
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
import nats
from nats.js.api import StreamConfig, ConsumerConfig, AckPolicy, DeliverPolicy, StorageType, DiscardPolicy

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BINARY = ROOT / 'research/.cache/nats-server/nats-server'

def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str)+'\n')

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def view(msg):
    d = {'subject':msg.subject, 'data':msg.data.decode(), 'headers':dict(msg.headers or {})}
    if hasattr(msg, 'seq'): d['seq'] = msg.seq
    else:
        m=msg.metadata
        d.update(stream_seq=m.sequence.stream, consumer_seq=m.sequence.consumer, delivered=m.num_delivered)
    return d

async def main(batch):
    out=HERE/'evidence'/batch
    out.mkdir(parents=True, exist_ok=False)
    state=ROOT/'research/.cache/nats-server'/batch
    state.mkdir(exist_ok=False)
    service_port=port()
    config=out/'server.conf'
    config.write_text(f'listen: "127.0.0.1:{service_port}"\njetstream {{ store_dir: "{state}", sync_interval: "always" }}\n')
    result={'scope':'Native fixed-source single NATS process, real file store; no OS/power/cluster claim',
            'protocol_sha256':hashlib.sha256((HERE/'protocol-001.json').read_bytes()).hexdigest(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'research/repos/nats-server',text=True).strip(),
            'client_version':importlib.metadata.version('nats-py'), 'observations':{}, 'checks':[], 'errors':[]}
    o=result['observations']; proc=None; nc=None; logs=[]
    def check(name, condition):
        result['checks'].append({'id':name,'passed':bool(condition)})
        if not condition: raise AssertionError(name)
    async def start(number):
        log=(out/f'server-{number}.log').open('w');logs.append(log)
        p=subprocess.Popen([str(BINARY),'-c',str(config)],stdout=log,stderr=subprocess.STDOUT,close_fds=True)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if p.poll() is not None: raise RuntimeError('NATS startup failed')
            try:
                reader,writer=await asyncio.open_connection('127.0.0.1',service_port)
                await reader.readline();writer.close();await writer.wait_closed();return p
            except OSError: await asyncio.sleep(.05)
        p.kill();p.wait();raise TimeoutError('NATS startup')
    async def connect(): return await nats.connect(servers=[f'nats://127.0.0.1:{service_port}'],max_reconnect_attempts=0)
    try:
        proc=await start(1);o['first_pid']=proc.pid
        nc=await connect();js=nc.jetstream()
        await js.add_stream(config=StreamConfig(name='FACTS',subjects=['facts'],storage=StorageType.FILE,duplicate_window=60))
        a=await js.publish('facts',b'A',headers={'Nats-Msg-Id':'r1'})
        b=await js.publish('facts',b'A',headers={'Nats-Msg-Id':'r1'})
        c=await js.publish('facts',b'B',headers={'Nats-Msg-Id':'r1'})
        o['publish_receipts']=[v.as_dict() for v in [a,b,c]]
        o['stored_before']=view(await js.get_msg('FACTS',seq=a.seq))
        check('N02_same_identity_dedup',a.seq==b.seq==c.seq and b.duplicate and c.duplicate and o['stored_before']['data']=='A')
        o['content_conflict_error']=False
        await js.add_stream(config=StreamConfig(name='MEM',subjects=['memory'],storage=StorageType.MEMORY))
        await js.publish('memory',b'volatile')
        await js.add_stream(config=StreamConfig(name='BOUND',subjects=['bounded'],storage=StorageType.FILE,max_msgs=1,discard=DiscardPolicy.OLD))
        first=await js.publish('bounded',b'first');last=await js.publish('bounded',b'last')
        try: await js.get_msg('BOUND',seq=first.seq);o['pruned_read']='unexpectedly found'
        except nats.js.errors.NotFoundError as e:o['pruned_read']={'code':e.code,'description':e.description}
        o['retained_latest']=view(await js.get_msg('BOUND',seq=last.seq))
        check('N05_retention_limit',isinstance(o['pruned_read'],dict) and o['retained_latest']['data']=='last')
        sub=await js.pull_subscribe('facts',durable='reader',config=ConsumerConfig(durable_name='reader',ack_policy=AckPolicy.EXPLICIT,ack_wait=.2,deliver_policy=DeliverPolicy.ALL))
        original=(await sub.fetch(1,timeout=2))[0];o['first_delivery']=view(original)
        check('N03_historical_delivery',original.data==b'A' and original.metadata.sequence.stream==a.seq)
        wrong=await js.pull_subscribe('facts',durable='new_only',config=ConsumerConfig(durable_name='new_only',deliver_policy=DeliverPolicy.NEW,ack_policy=AckPolicy.EXPLICIT))
        try: await wrong.fetch(1,timeout=.3);o['new_only_history']='unexpectedly found'
        except (nats.errors.TimeoutError,asyncio.TimeoutError):o['new_only_history']='timeout-no-prior-event'
        check('N06_wrong_start_rejects_history',o['new_only_history']=='timeout-no-prior-event')
        o['stream_config']=(await js.stream_info('FACTS')).config.as_dict()
        await nc.close();nc=None
        proc.kill();proc.wait(timeout=3);o['killed_exit']=proc.returncode
        check('old_server_reaped',proc.returncode==-9)
        proc=await start(2);o['second_pid']=proc.pid
        nc=await connect();js=nc.jetstream()
        o['stored_after']=view(await js.get_msg('FACTS',seq=a.seq))
        check('N01_process_crash_content',o['stored_after']==o['stored_before'])
        try: await js.stream_info('MEM');o['memory_after']='unexpectedly found'
        except nats.js.errors.NotFoundError as e:o['memory_after']={'code':e.code,'description':e.description}
        check('N06_memory_loss_control',isinstance(o['memory_after'],dict))
        sub=await js.pull_subscribe('facts',durable='reader')
        repeat=(await sub.fetch(1,timeout=3))[0];o['redelivery']=view(repeat)
        check('N04_unacked_identity_redelivery',repeat.data==b'A' and repeat.metadata.sequence.stream==a.seq and repeat.metadata.num_delivered>1)
        await repeat.ack_sync(timeout=2)
        o['consumer_after_ack']=(await js.consumer_info('FACTS','reader')).as_dict()
        check('N04_ack_floor',o['consumer_after_ack']['num_ack_pending']==0 and o['consumer_after_ack']['ack_floor']['stream_seq']==a.seq)
    except Exception as e:
        result['errors'].append({'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
    finally:
        if nc: await nc.close()
        if proc and proc.poll() is None: proc.terminate();proc.wait(timeout=5)
        for log in logs:log.close()
        result['status']='PASS' if not result['errors'] else 'FAIL'
        dump(out/'result.json',result)
        print(json.dumps({'batch':batch,'status':result['status'],'checks':result['checks'],'errors':result['errors']}))
    return 0 if not result['errors'] else 1

if __name__=='__main__':raise SystemExit(asyncio.run(main(sys.argv[1])))
