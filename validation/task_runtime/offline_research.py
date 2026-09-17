#!/usr/bin/env python3.12
"""Offline case: research retrieves with the runtime recall primitive and cites real sources."""
import hashlib
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

CORPUS = {
    "a-notes.md": "the cache stores hot data to avoid recomputation\n",
    "b-design.md": "cache eviction policy: LRU with a TTL of 300 seconds\n",
    "c-misc.md": "unrelated note about logging\n",
}


def digest(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-research-"))
    base = layout.create_task(root, "r-1", ROOT / "lore_harness" / "research")
    content = base / "surface" / "content"
    for name, text in CORPUS.items():
        (content / name).write_text(text)
    round_mod.ingest(base, "q-1", "research.question.set",
                     {"question": "What does the corpus say about cache eviction and TTL?",
                      "scope": "cite the files"})

    steps_round_1 = [
        json.dumps({"action": {"type": "recall", "query": "cache", "limit": 10}}),
        json.dumps({"action": {"type": "shell",
                               "script": "printf 'eviction is LRU with TTL 300s (a-notes, b-design)\\n' > synthesis.md"}}),
        json.dumps({"action": {"type": "emit", "kind": "research.source.added",
                               "payload": {"source_ref": "a-notes.md", "note": "cache notes"}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.finding.recorded",
                               "payload": {"finding_ref": "synthesis.md",
                                           "evidence_refs": ["a-notes.md", "b-design.md"]}}}),
    ]
    # second Round adds the second verified source; the harness then derives
    # saturation and completion on its own (the model declares nothing terminal)
    steps_round_2 = [
        json.dumps({"action": {"type": "emit", "kind": "research.source.added",
                               "payload": {"source_ref": "b-design.md", "note": "eviction policy"}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.saturation.reached",
                               "payload": {"reason": "claim: two sources cover the question"}}}),
    ]
    result = round_mod.run_round(base, provider.FauxProvider(steps_round_1), max_steps=8)
    result2 = round_mod.run_round(base, provider.FauxProvider(steps_round_2), max_steps=4)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    facts = facts_mod.read_facts(base)
    kinds = [f["kind"] for f in facts]
    check("round_committed", result.get("status") == "committed", json.dumps(result))
    check("second_round_committed", result2.get("status") == "committed", json.dumps(result2))
    check("two_rounds", ledger.round_count(base) == 2, str(ledger.round_count(base)))
    recall = [f["payload"] for f in facts if f["kind"] == "sys.recall.result"]
    check("recall_ran", len(recall) == 1, str(kinds))
    expected = [("a-notes.md", 1), ("b-design.md", 1)]
    got = [(m["file"], m["line"]) for m in (recall[0]["matches"] if recall else [])]
    check("recall_matches_corpus", got == expected, "expected %s got %s" % (expected, got))
    check("recall_deterministic_shape",
          bool(recall) and all({"file", "line", "snippet"} <= set(m) for m in recall[0]["matches"]),
          json.dumps(recall[:1], ensure_ascii=False)[:200])

    check("sources_registered", kinds.count("research.source.added") == 2, str(kinds))
    check("finding_recorded", kinds.count("research.finding.recorded") == 1, str(kinds))
    check("saturation_reached", kinds.count("research.saturation.reached") == 1, str(kinds))
    check("completed_derived", kinds.count("task.completed") == 1 and kinds[-1] == "task.completed", str(kinds))
    check("synthesis_written", (content / "synthesis.md").is_file())
    verified = [f["payload"] for f in facts if f["kind"] == "research.source.verified"]
    check("sources_verified_from_bytes",
          len(verified) == 2 and all(v["digest"] == digest(CORPUS[v["source_ref"]]) for v in verified),
          json.dumps(verified))
    check("head_matches_last_fact",
          layout.read_json(base / "surface" / "head")["facts_end"]["seq"] == facts[-1]["seq"])
    again = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("stops_after_completion", again.get("status") == "no_trigger", json.dumps(again))

    # second task: a fabricated source digest is caught, blocks completion, then is corrected
    base2 = layout.create_task(root, "r-2", ROOT / "lore_harness" / "research")
    content2 = base2 / "surface" / "content"
    (content2 / "a-notes.md").write_text(CORPUS["a-notes.md"])
    (content2 / "b-design.md").write_text(CORPUS["b-design.md"])
    round_mod.ingest(base2, "q-2", "research.question.set", {"question": "cache?", "scope": "corpus"})
    round_mod.run_round(base2, provider.FauxProvider([
        json.dumps({"action": {"type": "emit", "kind": "research.source.added",
                               "payload": {"source_ref": "missing.md"}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.saturation.reached",
                               "payload": {"reason": "claims answered"}}})]), max_steps=4)
    kinds2 = [f["kind"] for f in facts_mod.read_facts(base2)]
    check("missing_source_flagged", kinds2.count("research.source.invalid") == 1, str(kinds2))
    check("completion_blocked_by_invalid", "task.completed" not in kinds2, str(kinds2))
    round_mod.run_round(base2, provider.FauxProvider([
        json.dumps({"action": {"type": "emit", "kind": "research.source.added",
                               "payload": {"source_ref": "a-notes.md"}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.source.added",
                               "payload": {"source_ref": "b-design.md"}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.finding.recorded",
                               "payload": {"finding_ref": "a-notes.md", "evidence_refs": ["a-notes.md"]}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.saturation.reached",
                               "payload": {"reason": "now verified"}}})]),
        max_steps=5)
    kinds2b = [f["kind"] for f in facts_mod.read_facts(base2)]
    check("self_heals_after_invalid_source", kinds2b.count("task.completed") == 1, str(kinds2b))
    check("invalid_record_kept", kinds2b.count("research.source.invalid") == 1, str(kinds2b))

    # third task: saturation and completion DERIVED from verified evidence
    base3 = layout.create_task(root, "r-3", ROOT / "lore_harness" / "research")
    content3 = base3 / "surface" / "content"
    (content3 / "a-notes.md").write_text(CORPUS["a-notes.md"])
    (content3 / "b-design.md").write_text(CORPUS["b-design.md"])
    round_mod.ingest(base3, "q-3", "research.question.set", {"question": "cache?", "scope": "corpus"})
    round_mod.run_round(base3, provider.FauxProvider([
        json.dumps({"action": {"type": "emit", "kind": "research.source.added",
                               "payload": {"source_ref": "a-notes.md"}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.source.added",
                               "payload": {"source_ref": "b-design.md"}}}),
        json.dumps({"action": {"type": "emit", "kind": "research.finding.recorded",
                               "payload": {"finding_ref": "a-notes.md", "evidence_refs": ["a-notes.md"]}}})]),
        max_steps=4)
    kinds3 = [f["kind"] for f in facts_mod.read_facts(base3)]
    check("derived_saturation", kinds3.count("research.saturation.reached") == 1, str(kinds3))
    check("derived_completion", kinds3.count("task.completed") == 1 and kinds3[-1] == "task.completed", str(kinds3))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task_root": str(root), "kinds": kinds}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
