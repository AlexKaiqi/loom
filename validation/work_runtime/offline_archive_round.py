#!/usr/bin/env python3.12
"""Offline case: archive mode folds older content losslessly and records it.

No network, no credentials. Assertions read on-disk artifacts.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkout import skip_unless

from lore_work import facts as facts_mod
from lore_work import layout, ledger
from lore_work import provider
from lore_work import round as round_mod

MOVED = [
    {"from": "old-1.md", "to": "archive/old-1.md"},
    {"from": "old-2.md", "to": "archive/old-2.md"},
]
RESPONSE = [
    json.dumps({"action": {"type": "shell", "script": "mkdir -p archive && mv old-1.md old-2.md archive/"}}),
    json.dumps({"action": {"type": "emit", "kind": "archive.performed",
                           "payload": {"scope": "content", "moved": MOVED,
                                       "original_refs": ["archive/old-1.md", "archive/old-2.md"],
                                       "mode": "lossless"}}}),
]


def main() -> int:
    if skip_unless("archive.performed"):
        return 0
    root = Path(tempfile.mkdtemp(prefix="lore-archive-"))
    base = layout.create_work(root, "a-1", ROOT / "lore_harness")
    content = base / "surface" / "content"
    originals = {"old-1.md": "first note\n", "old-2.md": "second note\n",
                 "recent-1.md": "recent one\n", "recent-2.md": "recent two\n"}
    for name, text in originals.items():
        (content / name).write_text(text)
    round_mod.admit(base, "arc-1", "archive.requested", {"reason": "context pressure"})

    result = round_mod.run_round(base, provider.FauxProvider(RESPONSE), max_steps=4)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    check("round_committed", result.get("status") == "committed", json.dumps(result))
    facts = facts_mod.read_facts(base)
    kinds = [f["kind"] for f in facts]
    check("usage_observed", "sys.context.usage" in kinds, str(kinds))
    check("performed_once", kinds.count("archive.performed") == 1, str(kinds))
    check("stopped_after_performed", result.get("steps") == 2, json.dumps(result.get("steps")))

    check("archive_dir_exists", (content / "archive").is_dir())
    check("lossless_bytes",
          (content / "archive" / "old-1.md").read_text() == originals["old-1.md"]
          and (content / "archive" / "old-2.md").read_text() == originals["old-2.md"])
    check("recent_kept", (content / "recent-1.md").is_file() and (content / "recent-2.md").is_file())
    check("nothing_deleted", not (content / "old-1.md").exists() and not (content / "old-2.md").exists())

    performed = [f for f in facts if f["kind"] == "archive.performed"][0]["payload"]
    check("moved_recorded", performed.get("moved") == MOVED and performed.get("mode") == "lossless",
          json.dumps(performed))
    check("original_refs", performed.get("original_refs") == ["archive/old-1.md", "archive/old-2.md"])

    head = layout.read_json(base / "surface" / "head")
    check("head_matches_last_fact", head["facts_end"]["seq"] == facts[-1]["seq"])
    check("one_round", ledger.round_count(base) == 1)
    check("harness_digest_unchanged",
          layout.tree_digest(base / "harness") == layout.read_json(base / "work.json")["harness"]["digest"])

    again = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("no_immediate_rearchive", again.get("status") == "no_trigger", json.dumps(again))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work_root": str(root), "kinds": kinds}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
