"""Bounded real-facility load and restart check; no long-duration reliability claim.

The plan and thresholds are written before dispatch. Node event-only and Python
model-using strategies share the actual scheduler, SQLite/Git and Linux launcher.
The model's HTTP endpoint is controlled; this does not measure provider capacity.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import threading
import time

from support import CLIFixture, ROOT, ProviderFixture, query
from run_frozen import fingerprint


def run(args):
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    os.environ['LOOM_GO_BINARY']=str(Path(args.binary).resolve())
    os.environ.pop('LOOM_GO_EVIDENCE',None)
    fixture=CLIFixture();fixture.setUp()
    fixture.base=output;fixture.authority=output/'authority.sqlite';fixture.config=output/'config.toml'
    before=fingerprint()
    plan=dict(test_id='A21-bounded-load',works=32,initial_facts_per_work=4,file_bytes_per_work=65536,
              receivers=8,concurrency=4,source_events=12,event_interval_seconds=.5,
              offline_seconds=2,scan_interval='200ms',
              thresholds=dict(initial_settle_seconds=60,delivery_p95_seconds=10,final_settle_seconds=30,
                              restart_settle_seconds=20,controller_peak_rss_bytes=512*1024*1024),
              environment=dict(platform=platform.platform(),cpu_count=os.cpu_count(),
                               meminfo=Path('/proc/meminfo').read_text().splitlines()[:3]),
              binary_sha256=hashlib.sha256(fixture.binary.read_bytes()).hexdigest(),
              limitations=['Controlled HTTP model, no paid provider throughput.',
                           'Two-second unload/restart, not a long-duration soak.'])
    (output/'plan.json').write_text(json.dumps(plan,indent=2))
    (output/'source-hashes.json').write_text(json.dumps(before,sort_keys=True,indent=2))
    observation={'status':'fail','plan':'plan.json','samples':[],'deliveries':[]}
    process=None
    provider=ProviderFixture('text')
    serving=threading.Thread(target=provider.serve_forever,daemon=True);serving.start()
    def active_domains():
        with closing(sqlite3.connect(fixture.authority)) as db:
            return db.execute("SELECT count(*) FROM execution_domains WHERE state='retained'").fetchone()[0]
    def sample():
        assert process.poll() is None,'scheduler exited'
        status=Path('/proc',str(process.pid),'status').read_text()
        rss=int(next(line for line in status.splitlines() if line.startswith('VmRSS:')).split()[1])*1024
        active=active_domains()
        observation['samples'].append(dict(at=time.monotonic(),rss_bytes=rss,active_domains=active))
        assert active<=plan['concurrency'],'scheduler exceeded declared active concurrency'
        assert rss<=plan['thresholds']['controller_peak_rss_bytes'],'controller memory threshold exceeded'
    def settled(works):
        return all(not query(w,'SELECT * FROM pending') and
                   not query(w,"SELECT * FROM rounds WHERE state!='handed_off'") for w in works) and active_domains()==0
    def await_settled(works,seconds):
        start=time.monotonic()
        while time.monotonic()-start<seconds:
            sample()
            if settled(works):return time.monotonic()-start
            time.sleep(.05)
        raise AssertionError('work did not settle within fixed threshold')
    def start(name):
        nonlocal process
        with (output/(name+'.log')).open('wb') as log:
            process=subprocess.Popen(fixture.command('serve','--concurrency',plan['concurrency'],
                '--scan-interval',plan['scan_interval']),env=fixture.env,stdout=log,stderr=log)
    def stop():
        nonlocal process
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
    try:
        node=fixture.policy('event-policy',timeout=30)
        worker=node/'worker.mjs'
        worker.write_text(worker.read_text().replace('c.listen();',
            'c.onRequest("policy.start",p=>c.handoff(p.handoff_basis));c.listen();'))
        definitions=[fixture.definition(name='node.toml',sandbox=False),
                     fixture.definition(name='python.toml',sandbox=False,harness_argv=['python3','-I','{harness}/worker.py'])]
        for definition in definitions:
            definition.write_text(definition.read_text().replace('contextWindow=4096','contextWindow=65536'))
        works=[]
        for index in range(plan['works']):
            w=output/('work-'+str(index))
            fixture.call('create',w,'--harness',node if index%2==0 else ROOT/'harnesses/kernel',
                         '--definition',definitions[index%2])
            shutil.copyfile(ROOT/'templates/default/surface/main.md',w/'surface/main.md')
            (w/'surface/retained.bin').write_bytes(b'R'*plan['file_bytes_per_work'])
            for n in range(plan['initial_facts_per_work']):
                fixture.admit(w,'seed-'+str(n),{'text':'bounded load history '+str(n)})
            works.append(w)
        fixture.configure(model_endpoint=provider.base_url)
        start('initial-scheduler')
        observation['initial_settle_seconds']=await_settled(works,plan['thresholds']['initial_settle_seconds'])
        source=works[0];receivers=works[1:1+plan['receivers']]
        watermark=query(source,'SELECT max(seq) AS seq FROM events')[0]['seq']
        for w in receivers:
            fixture.call('allow-relay',source,w)
            command=fixture.command('subscribe',w,source,'watch','--kind','work.objective.set','--after',watermark)
            result=subprocess.run(command,capture_output=True,env=fixture.env,timeout=10)
            assert result.returncode==0,result.stderr.decode()
        pending={}
        def observe_deliveries():
            for marker,(sent,remaining) in list(pending.items()):
                for w in list(remaining):
                    rows=query(w,"SELECT seq FROM events WHERE json_extract(payload,'$.text')=?",(marker,))
                    if len(rows)==1 and not query(w,'SELECT * FROM pending WHERE seq=?',(rows[0]['seq'],)):
                        observation['deliveries'].append(dict(work=w.name,marker=marker,latency_seconds=time.monotonic()-sent))
                        remaining.remove(w)
                if not remaining:del pending[marker]
        for n in range(plan['source_events']):
            marker='fanout-'+str(n);sent=time.monotonic()
            fixture.admit(source,marker,{'text':marker})
            pending[marker]=(sent,set(receivers))
            until=sent+plan['event_interval_seconds']
            while time.monotonic()<until:
                sample();observe_deliveries();time.sleep(.05)
        deadline=time.monotonic()+plan['thresholds']['final_settle_seconds']
        while pending and time.monotonic()<deadline:
            sample();observe_deliveries();time.sleep(.05)
        assert not pending,'missing/unhandled multi-Work delivery'
        await_settled(works,plan['thresholds']['final_settle_seconds'])
        latencies=sorted(d['latency_seconds'] for d in observation['deliveries'])
        assert len(latencies)==plan['source_events']*plan['receivers']
        observation['delivery_p95_seconds']=latencies[(len(latencies)*95+99)//100-1]
        assert observation['delivery_p95_seconds']<=plan['thresholds']['delivery_p95_seconds']
        assert active_domains()==0,'waiting Works retained active execution domains'
        stop()
        fixture.admit(source,'while-offline',{'text':'persistent-offline-event'})
        time.sleep(plan['offline_seconds'])
        assert len(query(source,'SELECT * FROM pending'))==1
        assert active_domains()==0
        start('restarted-scheduler')
        observation['restart_settle_seconds']=await_settled(works,plan['thresholds']['restart_settle_seconds'])
        for w in receivers:
            rows=query(w,"SELECT seq FROM events WHERE json_extract(payload,'$.text')='persistent-offline-event'")
            assert len(rows)==1 and not query(w,'SELECT * FROM pending WHERE seq=?',(rows[0]['seq'],))
        for w in works:
            assert (w/'surface/retained.bin').read_bytes()==b'R'*plan['file_bytes_per_work']
        observation['provider_requests']=len(provider.calls)
        observation['peak_active_domains']=max(s['active_domains'] for s in observation['samples'])
        assert observation['peak_active_domains']>1,'load never exercised concurrent active Works'
        observation['status']='pass'
    finally:
        stop();provider.shutdown();provider.server_close();serving.join()
        observation['source_unchanged']=fingerprint()==before
        (output/'observations.json').write_text(json.dumps(observation,indent=2))
        fixture.doCleanups()
    assert observation['source_unchanged'],'source changed during acceptance'
    print(json.dumps({k:v for k,v in observation.items() if k not in ('samples','deliveries')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',required=True)
    parser.add_argument('--output',required=True)
    run(parser.parse_args())
