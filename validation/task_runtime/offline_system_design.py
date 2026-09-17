#!/usr/bin/env python3.12
"""Offline case: system design freezes units, refuses stale bases, flags violations,
propagates staleness through dependencies, and only completes when every unit is frozen.

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

TWO_UNITS = {"objective": "design a two-part system", "units": [
    {"id": "u1", "title": "interfaces", "deliverable": "interface spec"},
    {"id": "u2", "title": "storage", "deliverable": "storage design", "depends_on": ["u1"]},
]}


def accepted(unit_id, base_rev):
    return json.dumps({"action": {"type": "emit", "kind": "design.unit.accepted",
                                  "base_rev": base_rev, "payload": {"unit_id": unit_id}}})


def write_unit(unit_id, text):
    return json.dumps({"action": {"type": "shell",
                                  "script": "mkdir -p units && printf '%s\\n' > units/%s.md" % (text, unit_id)}})


def revision(base):
    return layout.read_json(base / "surface" / "head")["revision"]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-design-"))
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # A) two units, dependency order, completion only after both are frozen
    a = layout.create_task(root, "d-two", ROOT / "lore_harness" / "system_design")
    round_mod.ingest(a, "obj-a", "design.objective.set", TWO_UNITS)
    r1 = round_mod.run_round(a, provider.FauxProvider([write_unit("u1", "interface v1"), accepted("u1", revision(a))]),
                             max_steps=4)
    kinds_a1 = [f["kind"] for f in facts_mod.read_facts(a)]
    check("A_round1_committed", r1.get("status") == "committed", json.dumps(r1))
    check("A_u1_frozen", kinds_a1.count("design.unit.frozen") == 1, str(kinds_a1))
    check("A_not_complete_yet", "task.completed" not in kinds_a1, str(kinds_a1))
    r2 = round_mod.run_round(a, provider.FauxProvider([write_unit("u2", "storage v1"), accepted("u2", revision(a))]),
                             max_steps=4)
    kinds_a2 = [f["kind"] for f in facts_mod.read_facts(a)]
    check("A_round2_committed", r2.get("status") == "committed", json.dumps(r2))
    check("A_two_frozen", kinds_a2.count("design.unit.frozen") == 2, str(kinds_a2))
    check("A_completed_once", kinds_a2.count("task.completed") == 1, str(kinds_a2))
    check("A_no_violations", "design.freeze.violation" not in kinds_a2, str(kinds_a2))
    stopped = round_mod.run_round(a, provider.FauxProvider([]), max_steps=1)
    check("A_stops_after_completion", stopped.get("status") == "no_trigger", json.dumps(stopped))

    # B) a stale base revision is refused by the runtime, then the correct one is accepted
    b = layout.create_task(root, "d-stale", ROOT / "lore_harness" / "system_design")
    round_mod.ingest(b, "obj-b", "design.objective.set",
                     {"objective": "one unit", "units": [{"id": "u1", "deliverable": "spec"}]})
    rb = round_mod.run_round(b, provider.FauxProvider([write_unit("u1", "spec"), accepted("u1", "sha256:stale"),
                                                       accepted("u1", revision(b))]), max_steps=4)
    kinds_b = [f["kind"] for f in facts_mod.read_facts(b)]
    check("B_round_committed", rb.get("status") == "committed", json.dumps(rb))
    check("B_stale_refused", kinds_b.count("sys.declaration.rejected") == 1, str(kinds_b))
    check("B_then_accepted", kinds_b.count("design.unit.accepted") == 1, str(kinds_b))
    check("B_frozen_and_completed",
          kinds_b.count("design.unit.frozen") == 1 and kinds_b.count("task.completed") == 1, str(kinds_b))

    # C) freeze violation on a rogue byte change, then amendment -> re-freeze -> stale dependent
    c = layout.create_task(root, "d-amend", ROOT / "lore_harness" / "system_design")
    round_mod.ingest(c, "obj-c", "design.objective.set", TWO_UNITS)
    round_mod.run_round(c, provider.FauxProvider([write_unit("u1", "interface v1"), accepted("u1", revision(c))]),
                        max_steps=4)
    (c / "surface" / "content" / "units" / "u1.md").write_text("interface v1 ROGUE EDIT\n")
    r = round_mod.run_round(c, provider.FauxProvider([write_unit("u2", "storage v1"), accepted("u2", revision(c))]),
                            max_steps=4)
    kinds_c = [f["kind"] for f in facts_mod.read_facts(c)]
    check("C_violation_detected", kinds_c.count("design.freeze.violation") == 1, str(kinds_c))
    check("C_completion_blocked", "task.completed" not in kinds_c, str(kinds_c))

    round_mod.ingest(c, "am-1", "design.amendment.requested", {"unit_id": "u1", "reason": "interface changed"})
    round_mod.ingest(c, "am-2", "design.amendment.accepted", {"unit_id": "u1", "reason": "approved"})
    round_mod.run_round(c, provider.FauxProvider([write_unit("u1", "interface v2"), accepted("u1", revision(c))]),
                        max_steps=4)
    kinds_c2 = [f["kind"] for f in facts_mod.read_facts(c)]
    check("C_refrozen_after_amendment", kinds_c2.count("design.unit.frozen") == 3, str(kinds_c2))
    check("C_dependent_marked_stale", kinds_c2.count("design.unit.stale") == 1, str(kinds_c2))
    check("C_still_not_complete", "task.completed" not in kinds_c2, str(kinds_c2))

    round_mod.run_round(c, provider.FauxProvider([write_unit("u2", "storage v2"), accepted("u2", revision(c))]),
                        max_steps=4)
    kinds_c3 = [f["kind"] for f in facts_mod.read_facts(c)]
    check("C_completed_after_reaccept", kinds_c3.count("task.completed") == 1, str(kinds_c3))
    check("C_two_rounds_recorded", ledger.round_count(c) >= 4, str(ledger.round_count(c)))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task_root": str(root), "task_c_kinds": kinds_c3}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
