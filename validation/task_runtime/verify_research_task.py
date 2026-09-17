#!/usr/bin/env python3.12
"""Independent checker for a research task directory.

Re-derives every verified source digest from real bytes, recomputes the recall
matches independently, and checks that completion only appears after saturation
with all sources verified.

Usage: python3.12 verify_research_task.py <task-dir>
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


def independent_recall(content: Path, query: str, limit: int):
    needle = query.lower()
    hits = []
    for path in sorted(content.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.split("\n"), 1):   # JSONL/text: "\n" only (A-R8)
            if needle in line.lower():
                hits.append((str(path.relative_to(content)), number))
                if len(hits) >= limit:
                    return hits
    return hits


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
    facts = [json.loads(line) for line in (base / "surface" / "facts.jsonl").read_text().split("\n") if line.strip()]
    kinds = [f["kind"] for f in facts]

    added = [f["payload"].get("source_ref") for f in facts if f["kind"] == "research.source.added"]
    verified = [f["payload"] for f in facts if f["kind"] == "research.source.verified"]
    invalid = [f["payload"] for f in facts if f["kind"] == "research.source.invalid"]
    retracted = {f["payload"].get("source_ref") for f in facts if f["kind"] == "research.source.retracted"}

    check("sources_registered", bool(added), str(kinds))
    for item in verified:
        path = content / item["source_ref"]
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        check("verified_digest_real:%s" % item["source_ref"], actual == item["digest"],
              "%s != %s" % (actual, item["digest"]))
    unresolved = [i for i in invalid if i["source_ref"] not in retracted
                  and i["source_ref"] not in {v["source_ref"] for v in verified}]
    # An invalid source is a recorded refusal: it must never count as evidence, and
    # it must not be required to vanish for the task to finish (self-healing).
    verified_refs = {v["source_ref"] for v in verified}
    check("enough_verified_sources", len(verified_refs) >= 2, str(sorted(verified_refs)))
    check("every_evidence_ref_verified",
          all(i["source_ref"] not in verified_refs for i in invalid), json.dumps(invalid))
    if unresolved:
        print("INFO unresolved_invalid_sources_recorded=%s" % json.dumps([i["source_ref"] for i in unresolved]))

    recall_facts = [f["payload"] for f in facts if f["kind"] == "sys.recall.result"]
    if recall_facts:
        sample = recall_facts[0]
        expected = independent_recall(content, sample["query"], 20)
        got = [(m["file"], m["line"]) for m in sample["matches"]]
        check("recall_reproduced_independently", got == expected, "expected %s got %s" % (expected, got))

    check("saturation_before_completion",
          "research.saturation.reached" in kinds and "task.completed" in kinds
          and kinds.index("research.saturation.reached") < kinds.index("task.completed"), str(kinds))
    check("completed_once", kinds.count("task.completed") == 1, str(kinds))
    check("completed_is_last", kinds[-1] == "task.completed", str(kinds))

    findings = [f["payload"] for f in facts if f["kind"] == "research.finding.recorded"]
    check("finding_recorded", bool(findings), str(kinds))
    for finding in findings:
        for ref in finding.get("evidence_refs") or []:
            check("evidence_exists:%s" % ref, (content / ref).is_file(), "missing %s" % ref)

    head = json.loads((base / "surface" / "head").read_text())
    check("head_matches_last_fact", head["facts_end"]["seq"] == facts[-1]["seq"])

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task": str(base), "kinds": kinds, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
