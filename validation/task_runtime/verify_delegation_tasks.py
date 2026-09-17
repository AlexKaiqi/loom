#!/usr/bin/env python3.12
"""Independent checker for a delegation pair (parent + child task directories).

Usage: python3.12 verify_delegation_tasks.py <root> <parent-task-id> <child-task-id>
"""
import argparse
import json
from pathlib import Path


def facts_of(base):
    return [json.loads(line) for line in (base / "surface" / "facts.jsonl").read_text().split("\n") if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("parent")
    ap.add_argument("child")
    args = ap.parse_args()
    root = Path(args.root)
    parent, child = root / args.parent, root / args.child
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    pf, cf = facts_of(parent), facts_of(child)
    pk = [f["kind"] for f in pf]
    ck = [f["kind"] for f in cf]

    check("parent_delegated_once", pk.count("task.delegated") == 1, str(pk))
    check("parent_received_report", pk.count("task.reported") == 1, str(pk))
    check("parent_completed_once", pk.count("task.completed") == 1, str(pk))
    check("parent_order", pk.index("task.delegated") < pk.index("task.reported") < pk.index("task.completed"), str(pk))
    check("parent_content_untouched", not any((parent / "surface" / "content").iterdir()))

    check("child_got_delegation", ck.count("task.delegated") == 1, str(ck))
    check("child_reported_once", ck.count("task.reported") == 1, str(ck))
    check("child_completed_once", ck.count("task.completed") == 1, str(ck))
    report = child / "surface" / "content" / "report.md"
    check("child_deliverable_real", report.is_file() and report.read_bytes() == b"sum=10",
          repr(report.read_bytes()[:40]) if report.is_file() else "missing")

    parent_relations = json.loads((parent / "task.json").read_text()).get("relations", {})
    child_relations = json.loads((child / "task.json").read_text()).get("relations", {})
    check("parent_grants_child", any(g.get("peer") == args.child and "task.delegated" in g.get("kinds", [])
                                     for g in parent_relations.get("grants", [])), json.dumps(parent_relations))
    check("parent_wants_child_report", any(w.get("peer") == args.child and "task.reported" in w.get("kinds", [])
                                           for w in parent_relations.get("wants", [])), json.dumps(parent_relations))
    check("child_wants_parent_delegation", any(w.get("peer") == args.parent and "task.delegated" in w.get("kinds", [])
                                               for w in child_relations.get("wants", [])), json.dumps(child_relations))

    child_admission = [json.loads(l) for l in (child / "ledger" / "admission.jsonl").read_text().split("\n") if l.strip()]
    parent_admission = [json.loads(l) for l in (parent / "ledger" / "admission.jsonl").read_text().split("\n") if l.strip()]
    check("child_admission_from_parent",
          any(r.get("from") == args.parent and r.get("decision") == "accepted" for r in child_admission),
          json.dumps(child_admission))
    check("parent_admission_from_child",
          any(r.get("from") == args.child and r.get("decision") == "accepted" for r in parent_admission),
          json.dumps(parent_admission))

    for name, base in (("parent", parent), ("child", child)):
        head = json.loads((base / "surface" / "head").read_text())
        facts = facts_of(base)
        check("%s_head_matches_last_fact" % name,
              facts and head["facts_end"]["seq"] == facts[-1]["seq"] and head["facts_end"]["digest"] == facts[-1]["digest"])

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"parent": pk, "child": ck, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
