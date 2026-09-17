#!/usr/bin/env python3.12
"""Independent checker for a system-design work directory.

Reads only on-disk artifacts: re-derives every frozen unit's digest from the real
file bytes, checks dependency order, and confirms completion only appears after
all units are frozen.

Usage: python3.12 verify_design_work.py <work-dir>
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
    ap.add_argument("work")
    args = ap.parse_args()
    base = Path(args.work)
    content = base / "surface" / "content"
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    work = json.loads((base / "work.json").read_text())
    check("harness_digest_matches", tree_digest(base / "harness") == work["harness"]["digest"])
    check("no_harness_bytecode", not list((base / "harness").rglob("__pycache__")))

    facts = [json.loads(line) for line in (base / "surface" / "facts.jsonl").read_text().split("\n") if line.strip()]
    kinds = [f["kind"] for f in facts]
    spec = [f["payload"] for f in facts if f["kind"] == "design.objective.set"][0]
    unit_ids = [u["id"] for u in spec["units"]]
    frozen = [f["payload"] for f in facts if f["kind"] == "design.unit.frozen"]

    check("each_unit_frozen_once", sorted(f["unit_id"] for f in frozen) == sorted(unit_ids), str(kinds))
    for fact in frozen:
        path = content / fact["file"]
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        check("digest_matches_bytes:%s" % fact["unit_id"], actual == fact["file_digest"],
              "%s != %s" % (actual, fact["file_digest"]))
    check("no_freeze_violations", "design.freeze.violation" not in kinds, str(kinds))
    check("no_stale_units", "design.unit.stale" not in kinds, str(kinds))
    check("no_rejected_declarations", "sys.declaration.rejected" not in kinds, str(kinds))
    check("completed_once", kinds.count("work.completed") == 1, str(kinds))
    check("completed_is_last", kinds[-1] == "work.completed", str(kinds))
    accepted_order = [f["payload"]["unit_id"] for f in facts if f["kind"] == "design.unit.accepted"]
    check("dependency_order", accepted_order == unit_ids, str(accepted_order))

    head = json.loads((base / "surface" / "head").read_text())
    check("head_matches_last_fact", head["facts_end"]["seq"] == facts[-1]["seq"] and head["facts_end"]["digest"] == facts[-1]["digest"])
    rounds = [json.loads(line) for line in (base / "ledger" / "rounds.jsonl").read_text().split("\n") if line.strip()]
    commits = [r for r in rounds if r.get("phase", "commit") == "commit"]
    check("one_round_per_unit", len(commits) == len(unit_ids), str(len(commits)))
    check("no_interrupted_rounds", all(r.get("phase") != "start" for r in rounds[len(rounds) - 1:]),
          "last ledger row is an uncommitted start")

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work": str(base), "units": unit_ids, "kinds": kinds, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
