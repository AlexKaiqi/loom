"""Run frozen finite G1 models and retain every positive and negative trace."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import traceback
from .observer import ProtocolError, evaluate, merge, validate_inventory, verify_hashes
from .audit import audit_batch, load_plan
from .frozen_loader import FrozenModels

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "durability": ("cases-durability.json", "freeze-001.json", "DurabilityModel"),
    "durability-supplement": ("cases-durability-supplement.json", "freeze-004.json", "DurabilityModel"),
    "strategy": ("cases-strategy.json", "freeze-001.json", "StrategyModel"),
    "boundaries": ("cases-boundaries.json", "freeze-002.json", "BoundaryModel"),
}

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")

def trajectories(suite):
    for case in suite["cases"]:
        yield case
        for extra in case.get("extra_trajectories", []):
            yield {**extra, "id": case["id"]+"--"+extra["id"], "initial_state": merge(case["initial_state"], extra.get("initial_state_overrides", {}))}

def variants(case):
    main = case["known_bad_variant"]
    return [main, *main.get("additional_mechanisms", [])]

def execute(model_type, initial, actions, variant):
    model = model_type(deepcopy(initial), variant=variant)
    trace = {"initial": deepcopy(model.snapshot())}
    for index, action in enumerate(actions, 1):
        point = action.get("id", f"a{index}")
        if point in trace:
            raise ProtocolError(f"duplicate action checkpoint {point}")
        try:
            model.apply(action["op"], deepcopy(action["args"]))
        except Exception as error:
            error.g1_trace = trace
            raise
        trace[point] = deepcopy(model.snapshot())
    return trace

def run_one(model_type, case, defaults, variant, null_maps, target):
    name = None if variant is None else variant.get("name", variant.get("mechanism"))
    if variant is not None and not name:
        raise ProtocolError("missing mutation mechanism")
    record = {"case": case["id"], "variant": name, "status": "FAIL"}
    try:
        trace = execute(model_type, merge(defaults, case["initial_state"]), case["actions"], name)
        record["trace"] = trace
        checks = evaluate(case["expected"], trace, null_maps)
        failures = [row for row in checks if not row["passed"]]
        relevant = set(variant.get("must_violate", variant.get("violates", []))) if variant else set()
        killed = bool(failures) and (not relevant or any(row["assertion"] in relevant for row in failures))
        passed = killed if variant else not failures
        record.update(status="PASS" if passed else "FAIL", expected_assertions=len(case["expected"]), evaluated_assertions=len(checks), checks=checks, trace=trace, relevant_assertions=sorted(relevant), mutation_rejected=killed if variant else None)
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        record.setdefault("trace", getattr(error, "g1_trace", {}))
        # A model crash is not a valid killed semantic mutation.
    write_json(target, record)
    return {key: value for key, value in record.items() if key not in {"checks", "trace", "traceback"}}

def run(suite_names, batch):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", batch) or batch in {".", ".."}:
        raise ProtocolError("batch must be a simple new directory name")
    output = ROOT / "simulations" / "evidence" / batch
    if output.exists():
        raise ProtocolError("evidence batch already exists; old results must not be overwritten")
    loaded, bindings = {}, {}
    for family in suite_names:
        casefile, freezefile, class_name = SUITES[family]
        frozen = json.loads((ROOT / "design/g1" / freezefile).read_text())
        verify_hashes(ROOT, frozen["inputs_sha256"])
        bindings.update(frozen["inputs_sha256"])
        bindings["design/g1/"+freezefile] = hashlib.sha256((ROOT / "design/g1" / freezefile).read_bytes()).hexdigest()
        suite = json.loads((ROOT / "design/g1" / casefile).read_text())
        cases = list(trajectories(suite))
        validate_inventory([case["id"] for case in cases], [case["id"] for case in cases])
        for case in cases:
            if not case["actions"] or not case["expected"]:
                raise ProtocolError("empty actions or assertions")
        loaded[family] = (suite, cases, class_name)
    prefixes = tuple({"durability": "durability", "boundaries": "boundar", "strategy": "strategy"}[f.split("-")[0]] for f in suite_names)
    sources = [x for x in (ROOT / "simulations").glob("*.py") if x.name in {"__init__.py", "observer.py", "run_g1.py", "audit.py", "frozen_loader.py"} or x.name.startswith(prefixes)]
    code_hashes = {str(x.relative_to(ROOT)): hashlib.sha256(x.read_bytes()).hexdigest() for x in sources}
    plan, plan_hashes = load_plan(ROOT, suite_names)
    bindings.update(plan_hashes)
    frozen_models = FrozenModels(ROOT, [x for x in sources if x.name.startswith(prefixes)])
    try:
        for family, (suite, cases, class_name) in list(loaded.items()):
            loaded[family] = (suite, cases, frozen_models.load(family.split("-")[0], class_name))
        verify_hashes(ROOT, code_hashes)
    except Exception:
        frozen_models.close()
        raise
    output.mkdir(parents=True)
    summary = {"scope": "G1 finite models under declared fixture assumptions; no real Runtime properties verified", "batch": batch, "time_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version, "platform": platform.platform(), "command": sys.argv, "cwd": str(ROOT), "inputs_sha256": bindings, "implementation_sha256": code_hashes, "runs": [], "errors": []}
    expected_runs = [row["run_id"] for row in plan]
    for family, (suite, cases, model_type) in loaded.items():
        defaults = suite.get("observer_defaults", {})
        null_maps = ("request", "decision", "registration", "event_bindings") if family.split("-")[0] == "durability" else ()
        for case in cases:
            for variant in [None, *variants(case)]:
                name = "correct" if variant is None else variant.get("name", variant.get("mechanism"))
                ident = f"{family}--{case['id']}--{name}"
                result = run_one(model_type, case, defaults, variant, null_maps, output / (ident+".json"))
                result.update(run_id=ident, artifact=ident+".json", sha256=hashlib.sha256((output / (ident+".json")).read_bytes()).hexdigest())
                summary["runs"].append(result)
    summary["errors"].extend(audit_batch(ROOT, output, summary, plan))
    try:
        verify_hashes(ROOT, bindings)
        verify_hashes(ROOT, code_hashes)
    except ProtocolError as error:
        summary["errors"].append(str(error))
    frozen_models.close()
    summary["positive_runs"] = sum(r["variant"] is None for r in summary["runs"])
    summary["negative_runs"] = len(summary["runs"])-summary["positive_runs"]
    summary["status"] = "PASS" if not summary["errors"] and all(r["status"] == "PASS" for r in summary["runs"]) else "FAIL"
    write_json(output / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in ["batch", "status", "positive_runs", "negative_runs", "errors"]}))
    for result in summary["runs"]:
        if result["status"] != "PASS":
            print(json.dumps(result, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suites", nargs="+", choices=sorted(SUITES), required=True)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.suites, args.batch))
