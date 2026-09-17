#!/usr/bin/env python3.12
"""Offline case: coding mode routes execution to an authorized userspace range.

Covers: unauthorized target refusal, real edit + test in the userspace, declared
change/test outcomes, completion, and that content/ (Surface notes) stays separate.
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

STEPS = [
    json.dumps({"action": {"type": "shell", "target": "userspace:secret",
                           "script": "echo should-not-run > /tmp/lore-escape.txt"}}),
    json.dumps({"action": {"type": "shell", "target": "userspace",
                           "script": "printf 'def add(a, b):\\n    return a + b\\n' > add.py"}}),
    json.dumps({"action": {"type": "shell", "target": "userspace",
                           "script": "printf 'import add\\nassert add.add(2, 3) == 5\\nprint(\"ok\")\\n' > test_add.py"
                                     " && python3 test_add.py"}}),
    json.dumps({"action": {"type": "emit", "kind": "code.change.declared",
                           "payload": {"summary": "add() plus its test", "files": ["add.py", "test_add.py"]}}}),
    json.dumps({"action": {"type": "emit", "kind": "code.test.declared",
                           "payload": {"command": "python3 test_add.py", "outcome": "pass",
                                       "evidence_refs": ["test_add.py"]}}}),
    json.dumps({"action": {"type": "emit", "kind": "work.completed", "payload": {"evidence_refs": ["add.py"]}}}),
]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-code-"))
    userspace = Path(tempfile.mkdtemp(prefix="lore-ws-"))
    base = layout.create_work(root, "code-1", ROOT / "lore_harness" / "coding",
                              userspaces=[{"id": userspace.name, "path": str(userspace), "mode": "rw"}])
    round_mod.admit(base, "obj-1", "work.objective.set",
                     {"objective": "add(a,b) plus a passing test", "acceptance": ["test_add.py exits 0"]})
    result = round_mod.run_round(base, provider.FauxProvider(STEPS), max_steps=8)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    check("round_committed", result.get("status") == "committed", json.dumps(result))
    facts = facts_mod.read_facts(base)
    kinds = [f["kind"] for f in facts]
    tools = [f["payload"] for f in facts if f["kind"] == "sys.tool.result"]
    check("unauthorized_target_refused", tools[0]["exit"] == 126 and "unauthorized" in tools[0]["stderr"],
          json.dumps(tools[0]))
    check("refusal_records_target", tools[0]["target"] == "userspace:secret", json.dumps(tools[0].get("target")))
    check("no_escape_effect", not Path("/tmp/lore-escape.txt").exists())
    check("workspace_used", tools[1]["target"] == "userspace" and tools[1]["cwd"] == str(userspace),
          json.dumps(tools[1]))
    check("code_written", (userspace / "add.py").is_file() and (userspace / "test_add.py").is_file())
    check("test_ran", tools[2]["exit"] == 0 and "ok" in (tools[2]["stdout"] or ""), json.dumps(tools[2]))
    check("change_declared", kinds.count("code.change.declared") == 1, str(kinds))
    check("test_declared", kinds.count("code.test.declared") == 1, str(kinds))
    check("completed_once", kinds.count("work.completed") == 1, str(kinds))
    check("content_untouched", not any((base / "surface" / "content").iterdir()))
    check("head_matches_last_fact",
          layout.read_json(base / "surface" / "head")["facts_end"]["seq"] == facts[-1]["seq"])
    check("one_round", ledger.round_count(base) == 1)
    check("harness_unchanged",
          layout.tree_digest(base / "harness") == layout.read_json(base / "work.json")["harness"]["digest"])
    again = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("no_second_round", again.get("status") == "no_trigger", json.dumps(again))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work_root": str(root), "userspace": str(userspace), "kinds": kinds}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
