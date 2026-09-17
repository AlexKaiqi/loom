#!/usr/bin/env python3.12
"""Offline case: cross-task delegation with wants+grants authorization.

Two independent task directories, one event channel each way; an unauthorized
delivery is refused and recorded; the parent never touches the child's content.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lore_task import facts as facts_mod
from lore_task import layout, ledger
from lore_task import provider
from lore_task import round as round_mod


def kinds_of(base):
    return [f["kind"] for f in facts_mod.read_facts(base)]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-deleg-"))
    parent = layout.create_task(root, "parent-1", ROOT / "lore_harness" / "delegation_parent")
    child = layout.create_task(root, "child-1", ROOT / "lore_harness" / "delegation_child")
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    round_mod.ingest(parent, "obj-1", "task.objective.set",
                     {"objective": "get the child to produce report.md", "child": "child-1",
                      "scope": "write report.md whose exact content is sum=10"})

    # parent Round 1: delegate
    r1 = round_mod.run_round(parent, provider.FauxProvider([
        json.dumps({"action": {"type": "emit", "kind": "task.delegated",
                               "payload": {"child": "child-1", "scope": "write report.md whose exact content is sum=10",
                                           "input_refs": []}}})]), max_steps=3)
    delegated = [f for f in facts_mod.read_facts(parent) if f["kind"] == "task.delegated"]
    check("parent_delegated", r1.get("status") == "committed" and len(delegated) == 1, json.dumps(r1))
    waiting = round_mod.run_round(parent, provider.FauxProvider([]), max_steps=1)
    check("parent_waits_without_report", waiting.get("status") == "no_trigger", json.dumps(waiting))

    # unauthorized delivery first (no relations declared yet)
    refused = round_mod.deliver(parent, child, "d-refused", "task.delegated", delegated[0]["payload"])
    check("unauthorized_refused", refused["delivered"] is False and "wants" in refused["reason"], json.dumps(refused))

    # declare both directions: consumer wants, sender grants
    round_mod.relate(child, want=("parent-1", ["task.delegated"]))
    round_mod.relate(parent, grant=("child-1", ["task.delegated"]))
    round_mod.relate(parent, want=("child-1", ["task.reported"]))
    round_mod.relate(child, grant=("parent-1", ["task.reported"]))

    delivered = round_mod.deliver(parent, child, "d-1", "task.delegated", delegated[0]["payload"])
    check("authorized_delivered", delivered.get("delivered") is True, json.dumps(delivered))

    # child Round 1: do the scoped work and report
    r2 = round_mod.run_round(child, provider.FauxProvider([
        json.dumps({"action": {"type": "shell", "script": "printf 'sum=10\\n' > report.md"}}),
        json.dumps({"action": {"type": "emit", "kind": "task.reported",
                               "payload": {"result_ref": "report.md", "evidence_refs": ["report.md"]}}})]), max_steps=4)
    child_kinds = kinds_of(child)
    check("child_reported", r2.get("status") == "committed" and child_kinds.count("task.reported") == 1, str(child_kinds))
    check("child_completed_derived", child_kinds.count("task.completed") == 1, str(child_kinds))
    deliverable = child / "surface" / "content" / "report.md"
    check("child_deliverable_bytes_exact", deliverable.is_file() and deliverable.read_bytes() == b"sum=10\n",
          repr(deliverable.read_bytes()[:20]) if deliverable.is_file() else "missing")

    reported = [f for f in facts_mod.read_facts(child) if f["kind"] == "task.reported"][0]["payload"]
    back = round_mod.deliver(child, parent, "d-2", "task.reported", reported)
    check("report_delivered_to_parent", back.get("delivered") is True, json.dumps(back))

    # parent Round 2: acknowledge
    r3 = round_mod.run_round(parent, provider.FauxProvider([
        json.dumps({"action": {"type": "emit", "kind": "task.completed",
                               "payload": {"evidence_refs": ["task.reported"]}}})]), max_steps=3)
    parent_kinds = kinds_of(parent)
    check("parent_completed", r3.get("status") == "committed" and parent_kinds.count("task.completed") == 1, str(parent_kinds))

    # separation and audit
    check("parent_content_empty", not any((parent / "surface" / "content").iterdir()))
    check("child_content_untouched_by_parent", (child / "surface" / "content" / "report.md").is_file())
    rejected_rows = [r for r in ledger.read_jsonl(child / "ledger" / "admission.jsonl")
                     if r.get("decision") == "rejected"]
    check("refusal_recorded", len(rejected_rows) == 1 and rejected_rows[0]["reason"] == "missing wants", json.dumps(rejected_rows))
    accepted_rows = [r for r in ledger.read_jsonl(child / "ledger" / "admission.jsonl")
                     if r.get("decision") == "accepted"]
    check("accepted_from_parent", len(accepted_rows) == 1 and accepted_rows[0].get("from") == "parent-1",
          json.dumps(accepted_rows))
    check("no_relations_no_authority",
          "task.delegated" not in kinds_of(child) or delivered.get("delivered") is True)

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task_root": str(root), "parent": parent_kinds, "child": child_kinds}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
