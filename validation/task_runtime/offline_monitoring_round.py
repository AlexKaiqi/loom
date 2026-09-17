#!/usr/bin/env python3.12
"""Offline case: monitoring triggers on time or an external signal, never by polling."""
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lore_task import facts as facts_mod
from lore_task import layout, ledger
from lore_task import provider
from lore_task import round as round_mod

CHECK = [
    json.dumps({"action": {"type": "shell", "script": "test -f ready.flag && echo READY || echo NOT_READY"}}),
    json.dumps({"action": {"type": "emit", "kind": "monitor.condition.met",
                           "payload": {"monitor_id": "m1", "evidence_refs": ["ready.flag"]}}}),
]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-mon-"))
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # 1) deadline path: not due -> no trigger; after the deadline -> one Round
    base = layout.create_task(root, "m-deadline", ROOT / "lore_harness" / "monitoring")
    deadline = int(time.time()) + 2
    round_mod.admit(base, "cond-1", "monitor.condition.set",
                     {"monitor_id": "m1", "predicate": "content/ready.flag exists",
                      "check": "test -f ready.flag", "deadline_epoch": deadline})
    before = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("not_due_no_trigger", before.get("status") == "no_trigger", json.dumps(before))
    (base / "surface" / "content" / "ready.flag").write_text("ready\n")
    time.sleep(3)
    after = round_mod.run_round(base, provider.FauxProvider(CHECK), max_steps=4)
    kinds = [f["kind"] for f in facts_mod.read_facts(base)]
    check("due_triggers_round", after.get("status") == "committed", json.dumps(after))
    check("condition_met_once", kinds.count("monitor.condition.met") == 1, str(kinds))
    check("check_ran", any(f["kind"] == "sys.tool.result" for f in facts_mod.read_facts(base)), str(kinds))
    closed = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("closed_no_trigger", closed.get("status") == "no_trigger", json.dumps(closed))

    # 2) signal path: a far deadline, but an external signal opens the Round
    base2 = layout.create_task(root, "m-signal", ROOT / "lore_harness" / "monitoring")
    round_mod.admit(base2, "cond-2", "monitor.condition.set",
                     {"monitor_id": "m2", "predicate": "external signal",
                      "deadline_epoch": int(time.time()) + 86400})
    idle = round_mod.run_round(base2, provider.FauxProvider([]), max_steps=1)
    check("far_deadline_idle", idle.get("status") == "no_trigger", json.dumps(idle))
    round_mod.admit(base2, "sig-1", "monitor.signal", {"monitor_id": "m2", "detail": "upstream changed"})
    fired = round_mod.run_round(base2, provider.FauxProvider([
        json.dumps({"action": {"type": "emit", "kind": "monitor.condition.expired",
                               "payload": {"monitor_id": "m2", "reason": "signal only, condition not verifiable"}}})]),
        max_steps=2)
    kinds2 = [f["kind"] for f in facts_mod.read_facts(base2)]
    check("signal_triggers_round", fired.get("status") == "committed", json.dumps(fired))
    check("expired_declared", kinds2.count("monitor.condition.expired") == 1, str(kinds2))
    check("no_polling_residue", ledger.round_count(base2) == 1, str(ledger.round_count(base2)))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task_root": str(root)}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
