#!/usr/bin/env python3.12
"""Offline case: ask-user asks instead of guessing, waits as data, resumes on the answer.

No network, no credentials. Assertions read on-disk artifacts.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lore_task import facts as facts_mod
from lore_task import layout, ledger
from lore_task import provider
from lore_task import round as round_mod

ROUND_1 = [json.dumps({"action": {"type": "emit", "kind": "ask.requested",
                                  "payload": {"ask_id": "q1", "question": "Which greeting should I write?",
                                              "options": ["hello", "bonjour"]}}})]
ROUND_2 = [
    json.dumps({"action": {"type": "shell", "script": "printf 'bonjour\\n' > answer.md"}}),
    json.dumps({"action": {"type": "emit", "kind": "task.completed", "payload": {"evidence_refs": ["answer.md"]}}}),
]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-ask-"))
    base = layout.create_task(root, "q-1", ROOT / "lore_harness" / "ask_user")
    round_mod.ingest(base, "obj-1", "task.objective.set",
                     {"objective": "write the greeting the user chooses into answer.md",
                      "acceptance": ["answer.md contains the chosen greeting"]})
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    r1 = round_mod.run_round(base, provider.FauxProvider(ROUND_1), max_steps=4)
    kinds_1 = [f["kind"] for f in facts_mod.read_facts(base)]
    check("round1_committed", r1.get("status") == "committed", json.dumps(r1))
    check("asked_once", kinds_1.count("ask.requested") == 1, str(kinds_1))
    check("no_completion_yet", "task.completed" not in kinds_1, str(kinds_1))
    check("round1_stops_at_ask", r1.get("steps") == 1, json.dumps(r1.get("steps")))
    check("content_untouched", not any((base / "surface" / "content").iterdir()))

    waiting = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("waits_without_answer", waiting.get("status") == "no_trigger", json.dumps(waiting))

    result = round_mod.ingest(base, "ans-1", "ask.answered", {"ask_id": "q1", "answer": "bonjour", "by": "user"})
    check("answer_admitted", result["admission"]["decision"] == "accepted", json.dumps(result["admission"]))

    r2 = round_mod.run_round(base, provider.FauxProvider(ROUND_2), max_steps=4)
    kinds_2 = [f["kind"] for f in facts_mod.read_facts(base)]
    check("round2_committed", r2.get("status") == "committed", json.dumps(r2))
    check("answered_visible", "ask.answered" in kinds_2, str(kinds_2))
    check("completed_once", kinds_2.count("task.completed") == 1, str(kinds_2))
    answer = base / "surface" / "content" / "answer.md"
    check("answer_used_bytes_exact", answer.is_file() and answer.read_bytes() == b"bonjour\n",
          repr(answer.read_bytes()[:20]) if answer.is_file() else "missing")
    check("two_rounds", ledger.round_count(base) == 2, str(ledger.round_count(base)))

    done = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("no_round_after_completion", done.get("status") == "no_trigger", json.dumps(done))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task_root": str(root), "kinds": kinds_2}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
