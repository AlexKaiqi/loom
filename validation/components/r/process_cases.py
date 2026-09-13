"""R02/R07/R08/R12/R15/R18 real process companions; each run preserves raw data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from test_control import ControlContract,MODULE
from oracle import exact_identity_counts,responsibility,exact_binding

parser=argparse.ArgumentParser();parser.add_argument("--evidence",required=True);args=parser.parse_args()
out=Path(args.evidence);out.mkdir(parents=True,exist_ok=False)
rows=[]
os.environ["LORE_R_EVIDENCE_DIR"]=str(out/"fixtures")
fixture_counter=0
def start(fixture,slug,extra):
    cfg={"module":MODULE,"db":str(fixture.db),"authority":fixture.authority,"refs":fixture.refs,"refroot":str(fixture.refroot),"ready":str(out/(slug+".ready.json")),**extra}
    cp=out/(slug+".config.json");cp.write_text(json.dumps(cfg,indent=2))
    stdout=(out/(slug+".stdout")).open("wb");stderr=(out/(slug+".stderr")).open("wb")
    proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name("process_worker.py")),str(cp)],stdout=stdout,stderr=stderr,close_fds=True)
    stdout.close();stderr.close();return proc,cfg

def backup(fixture,slug):
    dest=out/slug;dest.mkdir()
    for p in fixture.root.glob("control.sqlite*"):shutil.copy2(p,dest/p.name)
    with sqlite3.connect(fixture.db) as c:(dest/"raw.sql").write_text("\n".join(c.iterdump()))

def wait_cut(proc,cfg):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        p=Path(cfg["ready"])
        if p.exists():
            data=json.loads(p.read_text())
            if data.get("pid")==proc.pid and data.get("label")==cfg["cut"]:return data
        if proc.poll() is not None:raise AssertionError("worker exited before actual cut")
        time.sleep(.02)
    raise AssertionError("cut not reached")

def fixture():
    global fixture_counter
    fixture_counter+=1
    f=ControlContract();f.fixture_label=f"fixture-{fixture_counter:03d}"
    try:f.setUp()
    except BaseException:
        f.doCleanups();raise
    return f

def crash_case(slug,cut,setup=False):
    f=fixture();proc=None
    try:
        if setup:
            c=f.result_ready();f.store.accept_decision("op1",c["token"],"d1",f.refs["r1"],f.refs["h1"],{"successors":[f.req(id="next")]})
        f.store.close()
        extra={"action":"apply","parent":"op1","decision":"d1"} if setup else {"action":"accept_hold" if cut=="after_client_ack" else "accept","principal":"alice","request":f.req()}
        proc,cfg=start(f,slug,{**extra,"cut":cut,"cut_id":"op1"});ready=wait_cut(proc,cfg)
        proc.send_signal(signal.SIGKILL);code=proc.wait(timeout=5);assert code==-signal.SIGKILL
        backup(f,slug+"-after-kill")
        q,qcfg=start(f,slug+"-query",{"action":"query","principal":"alice","id":"op1"});assert q.wait(timeout=10)==0
        original=json.loads((out/(slug+"-query.stdout")).read_text())
        expected={"principal":"alice",**f.req()};exact_binding({k:original[k] for k in expected},expected)
        if setup:
            with sqlite3.connect(f.db) as c:
                phase=c.execute("select phase from requests where id='op1'").fetchone()[0]
                decision=c.execute("select parent_id,source_ref_json,harness_ref_json,body_json,applied from decisions where id='d1'").fetchone()
                assert decision and decision[0]=="op1" and json.loads(decision[1])==f.refs["r1"] and json.loads(decision[2])==f.refs["h1"] and json.loads(decision[3])=={"successors":[f.req(id="next")]}
                old=int(phase=="decide")
                nxt=c.execute("select count(*) from requests where id='next' and phase='accepted'").fetchone()[0]
            responsibility([{"old":old,"successor":nxt,"saved_stop":0}])
            if cut=="before_handoff_commit":assert phase=="decide" and old==1 and nxt==0 and decision[4]==0
            else:assert phase=="settled" and old==0 and nxt==1 and decision[4]==1
        rows.append({"case":slug,"status":"PASS","actual_cut":ready,"signal_exit":code})
    finally:
        if proc is not None and proc.poll() is None:proc.kill();proc.wait()
        f.doCleanups()

try:
    for repetition in range(3):
        crash_case(f"R02-ack-kill-{repetition}","after_client_ack")
        crash_case(f"R02-commit-lost-reply-{repetition}","after_commit_before_reply")
        for cut in ("before_handoff_commit","after_handoff_commit_before_reply"):
            crash_case(f"R12-{cut}-{repetition}",cut,True)
        f=fixture();procs=[]
        try:
            f.store.close()
            for worker in range(4):
                p,_=start(f,f"R07-{repetition}-{worker}",{"action":"accept_many","principal":"alice","requests":[f.req(id=f"d{i}") for i in range(12)]});procs.append(p)
            for p in procs:assert p.wait(timeout=10)==0
            with sqlite3.connect(f.db) as c:ids=[x[0] for x in c.execute("select id from requests")]
            exact_identity_counts(ids,[f"d{i}" for i in range(12)]);backup(f,f"R07-{repetition}-db")
            rows.append({"case":f"R07-{repetition}","status":"PASS","pids":[p.pid for p in procs],"actual_ids":ids})
        finally:
            for p in procs:
                if p.poll() is None:p.kill();p.wait()
            f.doCleanups()
    for repetition in range(3):
        for mode in ("claim","holder"):
            f=fixture();procs=[]
            try:
                if mode=="claim":
                    for ns in ("n1","n2","n3"):
                        for i in range(12):f.store.accept("admin",f.req(id=f"{ns}-{i}",ns=ns))
                else:f.register()
                f.store.close()
                for worker in range(4):
                    extra={"action":"claim_many","worker":f"worker-{worker}"} if mode=="claim" else {"action":"acquire","resource_id":"s1","execution_id":f"exec-{worker}","base_ref":f.refs["f1"]}
                    p,_=start(f,f"parallel-{mode}-{repetition}-{worker}",extra);procs.append(p)
                for p in procs:assert p.wait(timeout=10)==0
                observations=[json.loads((out/f"parallel-{mode}-{repetition}-{worker}.stdout").read_text()) for worker in range(4)]
                if mode=="claim":
                    claims=[x for batch in observations for x in batch]
                    exact_identity_counts([x["id"] for x in claims],[f"{ns}-{i}" for ns in ("n1","n2","n3") for i in range(12)])
                    assert len(set(x["token"] for x in claims))==36
                    case="R08"
                else:
                    with sqlite3.connect(f.db) as c:holders=c.execute("select resource_id,execution_id from holders").fetchall()
                    assert len(holders)==1 and holders[0][0]=="s1"
                    assert sum(x.get("rejected")=="busy" for x in observations)==3
                    case="R15"
                backup(f,f"{case}-{repetition}-db");rows.append({"case":f"{case}-{repetition}","status":"PASS","pids":[p.pid for p in procs]})
            finally:
                for p in procs:
                    if p.poll() is None:p.kill();p.wait()
                f.doCleanups()
    f=fixture();lock=None
    try:
        f.store.accept("alice",f.req());f.store.close()
        lock=sqlite3.connect(f.db);lock.execute("BEGIN IMMEDIATE")
        p,_=start(f,"R18-locked",{"action":"accept","principal":"alice","request":f.req(id="locked"),"transaction_timeout":0.1})
        code=p.wait(timeout=10);assert code!=0
        locked_result=json.loads((out/"R18-locked.stdout").read_text())
        assert locked_result["error_code"]=="storage_error" and locked_result["action"]=="accept" and locked_result["request_id"]=="locked"
        assert lock.in_transaction
        (out/"R18-lock-observer.json").write_text(json.dumps({"observer_pid":os.getpid(),"observer_connection_in_transaction":lock.in_transaction,"begin":"BEGIN IMMEDIATE","requested_id":"locked","worker_pid":p.pid,"actual_contract_error":locked_result}))
        lock.rollback();lock.close();lock=None
        with sqlite3.connect(f.db) as c:
            assert c.execute("select id from requests").fetchall()==[("op1",)]
        backup(f,"R18-lock-db");rows.append({"case":"R18-lock","status":"PASS","exit":code})
    finally:
        if lock is not None:lock.rollback();lock.close()
        f.doCleanups()
    f=fixture();probe=None
    try:
        f.store.accept("alice",f.req());f.store.close()
        # Existing acknowledged DB becomes actually unwritable for the test UID.
        for file in f.root.glob("control.sqlite*"):file.chmod(0o444)
        f.root.chmod(0o555)
        try:
            probe=f.new_store(transaction_timeout=0.1)
            try:probe.accept("alice",f.req(id="readonly"))
            except Exception as exc:assert getattr(exc,"code",None)=="storage_error",repr(exc)
            else:raise AssertionError("readonly accepted without actual persistence")
        except Exception as exc:
            assert getattr(exc,"code",None)=="storage_error",repr(exc)
        finally:
            if probe is not None:probe.close()
            f.root.chmod(0o755)
            for file in f.root.glob("control.sqlite*"):file.chmod(0o644)
        with sqlite3.connect(f.db) as c:assert c.execute("select id from requests").fetchall()==[("op1",)]
        backup(f,"R18-readonly-db");rows.append({"case":"R18-readonly","status":"PASS","actual_uid":os.getuid()})
    finally:f.root.chmod(0o755);f.doCleanups()
    status="PASS"
except Exception as exc:
    status="FAIL";rows.append({"status":"FAIL","error":repr(exc)})
(out/"assessment.json").write_text(json.dumps({"stage":"COMPONENT_WHEN_REAL_SUT_ELSE_PREPARATION","status":status,"rows":rows,"pending_companions":[]},indent=2))
sys.exit(0 if status=="PASS" else 1)
