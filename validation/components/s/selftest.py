"""Verifier capability checks from actual Pi artifacts; never S component evidence."""
from pathlib import Path
import copy,hashlib,json,sys,subprocess
from oracle import evaluate_case,InvalidEvidence,pi_jsonl
from runner import evaluate,CASES
HERE=Path(__file__).resolve().parent
out=HERE/"evidence"/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
source=HERE/"evidence/public-preparation-003/single-state"
spec=json.loads(CASES.read_text());case=spec["cases"][0]
def artifact(name,data):
    (out/name).write_bytes(data)
    return {"path":name,"sha256":hashlib.sha256(data).hexdigest(),"origin":"trusted_external_collector"}
accepted=(source/"accepted.jsonl").read_bytes()
ev={"session:accepted":artifact("accepted.jsonl",accepted),"journal:provider":artifact("provider.jsonl",b""),"journal:tools":artifact("tools.jsonl",b"")}
checks={};details={}
def check(label,call,expected):
    try:got=call();status=got["status"]
    except InvalidEvidence as error:status="INVALID";got={"error":str(error)}
    checks[label]=status==expected;details[label]={"expected":expected,"observed":status,"result":got}
check("actual_accepted_original_positive",lambda:evaluate_case(case,ev,out),"PASS")
raw=pi_jsonl(accepted);original=pi_jsonl((source/"single-final.jsonl").read_bytes())
assistant=copy.deepcopy(next(e for e in original["entries"] if e.get("message",{}).get("role")=="assistant"))
assistant["seq"]=max(x["seq"] for x in raw["records"])+1
bad=accepted+json.dumps(assistant,ensure_ascii=False).encode()+b"\n"
bad_ev=copy.deepcopy(ev);bad_ev["session:accepted"]=artifact("bad-eager-provider.jsonl",bad)
check("known_bad_actual_assistant_before_drive",lambda:evaluate_case(case,bad_ev,out),"FAIL")
missing=copy.deepcopy(ev);missing.pop("journal:provider")
check("missing_source_not_killed",lambda:evaluate_case(case,missing,out),"INVALID")
wrong=copy.deepcopy(ev);wrong["session:accepted"]["sha256"]="0"*64
check("wrong_hash",lambda:evaluate_case(case,wrong,out),"INVALID")
missing_path=copy.deepcopy(case);missing_path["assertions"].append({"source":"session:accepted","path":["does_not_exist"],"op":"eq","value":True})
check("missing_path_not_killed",lambda:evaluate_case(missing_path,ev,out),"INVALID")
empty={"scope":"TRUSTED_COLLECTOR_OUTPUT","cases_sha256":hashlib.sha256(CASES.read_bytes()).hexdigest(),"case_evidence":{}}
(out/"empty.json").write_text(json.dumps(empty))
check("empty_run",lambda:evaluate(out/"empty.json"),"INVALID")
wrong_origin=copy.deepcopy(ev);wrong_origin["session:accepted"]["origin"]="sut_claim"
check("sut_self_report",lambda:evaluate_case(case,wrong_origin,out),"INVALID")
empty_case=copy.deepcopy(case);empty_case["assertions"]=[]
check("empty_assertions",lambda:evaluate_case(empty_case,ev,out),"INVALID")
(out/"empty-driver.py").write_text("raise SystemExit(0)\n")
proc=subprocess.run([sys.executable,str(HERE/"runner.py"),"--driver",str(out/"empty-driver.py"),"--run-dir",str(out/"empty-driver-run")],capture_output=True,text=True,timeout=10)
(out/"empty-driver.stdout").write_text(proc.stdout);(out/"empty-driver.stderr").write_text(proc.stderr)
checks["zero_exit_without_execution_rejected"]=proc.returncode==2 and json.loads(proc.stdout)["status"]=="INVALID"
result={"scope":"ORACLE_SELFTEST_ONLY","checks":checks,"details":details,"case_inventory":len(spec["cases"]),"formal_assertion_inventory":sum(len(c["assertions"]) for c in spec["cases"]),"inputs":{str(p.relative_to(HERE.parents[2])):hashlib.sha256(p.read_bytes()).hexdigest() for p in [CASES,HERE/"oracle.py",HERE/"runner.py",HERE/"selftest.py"]},"status":"PREPARATION_CHECKS_PASS" if all(checks.values()) else "FAIL"}
(out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"status":result["status"],"checks":checks}))
raise SystemExit(0 if all(checks.values()) else 1)
