#!/usr/bin/env python3.12
"""Offline case: pin reconstructs objective and acceptance at the front of projection.

No network, no credentials. Assertions read the session request bytes.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkout import skip_unless_pin

from lore_work import layout
from lore_work import provider
from lore_work import round as round_mod

ACCEPTANCE = ["report.md contains sum=10"]
RESPONSES = [
    json.dumps({"action": {"type": "shell", "script": "printf 'sum=10\\n' > report.md"}}),
    json.dumps({"action": {"type": "emit", "kind": "work.completed", "payload": {"evidence_refs": ["report.md"]}}}),
]


def main() -> int:
    if skip_unless_pin():
        return 0
    root = Path(tempfile.mkdtemp(prefix="lore-pin-"))
    base = layout.create_work(root, "p-1", ROOT / "lore_harness")
    round_mod.admit(base, "obj-1", "work.objective.set",
                    {"objective": "write sum=10 report", "acceptance": ACCEPTANCE})
    result = round_mod.run_round(base, provider.FauxProvider(RESPONSES), max_steps=4)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    check("round_committed", result.get("status") == "committed", json.dumps(result))
    session = base / "session" / "rounds" / (result.get("round_id", "") + ".jsonl")
    check("session_log", session.is_file())
    first = json.loads(session.read_text(encoding="utf-8").split("\n", 1)[0]) if session.is_file() else {}
    messages = (first.get("request") or [])
    user = next((m.get("content") or "" for m in messages if m.get("role") == "user"), "")
    check("pinned_heading_first", user.lstrip().startswith("# Pinned"), user[:200])
    check("acceptance_in_projection", json.dumps(ACCEPTANCE, ensure_ascii=False) in user, user[:400])
    check("objective_in_projection", "write sum=10 report" in user)

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work_root": str(root), "round": result.get("status")}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
