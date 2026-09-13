"""Fixed inventory runner. Exit 2 = missing dependency; 1 = failed evidence; 0 = PASS."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from support import save,sha
EXPECTED={"E"+str(i).zfill(2) for i in range(1,16)}
def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item
def verdict(result,ids):
    return set(ids)==EXPECTED and len(ids)==15 and result.testsRun==15 and not result.errors and not result.failures and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
def main(batch):
    import test_events
    out=Path(__file__).parent/"evidence"/batch;out.mkdir(parents=True,exist_ok=False)
    os.environ["LORE_E_EVIDENCE_DIR"]=str(out.resolve())
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_events.EventContract)
    tests=list(flatten(suite));ids=[t._testMethodName.split("_")[1] for t in tests]
    cases=json.loads((ROOT/"design/g3/e/cases.json").read_text())
    manifest_ids=[c["id"] for c in cases["cases"]]
    inputs={str(p.relative_to(ROOT)):sha(p.read_bytes()) for base in [ROOT/"design/g3/e",Path(__file__).parent] for p in base.glob("*") if p.is_file() and p.suffix in {".py",".md",".json"}}
    metadata={"batch":batch,"command":sys.argv,"python":sys.version,"client":importlib.metadata.version("nats-py"),"case_ids":ids,"inputs":inputs,"R_gate":os.environ.get("LORE_R_GATE"),"modules":{"E":os.environ.get("LORE_EVENT_MODULE","lore.events"),"R":os.environ.get("LORE_CONTROL_MODULE","lore.control")}}
    if set(ids)!=EXPECTED or len(ids)!=15 or set(manifest_ids)!=EXPECTED or len(manifest_ids)!=15:
        save(out/"result.json",{**metadata,"status":"FAIL","reason":"fixed case inventory mismatch"});return 1
    preparations=unittest.defaultTestLoader.loadTestsFromNames(["test_oracle","test_runner","test_fixture","test_receipts"])
    with (out/"preparation-controls.log").open("w") as log:preflight=unittest.TextTestRunner(stream=log,verbosity=2).run(preparations)
    if preflight.testsRun!=9 or not preflight.wasSuccessful() or preflight.skipped or preflight.expectedFailures:
        save(out/"result.json",{**metadata,"status":"FAIL","reason":"mandatory oracle/fixture/runner preparation controls failed or skipped","preparation_tests":preflight.testsRun});return 1
    with (out/"unittest.log").open("w") as log:result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    passed=verdict(result,ids)
    only_missing=result.testsRun==15 and len(result.errors)==15 and all("MISSING" in error for _,error in result.errors)
    status="PASS" if passed else "MISSING" if only_missing else "FAIL"
    save(out/"result.json",{**metadata,"status":status,"preparation_tests":preflight.testsRun,"tests_run":result.testsRun,"errors":[{"test":str(t),"traceback":e} for t,e in result.errors],"failures":[{"test":str(t),"traceback":e} for t,e in result.failures],"skipped":result.skipped,"expected_failures":result.expectedFailures,"unexpected_successes":[str(t) for t in result.unexpectedSuccesses]})
    print(json.dumps({"batch":batch,"status":status,"preparation_tests":preflight.testsRun,"tests_run":result.testsRun,"errors":len(result.errors),"failures":len(result.failures),"skipped":len(result.skipped)}))
    return 0 if passed else 2 if only_missing else 1
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("batch")
    raise SystemExit(main(parser.parse_args().batch))
