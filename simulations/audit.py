"""Audit stored evidence against an inventory derived before execution."""
from hashlib import sha256
import json
from .observer import ProtocolError, canonical, evaluate, validate_inventory, verify_hashes

def load_plan(root, families):
    inventories = [("freeze-003.json", "execution-inventory.json")]
    if "durability-supplement" in families:
        inventories.append(("freeze-004.json", "execution-inventory-supplement.json"))
    rows, bindings = [], {}
    for freezefile, inventory in inventories:
        freeze_path = root / "design/g1" / freezefile
        freeze = json.loads(freeze_path.read_text())
        verify_hashes(root, freeze["inputs_sha256"])
        path = root / "design/g1" / inventory
        data = json.loads(path.read_text())
        verify_hashes(root, data["source_sha256"])
        rows.extend(row for row in data["runs"] if row["suite"] in families)
        bindings.update({str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in [path, freeze_path]})
    validate_inventory([row["run_id"] for row in rows], [row["run_id"] for row in rows])
    return rows, bindings

def expected_for(root, family, case_id):
    suite = json.loads((root / f"design/g1/cases-{family}.json").read_text())
    for main in suite["cases"]:
        if main["id"] == case_id:
            return main["expected"]
        for extra in main.get("extra_trajectories", []):
            if main["id"]+"--"+extra["id"] == case_id:
                return extra["expected"]
    raise ProtocolError("unregistered case in evidence inventory")

def audit_batch(root, output, summary, plan):
    errors = []
    try:
        validate_inventory([r["run_id"] for r in plan], [r["run_id"] for r in summary["runs"]])
    except ProtocolError as error:
        return [str(error)]
    actual = {r["run_id"]: r for r in summary["runs"]}
    for requirement in plan:
        row = actual[requirement["run_id"]]
        try:
            file = output / row["artifact"]
            if not file.is_file() or sha256(file.read_bytes()).hexdigest() != row["sha256"]:
                raise ProtocolError("missing or modified raw artifact")
            record = json.loads(file.read_text())
            if record.get("error"):
                raise ProtocolError("model/observation error is invalid evidence: "+record["error"])
            if record["case"] != requirement["case"] or record["variant"] != requirement["variant"]:
                raise ProtocolError("artifact identity mismatch")
            if list(record["trace"]) != requirement["checkpoints"]:
                raise ProtocolError("missing or unexpected raw checkpoints")
            expected = expected_for(root, requirement["suite"], requirement["case"])
            null_maps = ("request", "decision", "registration", "event_bindings") if requirement["suite"].split("-")[0] == "durability" else ()
            checks = evaluate(expected, record["trace"], null_maps)
            if [[c["assertion"], c["checkpoint"]] for c in checks] != requirement["checks"]:
                raise ProtocolError("missing, extra or reordered assertion evaluation")
            if canonical(checks) != canonical(record["checks"]):
                raise ProtocolError("stored checks disagree with raw trace re-evaluation")
            failures = [c for c in checks if not c["passed"]]
            relevant = set(requirement["relevant_assertions"])
            passed = not failures if requirement["variant"] is None else bool(failures) and (not relevant or any(c["assertion"] in relevant for c in failures))
            if not passed or record["status"] != "PASS" or row["status"] != "PASS":
                raise ProtocolError("frozen semantic criteria not satisfied")
        except (ProtocolError, KeyError, ValueError, TypeError) as error:
            errors.append(requirement["run_id"]+": "+str(error))
    return errors
