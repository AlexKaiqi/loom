#!/usr/bin/env python3.12
"""Offline case: one goal-mode Round with a faux provider (no network, no credentials).

Assertions re-read on-disk artifacts (facts.jsonl, head, ledger, session, content)
instead of trusting the runtime's own return value.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lore_work import facts as facts_mod
from lore_work import layout, ledger
from lore_work import provider
from lore_work import round as round_mod

RESPONSES = [
    json.dumps({"action": {"type": "shell", "script": "printf 'sum=10\\n' > report.md"}}),
    json.dumps({"action": {"type": "emit", "kind": "work.completed", "payload": {"evidence_refs": ["report.md"]}}}),
    json.dumps({"action": {"type": "final", "text": "done"}}),
]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-work-"))
    base = layout.create_work(root, "t-1", ROOT / "lore_harness")
    round_mod.admit(base, "obj-1", "work.objective.set",
                     {"objective": "write sum=10 report", "acceptance": ["report.md contains sum=10"]})
    result = round_mod.run_round(base, provider.FauxProvider(RESPONSES), max_steps=5)

    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    check("round_committed", result.get("status") == "committed", json.dumps(result))
    admitted = ledger.read_jsonl(base / "ledger" / "admission.jsonl")
    check("admission_accepted", len(admitted) == 1 and admitted[0]["decision"] == "accepted", json.dumps(admitted))
    facts = facts_mod.read_facts(base)
    kinds = [f["kind"] for f in facts]
    core = [kind for kind in kinds if kind != "sys.context.usage"]
    check("fact_kinds", core == ["work.objective.set", "sys.tool.result", "work.completed"], str(kinds))
    report = base / "surface" / "content" / "report.md"
    check("content_written_bytes_exact", report.is_file() and report.read_bytes() == b"sum=10\n",
          repr(report.read_bytes()[:20]) if report.is_file() else "missing")
    head = layout.read_json(base / "surface" / "head")
    check("head_commit",
          head["facts_end"]["seq"] == facts[-1]["seq"] and head["round_id"] == result.get("round_id")
          and head["ledger_seq"] == 1,
          json.dumps(head))
    records = ledger.round_records(base)
    check("round_record", len(records) == 1 and records[0]["trigger_seq"] == 1, json.dumps(records))
    check("session_log", (base / "session" / "rounds" / (result.get("round_id", "") + ".jsonl")).is_file())
    check("harness_untouched",
          layout.tree_digest(base / "harness") == layout.read_json(base / "work.json")["harness"]["digest"])
    again = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("no_second_trigger", again.get("status") == "no_trigger", json.dumps(again))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work_root": str(root), "round": result}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
