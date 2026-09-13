"""Original33 provider samples against a real collector and separate candidate processes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from collector import Collector
from evidence import ROOT, begin, unchanged
from oracle import assess

parser=argparse.ArgumentParser()
parser.add_argument("--module",default="lore_provider")
parser.add_argument("--batch",required=True)
parser.add_argument("--selection",choices=("all","bad","missing"),default="all")
args=parser.parse_args()
os.chdir(ROOT)
out, inputs = begin(args.batch,args.module)
requests=json.loads((ROOT/"design/g3/provider/request-cases.json").read_bytes())["cases"]
responses=json.loads((ROOT/"design/g3/provider/cases.json").read_bytes())["cases"]
jobs=[("response",c) for c in responses]+[("request",c) for c in requests]
if args.selection=="bad": jobs=[j for j in jobs if j[1]["id"] in {"PW01-text","PW08-short-body","PQ04-untrusted-url"}]
if args.selection=="missing": jobs=[("request",requests[0])]
started=time.monotonic(); observations=[]
server=Collector(out/"server")
try:
    for kind, case in jobs:
        assert time.monotonic()-started < 45
        request_case=requests[0] if kind=="response" else case
        response_case=case if kind=="response" else responses[0]
        response=response_case["response"]
        raw=(ROOT/response["body_path"]).read_bytes()
        server.configure(response,raw)
        previous=server.snapshot()
        token=uuid.uuid4().hex; jobdir=out/"workers"/token; jobdir.mkdir(parents=True)
        config=dict(module=args.module,intent=request_case["input"],scope=request_case["scope"],
                    endpoint=server.endpoint,artifacts=str(jobdir/"artifacts"),output=str(jobdir/"returned.json"))
        (jobdir/"input.json").write_text(json.dumps(config)+"\n")
        command=[sys.executable,"-B",str(ROOT/"validation/components/provider/worker.py"),str(jobdir/"input.json")]
        try:
            worker=subprocess.run(command,capture_output=True,timeout=5,
                env={"PATH":"/usr/bin:/bin","PYTHONPATH":str(ROOT)+":"+str(ROOT/"validation/components/provider")})
            (jobdir/"stdout").write_bytes(worker.stdout);(jobdir/"stderr").write_bytes(worker.stderr)
            returned=json.loads((jobdir/"returned.json").read_bytes())
            exit_code=worker.returncode
        except subprocess.TimeoutExpired as error:
            (jobdir/"stdout").write_bytes(error.stdout or b"");(jobdir/"stderr").write_bytes(error.stderr or b"")
            returned=dict(status="TIMEOUT");exit_code=-1
        current=server.snapshot(); records=current["records"][len(previous["records"]):]
        expected_request=(ROOT/request_case["expected_request"]["body_path"]).read_bytes() if request_case.get("expected_request") else b""
        failures=assess(case,kind,returned,records,expected_request,response,raw,request_case["scope"],config["artifacts"],responses[0]["expected"]["normalized"])
        if returned.get("status")=="MISSING": failures.append("component_missing")
        observation=dict(case_id=case["id"],kind=kind,worker=str(jobdir),command=command,
                         exit_code=exit_code,returned=returned,records=records,failures=failures)
        observations.append(observation)
        (out/"observations.json").write_text(json.dumps(observations,indent=2)+"\n")
    physical=server.snapshot()
finally:
    server.close()
changed=unchanged(inputs)
failures=[dict(case_id=x["case_id"],failures=x["failures"]) for x in observations if x["failures"]]
status="MISSING" if any("component_missing" in x["failures"] for x in observations) else "FAIL" if failures or changed else "PASS"
result=dict(status=status,scope="Finite local HTTP provider wire only; no real model/proxy/Pi Session or S acceptance",module=args.module,
    cases=len(observations),failures=failures,http_requests=len(physical["records"]),max_active=physical["max_active"],
    io_bytes=physical["total_io"],elapsed=time.monotonic()-started,inputs_unchanged=not changed,changed=changed,server_exit=server.process.exitcode)
if result["http_requests"]>32 or result["max_active"]>2 or result["io_bytes"]>67108864 or result["elapsed"]>=45 or result["server_exit"]!=0:
    result["status"]="INVALID"
(out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
raise SystemExit(0 if result["status"]=="PASS" else 2 if result["status"]=="MISSING" else 1)
