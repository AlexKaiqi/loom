#!/usr/bin/env python3.12
"""Independent checker for a monitoring work directory (reads only on-disk artifacts).

Usage: python3.12 verify_monitoring_work.py <work-dir>
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
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    work = json.loads((base / "work.json").read_text())
    check("harness_digest_matches", tree_digest(base / "harness") == work["harness"]["digest"])

    facts = [json.loads(l) for l in (base / "surface" / "facts.jsonl").read_text().split("\n") if l.strip()]
    kinds = [f["kind"] for f in facts]
    check("kinds_exact", kinds == ["monitor.condition.set", "sys.tool.result", "monitor.condition.met"], str(kinds))
    tools = [f["payload"] for f in facts if f["kind"] == "sys.tool.result"]
    check("check_ran_for_real", bool(tools) and tools[0].get("exit") == 0 and "READY" in (tools[0].get("stdout") or ""),
          json.dumps(tools))
    met = [f["payload"] for f in facts if f["kind"] == "monitor.condition.met"]
    check("condition_met_once", len(met) == 1, json.dumps(met))
    check("met_has_monitor_id", bool(met) and bool(met[0].get("monitor_id")), json.dumps(met)[:150])

    head = json.loads((base / "surface" / "head").read_text())
    check("head_matches_last_fact",
          head["facts_end"]["seq"] == facts[-1]["seq"] and head["facts_end"]["digest"] == facts[-1]["digest"])
    commits = [json.loads(l) for l in (base / "ledger" / "rounds.jsonl").read_text().split("\n")
               if l.strip() and json.loads(l).get("phase", "commit") == "commit"]
    check("one_committed_round", len(commits) == 1, str(len(commits)))
    admitted = [json.loads(l) for l in (base / "ledger" / "admission.jsonl").read_text().split("\n") if l.strip()]
    check("condition_admitted", len(admitted) == 1 and admitted[0].get("decision") == "accepted", json.dumps(admitted))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work": str(base), "kinds": kinds, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
