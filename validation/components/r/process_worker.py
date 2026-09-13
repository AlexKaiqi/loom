"""Actual child process used for preregistered crash/concurrency checks."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import sys

cfg=json.loads(Path(sys.argv[1]).read_text())
module=importlib.import_module(cfg["module"])
def checker(ref,purpose,expected=None):
    from restore_fixture import check as restore_check
    restored=restore_check(ref,purpose,expected,cfg["refs"],cfg["refroot"])
    if restored is not None:return restored
    if purpose=="input" and (isinstance(expected,dict) and "invocation_id" in expected or isinstance(ref,dict) and "path" in ref):
        from input_fixture import check_input_ref
        return check_input_ref(ref,expected,Path(cfg["refroot"]).parent)
    if not isinstance(ref,dict) or ref.get("id") not in cfg["refs"]:return False
    original=cfg["refs"][ref["id"]]
    p=Path(cfg["refroot"])/ref["id"]
    from reference_context_fixture import matches_context
    kinds={"stop":{"answer","stop_reason"},"result":{"tool_result","answer"},"stopped":{"stopped"},"published":{"file_version"}}
    return ref==original and p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==ref["sha256"] and (purpose not in kinds or ref["kind"] in kinds[purpose]) and (matches_context(cfg["refroot"],ref,purpose,expected) if purpose in {"base","stop"} else all(ref.get(k)==v for k,v in (expected or {}).items()))
def checkpoint(label,record):
    if label==cfg.get("cut") and record.get("id")==cfg.get("cut_id"):
        p=Path(cfg["ready"]);t=p.with_suffix(".tmp")
        with t.open("w") as f:
            json.dump({"label":label,"record_id":record["id"],"pid":os.getpid()},f);f.flush();os.fsync(f.fileno())
        t.replace(p)
        signal.pause()
store=module.ControlStore(cfg["db"],authority=cfg["authority"],reference_checker=checker,checkpoint=checkpoint,transaction_timeout=cfg.get("transaction_timeout",10))
action=cfg["action"]
if action in ("accept","accept_hold"):
    try:out=store.accept(cfg["principal"],cfg["request"])
    except Exception as exc:
        print(json.dumps({"action":action,"request_id":cfg["request"]["id"],"error_code":getattr(exc,"code",None),"error_type":type(exc).__name__}),flush=True);sys.exit(2)
    if action=="accept_hold":
        p=Path(cfg["ready"]);t=p.with_suffix(".tmp")
        with t.open("w") as f:
            json.dump({"label":"after_client_ack","record_id":out["id"],"pid":os.getpid(),"receipt":out},f);f.flush();os.fsync(f.fileno())
        t.replace(p);signal.pause()
elif action=="apply":out=store.apply_decision(cfg["parent"],cfg["decision"])
elif action=="query":out=store.query(cfg["principal"],cfg["id"])
elif action=="query_input":out=store.query_input(cfg["principal"],cfg["id"])
elif action=="accept_many":
    out=[store.accept(cfg["principal"],request) for request in cfg["requests"]]
elif action=="claim_many":
    out=[]
    while True:
        claim=store.claim(cfg["worker"],100)
        if claim is None:break
        out.append(claim)
elif action=="acquire":
    try:out=store.acquire(cfg["resource_id"],cfg["execution_id"],cfg["base_ref"])
    except Exception as exc:
        if getattr(exc,"code",None)!="busy":raise
        out={"rejected":"busy"}
else:raise RuntimeError("unknown test worker action")
print(json.dumps(out,sort_keys=True,allow_nan=False),flush=True)
store.close()
