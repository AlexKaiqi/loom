#!/usr/bin/env python3.12
"""Independent checker for an archive task directory (reads only on-disk artifacts).

Usage: python3.12 verify_archive_task.py <task-dir>
"""
import argparse
import hashlib
import json
import os
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
    args = ap.parse_args()
    base = Path(args.task)
    content = base / "surface" / "content"
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    task = json.loads((base / "task.json").read_text())
    check("harness_digest_matches", tree_digest(base / "harness") == task["harness"]["digest"])
    check("no_harness_bytecode", not list((base / "harness").rglob("__pycache__")))

    facts = [json.loads(l) for l in (base / "surface" / "facts.jsonl").read_text().split("\n") if l.strip()]
    kinds = [f["kind"] for f in facts]
    check("usage_observed", any(k == "sys.context.usage" for k in kinds), str(kinds))
    check("performed_once", kinds.count("archive.performed") == 1, str(kinds))
    performed = [f["payload"] for f in facts if f["kind"] == "archive.performed"]
    if performed:
        payload = performed[0]
        check("mode_lossless", payload.get("mode") == "lossless", json.dumps(payload)[:200])
        moved = payload.get("moved") or []
        check("moved_listed", len(moved) >= 1, json.dumps(moved))
        check("originals_reachable", all((content / m["to"]).is_file() for m in moved), json.dumps(moved))
        check("original_refs_recorded",
              set(payload.get("original_refs") or []) == {m["to"] for m in moved}, json.dumps(payload)[:200])
    survivors = [str(p.relative_to(content)) for p in content.rglob("*") if p.is_file() and "archive/" not in str(p.relative_to(content))]
    check("recent_files_kept", len(survivors) >= 1, str(survivors))

    head = json.loads((base / "surface" / "head").read_text())
    check("head_matches_last_fact",
          head["facts_end"]["seq"] == facts[-1]["seq"] and head["facts_end"]["digest"] == facts[-1]["digest"])
    commits = [json.loads(l) for l in (base / "ledger" / "rounds.jsonl").read_text().split("\n")
               if l.strip() and json.loads(l).get("phase", "commit") == "commit"]
    check("one_committed_round", len(commits) == 1, str(len(commits)))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task": str(base), "kinds": kinds, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
