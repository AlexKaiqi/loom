#!/usr/bin/env python3.12
"""Offline case: plan mode advances exactly one stage per Round, then derives plan.completed.

No network, no credentials. Assertions read on-disk artifacts.
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

STAGE_1 = [
    json.dumps({"action": {"type": "shell", "script": "printf 'stage one\\n' > stage-1.md"}}),
    json.dumps({"action": {"type": "emit", "kind": "plan.stage.completed",
                           "payload": {"stage_id": "s1", "evidence_refs": ["stage-1.md"]}}}),
]
STAGE_2 = [
    json.dumps({"action": {"type": "shell", "script": "printf 'stage two\\n' > stage-2.md"}}),
    json.dumps({"action": {"type": "emit", "kind": "plan.stage.completed",
                           "payload": {"stage_id": "s2", "evidence_refs": ["stage-2.md"]}}}),
]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-plan-"))
    base = layout.create_task(root, "p-1", ROOT / "lore_harness" / "plan")
    round_mod.ingest(base, "plan-1", "plan.created", {
        "plan_id": "p1",
        "stages": [
            {"id": "s1", "title": "stage one", "deliverable": "stage-1.md"},
            {"id": "s2", "title": "stage two", "deliverable": "stage-2.md"},
        ],
    })
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    r1 = round_mod.run_round(base, provider.FauxProvider(STAGE_1), max_steps=4)
    kinds_1 = [f["kind"] for f in facts_mod.read_facts(base)]
    check("round1_committed", r1.get("status") == "committed", json.dumps(r1))
    check("round1_one_stage", kinds_1.count("plan.stage.completed") == 1, str(kinds_1))
    check("no_premature_plan_completed", "plan.completed" not in kinds_1, str(kinds_1))
    check("round1_stops_after_stage", r1.get("steps") == 2, json.dumps(r1.get("steps")))

    r2 = round_mod.run_round(base, provider.FauxProvider(STAGE_2), max_steps=4)
    facts_2 = facts_mod.read_facts(base)
    kinds_2 = [f["kind"] for f in facts_2]
    check("round2_committed", r2.get("status") == "committed", json.dumps(r2))
    check("two_stages_completed", kinds_2.count("plan.stage.completed") == 2, str(kinds_2))
    check("plan_completed_derived", kinds_2.count("plan.completed") == 1, str(kinds_2))
    check("derived_last", kinds_2[-1] == "plan.completed", str(kinds_2))
    check("two_round_records", ledger.round_count(base) == 2, str(ledger.round_count(base)))
    check("stage_files", (base / "surface" / "content" / "stage-1.md").is_file()
          and (base / "surface" / "content" / "stage-2.md").is_file())

    r3 = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("no_third_round", r3.get("status") == "no_trigger", json.dumps(r3))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task_root": str(root), "facts": [f["kind"] for f in facts_2]}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
