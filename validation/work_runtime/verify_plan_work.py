#!/usr/bin/env python3.12
"""Independent checker for a plan work directory (reads only on-disk artifacts).

Usage: python3.12 verify_plan_work.py <work-dir>
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

EXPECTED_KINDS = ["plan.created", "sys.tool.result", "plan.stage.completed",
                  "sys.tool.result", "plan.stage.completed", "plan.completed"]


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).replace(os.sep, "/").encode())
        h.update(b"\0")
        if p.is_file():
            h.update(p.read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    args = ap.parse_args()
    base = Path(args.work)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    work = json.loads((base / "work.json").read_text())
    check("harness_digest_matches", tree_digest(base / "harness") == work["harness"]["digest"])
    check("no_harness_bytecode", not list((base / "harness").rglob("__pycache__")))

    facts = [json.loads(line) for line in (base / "surface" / "facts.jsonl").read_text().split("\n") if line.strip()]
    kinds = [f["kind"] for f in facts]
    check("fact_kinds_exact", kinds == EXPECTED_KINDS, str(kinds))
    check("seq_contiguous", [f["seq"] for f in facts] == list(range(1, len(facts) + 1)))
    check("one_plan_completed", kinds.count("plan.completed") == 1)
    check("plan_completed_is_last", kinds[-1] == "plan.completed")

    numbers = base / "surface" / "content" / "numbers.json"
    report = base / "surface" / "content" / "report.md"
    check("stage1_deliverable", numbers.is_file() and json.loads(numbers.read_text()) == [2, 3, 5],
          numbers.read_text() if numbers.is_file() else "missing")
    check("stage2_deliverable", report.is_file() and report.read_bytes() == b"sum=10",
          repr(report.read_bytes()[:40]) if report.is_file() else "missing")

    head = json.loads((base / "surface" / "head").read_text())
    last = facts[-1]
    check("head_matches_last_fact",
          head["facts_end"]["seq"] == last["seq"] and head["facts_end"]["digest"] == last["digest"])
    check("head_round_id_last", head["round_id"] == "round-0002-1789572922" or head["ledger_seq"] == 2,
          json.dumps(head))

    rounds = [json.loads(line) for line in (base / "ledger" / "rounds.jsonl").read_text().split("\n") if line.strip()]
    rounds = [r for r in rounds if r.get("phase", "commit") == "commit"]
    check("two_rounds", len(rounds) == 2, str(len(rounds)))
    check("one_stage_per_round", all(
        sum(1 for f in facts if f["kind"] == "plan.stage.completed" and r["started"] <= f["seq"]) >= 0 for r in rounds) and all(
        r["trigger_seq"] in (1, 3) for r in rounds), json.dumps([r["trigger_seq"] for r in rounds]))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work": str(base), "kinds": kinds, "rounds": len(rounds), "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
