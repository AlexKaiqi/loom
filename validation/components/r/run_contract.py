"""One bounded R acceptance entry, with mandatory unit and actual process companions."""
import argparse
import ast
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument("--module",default="lore.control");parser.add_argument("--batch",required=True);args=parser.parse_args()
if not args.batch or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.batch):parser.error("simple fresh batch ID required")
out=ROOT/"validation/components/r/evidence"/args.batch;out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs={str(p.relative_to(ROOT)):sha(p) for base in (ROOT/"design/g3/r",ROOT/"validation/components/r") for p in base.glob("*") if p.suffix in (".md",".json",".py")}
inventory=json.loads((ROOT/"design/g3/r/execution-inventory.json").read_text())
manifest=json.loads((ROOT/"design/g3/r/cases.json").read_text())
report={"scope":"R component only; reference authority is explicit fixture, no OS stop/model/NATS proof","module":args.module,"started":time.time(),"environment":{"python":platform.python_version(),"platform":platform.platform(),"uid":os.getuid()},"inputs":inputs,"expected_units":inventory["unit_case_ids"],"expected_process":inventory["required_process_case_ids"],"executed_units":[],"executed_process":[],"status":"STARTED"}
rc=1
try:
    os.environ["LORE_CONTROL_MODULE"]=args.module
    os.environ["LORE_R_EVIDENCE_DIR"]=str(out/"unit-fixtures")
    import test_control as tests
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(tests.ControlContract)
    discovered=[t._testMethodName.split("_")[1] for t in suite]
    if sorted(discovered)!=sorted(inventory["unit_case_ids"]) or sorted(discovered)!=sorted(x["id"] for x in manifest["cases"]):raise RuntimeError("required unit inventory differs from executable discovery")
    report["discovered_units"]=discovered
    try:module=importlib.import_module(args.module)
    except ModuleNotFoundError as exc:
        if exc.name not in {args.module,args.module.split(".")[0]}:raise
        report.update(status="MISSING",reason="component unavailable; no component property credited");rc=2
    else:
        origin=Path(module.__file__).resolve();base=origin.parent
        source_files=sorted(base.rglob("*.py")) if (base/"__init__.py").exists() else [origin]
        sources={str(p):sha(p) for p in source_files};report["implementation"]=sources
        class Result(unittest.TextTestResult):
            def startTest(self,test):
                report["executed_units"].append(test._testMethodName.split("_")[1]);super().startTest(test)
        log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
        (out/"unit.log").write_text(log.getvalue())
        report["unit_failures"]=[{"test":str(t),"trace":s} for t,s in result.failures]
        report["unit_errors"]=[{"test":str(t),"trace":s} for t,s in result.errors]
        report["unit_skips"]=[{"test":str(t),"reason":s} for t,s in result.skipped]
        argv=[sys.executable,str(Path(__file__).with_name("process_cases.py")),"--evidence",str(out/"process")]
        env=dict(os.environ);env["PYTHONPATH"]=str(ROOT)+os.pathsep+env.get("PYTHONPATH","")
        child=subprocess.run(argv,cwd=Path(__file__).parent,env=env,capture_output=True,timeout=300)
        (out/"process.stdout").write_bytes(child.stdout);(out/"process.stderr").write_bytes(child.stderr)
        report["process_exit"]=child.returncode;report["process_argv"]=argv
        assessment=json.loads((out/"process/assessment.json").read_text())
        report["process_assessment"]=assessment
        report["executed_process"]=[row["case"] for row in assessment["rows"] if "case" in row]
        report["sources_unchanged"]=all(Path(p).is_file() and sha(Path(p))==h for p,h in sources.items())
        report["inputs_unchanged"]=all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in inputs.items())
        ok=result.wasSuccessful() and not result.skipped and sorted(report["executed_units"])==sorted(inventory["unit_case_ids"]) and child.returncode==0 and assessment["status"]=="PASS" and not assessment["pending_companions"] and sorted(report["executed_process"])==sorted(inventory["required_process_case_ids"]) and all(x.get("status")=="PASS" for x in assessment["rows"]) and report["sources_unchanged"] and report["inputs_unchanged"]
        report["status"]="PASS" if ok else "FAIL";rc=0 if ok else 1
except BaseException as exc:
    report.update(status="INVALID",error={"type":type(exc).__name__,"message":str(exc)});rc=1
report["finished"]=time.time();(out/"result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"status":report["status"],"unit_cases":len(report["executed_units"]),"process_cases":len(report["executed_process"]),"evidence":str(out)}));sys.exit(rc)
