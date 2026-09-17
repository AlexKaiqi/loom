#!/usr/bin/env python3.12
"""Independent checker for an ask-user work directory (reads only on-disk artifacts).

Usage: python3.12 verify_ask_user_work.py <work-dir>
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
    ap.add_argument("work")
    args = ap.parse_args()
    base = Path(args.work)
    content = base / "surface" / "content"
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    work = json.loads((base / "work.json").read_text())
    check("harness_digest_matches", tree_digest(base / "harness") == work["harness"]["digest"])

    facts = [json.loads(l) for l in (base / "surface" / "facts.jsonl").read_text().split("\n") if l.strip()]
    kinds = [f["kind"] for f in facts]
    expected = ["work.objective.set", "ask.requested", "ask.answered", "sys.tool.result", "work.completed"]
    check("kinds_exact", kinds == expected, str(kinds))
    check("asked_once", kinds.count("ask.requested") == 1, str(kinds))
    check("answered_once", kinds.count("ask.answered") == 1, str(kinds))
    check("completed_once", kinds.count("work.completed") == 1, str(kinds))

    answers = [f["payload"] for f in facts if f["kind"] == "ask.answered"]
    answer_file = content / "answer.md"
    if answers and answer_file.is_file():
        # semantic criterion: the file holds the greeting the user actually answered
        check("answer_used", answer_file.read_text().strip() == str(answers[0].get("answer", "")).strip(),
              repr(answer_file.read_text()[:60]))
    else:
        check("answer_used", False, "missing answer fact or answer.md")

    head = json.loads((base / "surface" / "head").read_text())
    check("head_matches_last_fact",
          head["facts_end"]["seq"] == facts[-1]["seq"] and head["facts_end"]["digest"] == facts[-1]["digest"])
    commits = [json.loads(l) for l in (base / "ledger" / "rounds.jsonl").read_text().split("\n")
               if l.strip() and json.loads(l).get("phase", "commit") == "commit"]
    check("two_committed_rounds", len(commits) == 2, str(len(commits)))
    admitted = [json.loads(l) for l in (base / "ledger" / "admission.jsonl").read_text().split("\n") if l.strip()]
    check("admissions_accepted", len(admitted) == 2 and all(a.get("decision") == "accepted" for a in admitted),
          json.dumps(admitted))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work": str(base), "kinds": kinds, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
