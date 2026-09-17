#!/usr/bin/env python3.12
"""Independent checker for a coding work directory.

Reads only on-disk artifacts, re-derives digests, cross-checks the declared test
outcome against the recorded tool exit code, and re-runs the test itself in the
authorized userspace.

Usage: python3.12 verify_coding_work.py <work-dir>
"""
import argparse
import hashlib
import json
import os
import subprocess
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
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    work = json.loads((base / "work.json").read_text())
    check("harness_digest_matches", tree_digest(base / "harness") == work["harness"]["digest"])
    check("workspace_declared", len(work.get("userspaces", [])) == 1, json.dumps(work.get("userspaces")))
    userspace = Path(work["userspaces"][0]["path"])

    facts = [json.loads(line) for line in (base / "surface" / "facts.jsonl").read_text().split("\n") if line.strip()]
    kinds = [f["kind"] for f in facts]
    tools = [f["payload"] for f in facts if f["kind"] == "sys.tool.result"]
    check("tool_targets_workspace", tools and all(t.get("target") == "userspace" for t in tools),
          json.dumps([t.get("target") for t in tools]))
    check("cwd_is_workspace", all(t.get("cwd") == str(userspace) for t in tools),
          json.dumps([t.get("cwd") for t in tools]))

    test_runs = [t for t in tools if "test_add.py" in (t.get("script") or "")]
    check("test_actually_run", bool(test_runs), "no tool result ran test_add.py")
    check("recorded_test_exit_zero", bool(test_runs) and all(t["exit"] == 0 for t in test_runs),
          json.dumps([t.get("exit") for t in test_runs]))

    declared = [f["payload"] for f in facts if f["kind"] == "code.test.declared"]
    check("test_declared_once", len(declared) == 1, str(kinds))
    check("declared_matches_recorded",
          bool(declared) and declared[0].get("outcome") == "pass" and bool(test_runs) and test_runs[-1]["exit"] == 0,
          json.dumps(declared))

    check("add_py_present", (userspace / "add.py").is_file())
    check("test_py_present", (userspace / "test_add.py").is_file())
    check("completed_once", kinds.count("work.completed") == 1, str(kinds))
    check("content_no_side_channel",
          not any((base / "surface" / "content").iterdir()),
          "content is empty for this objective (no notes were needed)")

    proc = subprocess.run([sys.executable, "test_add.py"], cwd=str(userspace),
                          capture_output=True, text=True, timeout=60)
    check("independent_rerun_passes", proc.returncode == 0, proc.stdout + proc.stderr)

    head = json.loads((base / "surface" / "head").read_text())
    check("head_matches_last_fact", head["facts_end"]["seq"] == facts[-1]["seq"])

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work": str(base), "userspace": str(userspace), "kinds": kinds, "ok": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
