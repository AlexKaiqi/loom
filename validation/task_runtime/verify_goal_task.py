#!/usr/bin/env python3.12
"""Independent checker for a goal task directory: reads only on-disk artifacts.

Usage: python3.12 verify_goal_task.py <task-dir> [--expect-sum 10]

It does not import the runtime; it re-derives digests and re-reads facts, head,
ledger, content and the harness tree from bytes.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


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
    ap.add_argument("task")
    ap.add_argument("--expect-sum", default="10")
    args = ap.parse_args()
    base = Path(args.task)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    task = json.loads((base / "task.json").read_text())
    check("layout_version", task.get("layout_version") == 1, json.dumps(task.get("layout_version")))
    check("harness_digest_matches", tree_digest(base / "harness") == task["harness"]["digest"],
          "%s != %s" % (tree_digest(base / "harness"), task["harness"]["digest"]))
    check("no_harness_bytecode", not list((base / "harness").rglob("__pycache__")))

    facts = [json.loads(line) for line in (base / "surface" / "facts.jsonl").read_text().split("\n") if line.strip()]
    check("facts_seq_contiguous", [f["seq"] for f in facts] == list(range(1, len(facts) + 1)), str([f["seq"] for f in facts]))
    kinds = [f["kind"] for f in facts]
    check("single_completion", kinds.count("task.completed") == 1, str(kinds))
    check("declared_kinds_only",
          set(kinds) <= {"sys.tool.result", "task.objective.set", "user.message", "task.phase.changed", "task.completed"},
          str(set(kinds)))

    report = base / "surface" / "content" / "report.md"
    expect = ("sum=%s" % args.expect_sum).encode("utf-8")
    check("report_content_bytes_exact", report.is_file() and report.read_bytes() == expect,
          repr(report.read_bytes()[:40]) if report.is_file() else "missing")
    numbers = base / "surface" / "content" / "numbers.json"
    check("numbers_content", numbers.is_file() and json.loads(numbers.read_text()) == [2, 3, 5],
          numbers.read_text() if numbers.is_file() else "missing")

    head = json.loads((base / "surface" / "head").read_text())
    last = facts[-1] if facts else None
    check("head_points_at_last_fact",
          last is not None and head["facts_end"]["seq"] == last["seq"] and head["facts_end"]["digest"] == last["digest"],
          json.dumps(head["facts_end"]))

    rounds = [json.loads(line) for line in (base / "ledger" / "rounds.jsonl").read_text().split("\n") if line.strip()]
    rounds = [r for r in rounds if r.get("phase", "commit") == "commit"]
    check("one_round_record", len(rounds) == 1, str(len(rounds)))
    if rounds:
        rec = rounds[0]
        check("round_revision_matches_content", rec["revision"] == tree_digest(base / "surface" / "content"),
              "%s != %s" % (rec["revision"], tree_digest(base / "surface" / "content")))
        check("round_session_exists", (base / rec["session"]).is_file(), rec["session"])

    admitted = [json.loads(line) for line in (base / "ledger" / "admission.jsonl").read_text().split("\n") if line.strip()]
    check("admission_single_accept", len(admitted) == 1 and admitted[0]["decision"] == "accepted", json.dumps(admitted))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task": str(base), "facts": len(facts), "kinds": kinds, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
