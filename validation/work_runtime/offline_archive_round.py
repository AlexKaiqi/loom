#!/usr/bin/env python3.12
"""Offline case: archive bounds the projection listing; Surface files stay put.

No network, no credentials. Assertions read on-disk artifacts and session bytes.
"""
import json
import os
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

RESPONSES = [
    json.dumps({"action": {"type": "emit", "kind": "work.completed",
                           "payload": {"evidence_refs": ["recent-2.md"]}}}),
]


def main() -> int:
    if skip_unless("archive.performed"):
        return 0
    root = Path(tempfile.mkdtemp(prefix="lore-archive-"))
    base = layout.create_work(root, "a-1", ROOT / "lore_harness")
    content = base / "surface" / "content"
    originals = {"old-1.md": "first note\n", "old-2.md": "second note\n",
                 "recent-1.md": "recent one\n", "recent-2.md": "recent two\n"}
    mtime = 1_700_000_000
    for name, text in originals.items():
        path = content / name
        path.write_text(text)
        os.utime(path, (mtime, mtime))
        mtime += 60
    round_mod.admit(base, "obj-1", "work.objective.set",
                    {"objective": "leave the notes in place", "acceptance": ["files remain"]})

    result = round_mod.run_round(base, provider.FauxProvider(RESPONSES), max_steps=4)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    check("round_committed", result.get("status") == "committed", json.dumps(result))
    facts = facts_mod.read_facts(base)
    kinds = [f["kind"] for f in facts]
    check("usage_observed", "sys.context.usage" in kinds, str(kinds))
    check("performed_once", kinds.count("archive.performed") == 1, str(kinds))

    for name, text in originals.items():
        path = content / name
        check("surface_kept_%s" % name, path.is_file() and path.read_text() == text,
              "missing" if not path.is_file() else path.read_text())
    check("no_archive_dir", not (content / "archive").exists())

    performed = [f for f in facts if f["kind"] == "archive.performed"][0]["payload"]
    check("mode_lossless", performed.get("mode") == "lossless", json.dumps(performed))
    omitted = performed.get("omitted") or []
    shown = performed.get("shown") or []
    check("omitted_some", len(omitted) >= 1, json.dumps(performed))
    check("shown_bounded", len(shown) <= 2, json.dumps(performed))
    check("omitted_still_on_surface", all((content / name).is_file() for name in omitted), json.dumps(omitted))
    check("original_refs_are_surface_paths",
          set(performed.get("original_refs") or []) == set(omitted), json.dumps(performed))

    session = base / "session" / "rounds" / (result.get("round_id", "") + ".jsonl")
    first = json.loads(session.read_text(encoding="utf-8").split("\n", 1)[0]) if session.is_file() else {}
    user = next((m.get("content") or "" for m in (first.get("request") or []) if m.get("role") == "user"), "")
    check("projection_mentions_omitted", "omitted" in user.lower() or "still on Surface" in user, user[:400])
    for name in shown:
        check("shown_listed_%s" % name, name in user, user[:300])

    head = layout.read_json(base / "surface" / "head")
    check("head_matches_last_fact", head["facts_end"]["seq"] == facts[-1]["seq"])
    check("one_round", ledger.round_count(base) == 1)
    check("harness_digest_unchanged",
          layout.tree_digest(base / "harness") == layout.read_json(base / "work.json")["harness"]["digest"])

    again = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("no_second_trigger", again.get("status") == "no_trigger", json.dumps(again))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work_root": str(root), "kinds": kinds, "performed": performed}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
