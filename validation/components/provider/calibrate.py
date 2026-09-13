"""Live socket/byte calibration only. No Pi mapping implementation."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import time
from collector import Collector
from evidence import ROOT, begin, unchanged

parser=argparse.ArgumentParser();parser.add_argument("--batch",required=True);args=parser.parse_args()
os.chdir(ROOT);out,inputs=begin(args.batch)
requests=json.loads((ROOT/"design/g3/provider/request-cases.json").read_bytes())["cases"]
responses=json.loads((ROOT/"design/g3/provider/cases.json").read_bytes())["cases"]
server=Collector(out/"server");checks=[];observations=[];started=time.monotonic()
try:
    jobs=[(case,responses[0]) for case in requests if case["expected_http_requests"]==1]
    jobs.append((requests[0],responses[7]))
    for number,(request,response) in enumerate(jobs):
        sent=(ROOT/request["expected_request"]["body_path"]).read_bytes();raw=(ROOT/response["response"]["body_path"]).read_bytes()
        server.configure(response["response"],raw);before=server.snapshot()
        client=http.client.HTTPConnection(server.endpoint["host"],server.endpoint["port"],timeout=2)
        client.request("POST","/v1/chat/completions",body=sent,headers={"Content-Type":"application/json"})
        actual=client.getresponse();short=False
        try:received=actual.read()
        except http.client.IncompleteRead as error:received=error.partial;short=True
        client.close();(out/f"client-{number}.body").write_bytes(received)
        after=server.snapshot();records=after["records"][len(before["records"]):]
        checks.extend([len(records)==1,Path(records[0]["body_path"]).read_bytes()==sent,records[0]["request_complete"],
                       received==raw,records[0]["closed"],records[0]["response_send_complete"],
                       short==(records[0]["response_body_size"]!=records[0]["advertised_response_length"])])
        observations.append(dict(request=request["id"],response=response["id"],short_read_exception=short,
                                 received_size=len(received),received_sha256=hashlib.sha256(received).hexdigest(),record=records[0]))
    before=server.snapshot();server.configure(responses[0]["response"],(ROOT/responses[0]["response"]["body_path"]).read_bytes());after=server.snapshot()
    checks.append(len(before["records"])==len(after["records"]))
    physical=after
finally:server.close()
changed=unchanged(inputs)
result=dict(status="PASS" if all(checks) and not changed else "FAIL",checks=len(checks),passed=sum(checks),http_requests=len(physical["records"]),
            max_active=physical["max_active"],io_bytes=physical["total_io"],elapsed=time.monotonic()-started,inputs_unchanged=not changed,
            scope="Collector byte/short-disconnect calibration; no candidate or provider mapping")
(out/"observations.json").write_text(json.dumps(observations,indent=2)+"\n");(out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result));raise SystemExit(0 if result["status"]=="PASS" else 1)
