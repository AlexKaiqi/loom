"""Fail-closed independent offline oracle and external collector entry."""
from pathlib import Path
import argparse,sys,json,subprocess,hashlib
from oracle import InvalidEvidence, strict_json, evaluate_case
ROOT=Path(__file__).resolve().parents[3]
CASES=ROOT/"design/g3/s/cases.json"
def evaluate(bundle_path, selected=None):
    spec=strict_json(CASES.read_text())
    cases=spec["cases"]
    ids=[c["id"] for c in cases]
    if len(ids)!=len(set(ids)) or not ids or len(ids)!=spec["case_count"]:
        raise InvalidEvidence("empty/duplicate case discovery")
    if any(not c["assertions"] for c in cases):
        raise InvalidEvidence("empty assertion discovery")
    bundle=strict_json(bundle_path.read_text())
    if bundle.get("cases_sha256")!=hashlib.sha256(CASES.read_bytes()).hexdigest():
        raise InvalidEvidence("wrong preregistered cases version")
    if bundle.get("scope")!="TRUSTED_COLLECTOR_OUTPUT":
        raise InvalidEvidence("not independent collector output")
    if selected:
        cases=[c for c in cases if c["id"]==selected]
        if not cases:raise InvalidEvidence("unknown selected case")
    required={c["id"] for c in cases}
    supplied=bundle.get("case_evidence")
    if not isinstance(supplied,dict) or set(supplied)!=required:
        raise InvalidEvidence("missing/extra case evidence or empty run")
    outputs=[evaluate_case(case,supplied[case["id"]],bundle_path.parent) for case in cases]
    return {"scope":"DIAGNOSTIC_SUBSET" if selected else "FINITE_S_CASE_OBSERVATIONS",
            "status":"PASS" if all(r["status"]=="PASS" for r in outputs) else "FAIL",
            "component_approval":False,
            "approval_note":"Requires independently frozen actual collector/SUT provenance and G4 E01-E05 gate; fixture/oracle preparation cannot grant component PASS.",
            "case_count":len(outputs),"assertion_count":sum(len(r["assertions"]) for r in outputs),"results":outputs}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bundle",type=Path);p.add_argument("--case")
    p.add_argument("--driver",type=Path);p.add_argument("--run-dir",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    try:
        bundle=args.bundle
        if args.driver:
            if bundle or args.case or not args.run_dir:
                raise InvalidEvidence("driver requires fresh run-dir, not bundle/subset")
            args.run_dir.mkdir(parents=True,exist_ok=False)
            spec=strict_json(CASES.read_text())
            plan={"protocol":"S-TRUSTED-COLLECTOR/1","cases_sha256":hashlib.sha256(CASES.read_bytes()).hexdigest(),
                  "cases":[{k:c[k] for k in ("id","setup","actions")} for c in spec["cases"]]}
            planfile=args.run_dir/"action-plan.json";planfile.write_text(json.dumps(plan,ensure_ascii=False,indent=2))
            command=[sys.executable,str(args.driver.resolve()),"--plan",str(planfile.resolve()),"--output",str(args.run_dir.resolve())]
            proc=subprocess.run(command,capture_output=True,text=True,timeout=900)
            (args.run_dir/"collector.stdout").write_text(proc.stdout);(args.run_dir/"collector.stderr").write_text(proc.stderr)
            (args.run_dir/"collector-command.json").write_text(json.dumps({"argv":command,"returncode":proc.returncode,"driver_sha256":hashlib.sha256(args.driver.read_bytes()).hexdigest()},indent=2))
            if proc.returncode:raise InvalidEvidence("collector failed, exit "+str(proc.returncode))
            bundle=args.run_dir/"bundle.json"
        if bundle is None or not bundle.is_file():
            raise InvalidEvidence("actual collector/bundle missing; no component run")
        result=evaluate(bundle,args.case)
        exitcode=0 if result["status"]=="PASS" else 1
    except (InvalidEvidence,OSError,ValueError,UnicodeError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        result={"status":"INVALID","component_approval":False,"error":str(error)}
        exitcode=2
    serialized=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if args.output:args.output.write_text(serialized)
    print(serialized,end="");return exitcode
if __name__=="__main__":raise SystemExit(main())
