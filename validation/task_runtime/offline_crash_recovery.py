#!/usr/bin/env python3.12
"""Offline case: an interrupted Round leaves an uncommitted fact tail.

`head` is the commit point; the runtime must refuse to continue on top of it,
`recover` must quarantine the tail (never silently drop it), and a later Round
must then run normally. No network, no credentials.
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

CRASH = [json.dumps({"action": {"type": "shell", "script": "printf 'partial\\n' > partial.txt"}})]
COMPLETE = [
    json.dumps({"action": {"type": "shell", "script": "printf 'final\\n' > final.txt"}}),
    json.dumps({"action": {"type": "emit", "kind": "task.completed", "payload": {"evidence_refs": ["final.txt"]}}}),
]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-crash-"))
    base = layout.create_task(root, "c-1", ROOT / "lore_harness" / "goal")
    round_mod.admit(base, "obj-1", "task.objective.set", {"objective": "produce final.txt"})
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    client = provider.FauxProvider(CRASH)
    try:
        round_mod.run_round(base, client, max_steps=2)
        check("crash_raised", False, "provider exhaustion did not surface")
    except provider.ProviderError as exc:
        check("crash_raised", True, str(exc))

    facts = facts_mod.read_facts(base)
    head = layout.read_json(base / "surface" / "head")
    last_row = ledger.last_row(base)
    check("uncommitted_tail_present",
          len(facts) == 2 and head["facts_end"]["seq"] == 0 and last_row.get("phase") == "start",
          "facts=%d head=%s last=%s" % (len(facts), head["facts_end"], json.dumps(last_row)))

    blocked = round_mod.run_round(base, provider.FauxProvider([]), max_steps=1)
    check("run_refuses_uncommitted", blocked.get("status") == "recovery_needed", json.dumps(blocked))

    raw_before = (base / "surface" / "facts.jsonl").read_bytes()
    repaired = round_mod.recover(base)
    check("recover_reports", repaired.get("status") == "recovered" and repaired["committed_seq"] == 1,
          json.dumps(repaired))
    check("quarantine_saved", (base / repaired["saved"]).is_file())
    saved_facts = [json.loads(l) for l in (base / repaired["saved"]).read_text().split("\n") if l.strip()]
    check("quarantine_has_original_bytes", len(saved_facts) == 1 and saved_facts[0]["kind"] == "sys.tool.result",
          json.dumps(saved_facts))
    check("facts_truncated", len(facts_mod.read_facts(base)) == 1)
    repairs = ledger.read_jsonl(base / "ledger" / "repairs.jsonl")
    check("repair_recorded", len(repairs) == 1 and repairs[0]["discarded"] == ["sys.tool.result#2"],
          json.dumps(repairs))

    result = round_mod.run_round(base, provider.FauxProvider(COMPLETE), max_steps=4)
    kinds = [f["kind"] for f in facts_mod.read_facts(base)]
    check("resume_commits", result.get("status") == "committed", json.dumps(result))
    check("completed_after_recovery", kinds.count("task.completed") == 1, str(kinds))
    check("partial_effect_remains_visible", (base / "surface" / "content" / "partial.txt").is_file(),
          "content changes before the crash stay on disk; the fact tail was quarantined")

    # --- acceptance A findings: byte-identical quarantine, torn tail, commit publish ---
    # (1) the quarantined bytes must be the ORIGINAL bytes, not a re-serialization
    saved_path = base / repaired["saved"]
    expected_tail = raw_before.split(b"\n")[1:]          # facts after seq 1, verbatim
    expected_tail = [l for l in expected_tail if l]
    check("quarantine_byte_identical",
          saved_path.read_bytes() == b"".join(l + b"\n" for l in expected_tail),
          repr(saved_path.read_bytes()[:80]))

    # (2) a torn trailing line is truncated with a trace and cannot corrupt the next append
    facts_path = base / "surface" / "facts.jsonl"
    before_count = len(facts_mod.read_facts(base))
    with open(facts_path, "ab") as fh:
        fh.write(b'{"seq": 999, "kind": "torn')
    check("torn_tail_detected", facts_mod.torn_tail(base) is True)
    facts_mod.append_fact(base, "sys.tool.result", {"script": "after-torn", "exit": 0}, source="runtime")
    after = facts_mod.read_facts(base)
    check("torn_tail_repaired_before_append",
          len(after) == before_count + 1 and after[-1]["payload"].get("script") == "after-torn",
          "before=%d after=%d last=%s" % (before_count, len(after), json.dumps(after[-1])[:120]))
    torn_repairs = [r for r in ledger.read_jsonl(base / "ledger" / "repairs.jsonl")
                    if r.get("action") == "truncate_torn_tail"]
    check("torn_tail_traced", len(torn_repairs) == 1 and torn_repairs[0]["discarded_len"] > 0,
          json.dumps(torn_repairs))

    # (3) crash between the ledger commit row and the head write -> publish, never discard
    fresh = layout.create_task(root, "c-2", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh, "obj-2", "task.objective.set", {"objective": "produce final.txt"})
    round_mod.run_round(fresh, provider.FauxProvider(COMPLETE), max_steps=4)
    committed_facts = facts_mod.read_facts(fresh)
    head = layout.read_json(fresh / "surface" / "head")
    head["facts_end"] = {"seq": 0, "digest": head["facts_end"]["digest"]}
    head["round_id"] = None
    layout.write_json(fresh / "surface" / "head", head)
    blocked2 = round_mod.run_round(fresh, provider.FauxProvider([]), max_steps=1)
    check("unpublished_commit_blocks_run",
          blocked2.get("status") == "recovery_needed" and blocked2.get("reason") == "commit_not_published",
          json.dumps(blocked2))
    published = round_mod.recover(fresh)
    head2 = layout.read_json(fresh / "surface" / "head")
    check("recover_publishes_commit",
          published.get("action") == "published_commit" and head2["facts_end"]["seq"] == len(committed_facts),
          json.dumps(published))
    check("committed_facts_not_discarded",
          len(facts_mod.read_facts(fresh)) == len(committed_facts), str(len(facts_mod.read_facts(fresh))))
    check("resume_after_publish_allowed",
          round_mod.run_round(fresh, provider.FauxProvider([]), max_steps=1).get("status") != "recovery_needed")

    # (4) acceptance A-N1: a complete JSON line missing ONLY its trailing newline
    fresh2 = layout.create_task(root, "c-3", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh2, "obj-3", "task.objective.set", {"objective": "x"})
    facts2 = fresh2 / "surface" / "facts.jsonl"
    facts2.write_bytes(facts2.read_bytes().rstrip(b"\n"))          # drop the final newline
    n_before = len(facts_mod.read_facts(fresh2))
    facts_mod.append_fact(fresh2, "sys.tool.result", {"script": "after-missing-newline", "exit": 0}, source="runtime")
    after2 = facts_mod.read_facts(fresh2)
    check("missing_newline_does_not_corrupt_append",
          len(after2) == n_before + 1 and after2[-1]["payload"].get("script") == "after-missing-newline",
          "before=%d after=%d" % (n_before, len(after2)))
    nl_repairs = [r for r in ledger.read_jsonl(fresh2 / "ledger" / "repairs.jsonl")
                  if r.get("action") == "restore_missing_newline"]
    check("missing_newline_traced", len(nl_repairs) == 1, json.dumps(nl_repairs))

    # (5) acceptance A-N2: an interrupted Round whose uncommitted tail is TORN
    fresh3 = layout.create_task(root, "c-4", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh3, "obj-4", "task.objective.set", {"objective": "produce final.txt"})
    try:
        round_mod.run_round(fresh3, provider.FauxProvider(CRASH), max_steps=2)
    except provider.ProviderError:
        pass
    with open(fresh3 / "surface" / "facts.jsonl", "ab") as fh:
        fh.write(b'{"seq": 3, "kind": "torn')
    rec2 = round_mod.recover(fresh3)
    check("recover_survives_torn_tail",
          rec2.get("status") == "recovered" and any(str(x).startswith("<torn") for x in rec2.get("discarded", [])),
          json.dumps(rec2)[:220])
    check("torn_recover_traced",
          any(r.get("reason", "").startswith("uncommitted") for r in ledger.read_jsonl(fresh3 / "ledger" / "repairs.jsonl")),
          json.dumps(ledger.read_jsonl(fresh3 / "ledger" / "repairs.jsonl"))[:200])
    check("torn_recover_aborts_start",
          ledger.last_row(fresh3).get("phase") == "abort", json.dumps(ledger.last_row(fresh3)))
    resumed = round_mod.run_round(fresh3, provider.FauxProvider(
        [json.dumps({"action": {"type": "final", "text": "stop"}})]), max_steps=2)
    check("torn_recover_not_stuck", resumed.get("status") != "recovery_needed", json.dumps(resumed))

    # (6) acceptance A-N3: a fault after recover truncated but before it wrote the abort marker
    fresh4 = layout.create_task(root, "c-5", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh4, "obj-5", "task.objective.set", {"objective": "produce final.txt"})
    try:
        round_mod.run_round(fresh4, provider.FauxProvider(CRASH), max_steps=2)
    except provider.ProviderError:
        pass
    facts4 = fresh4 / "surface" / "facts.jsonl"
    lines = [l for l in facts4.read_bytes().split(b"\n") if l.strip()]
    facts4.write_bytes(b"".join(l + b"\n" for l in lines[:1]))     # simulate "already truncated"
    rec3 = round_mod.recover(fresh4)
    check("recover_resumable_after_own_fault",
          rec3.get("status") == "nothing_to_recover" and rec3.get("aborted_start") is True,
          json.dumps(rec3))
    check("resume_abort_written", ledger.last_row(fresh4).get("phase") == "abort",
          json.dumps(ledger.last_row(fresh4)))
    allowed = round_mod.run_round(fresh4, provider.FauxProvider(
        [json.dumps({"action": {"type": "final", "text": "stop"}})]), max_steps=2)
    check("no_permanent_stuck_after_resume", allowed.get("status") != "recovery_needed", json.dumps(allowed))

    # (7) acceptance A-N7: a SECOND recover must be a no-op, not delete admitted facts
    fresh5 = layout.create_task(root, "c-6", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh5, "obj-6", "task.objective.set", {"objective": "produce final.txt"})
    try:
        round_mod.run_round(fresh5, provider.FauxProvider(CRASH), max_steps=2)
    except provider.ProviderError:
        pass
    first = round_mod.recover(fresh5)
    after_first = facts_mod.read_facts(fresh5)
    second = round_mod.recover(fresh5)
    after_second = facts_mod.read_facts(fresh5)
    third = round_mod.recover(fresh5)
    check("second_recover_is_noop",
          first.get("status") == "recovered" and second.get("status") == "nothing_to_recover"
          and third.get("status") == "nothing_to_recover",
          "1=%s 2=%s 3=%s" % (first.get("status"), second.get("status"), third.get("status")))
    check("double_recover_keeps_admitted_facts",
          len(after_first) == len(after_second) == 1 and after_second[0]["kind"] == "task.objective.set",
          "after_first=%s after_second=%s" % (json.dumps(after_first)[:80], json.dumps(after_second)[:80]))

    # (8) acceptance A-N8: a NEWLINE-TERMINATED malformed last line is also repaired
    fresh6 = layout.create_task(root, "c-7", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh6, "obj-7", "task.objective.set", {"objective": "x"})
    facts6 = fresh6 / "surface" / "facts.jsonl"
    before6 = len(facts_mod.read_facts(fresh6))
    with open(facts6, "ab") as fh:
        fh.write(b'{"seq": 9, "kind": "torn\n')      # ends with \n but is not valid JSON
    facts_mod.append_fact(fresh6, "sys.tool.result", {"script": "after-terminated-torn", "exit": 0}, source="runtime")
    after6 = facts_mod.read_facts(fresh6)
    check("terminated_malformed_line_repaired",
          len(after6) == before6 + 1 and after6[-1]["payload"].get("script") == "after-terminated-torn",
          "before=%d after=%d" % (before6, len(after6)))
    repairs6 = ledger.read_jsonl(fresh6 / "ledger" / "repairs.jsonl")
    check("terminated_malformed_traced",
          any(r.get("action") == "truncate_torn_tail" and r.get("discarded_len", 0) > 0 for r in repairs6),
          json.dumps(repairs6)[:200])

    # (9) acceptance A-R1: a hand-edited `start` row without trigger_seq must refuse, not KeyError
    fresh7 = layout.create_task(root, "c-8", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh7, "obj-8", "task.objective.set", {"objective": "x"})
    (fresh7 / "ledger" / "rounds.jsonl").write_text(
        json.dumps({"phase": "start", "round_id": "r-foreign"}) + "\n")
    try:
        round_mod.recover(fresh7)
        check("start_without_trigger_seq_refused", False, "recover guessed the commit floor")
    except ValueError as exc:
        check("start_without_trigger_seq_refused", "no trigger_seq" in str(exc), str(exc))
    check("foreign_start_left_untouched", len(facts_mod.read_facts(fresh7)) == 1)

    # (10) acceptance A-R2: corruption in the MIDDLE of the stream errors loudly
    fresh8 = layout.create_task(root, "c-9", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh8, "obj-9", "task.objective.set", {"objective": "x"})
    facts8 = fresh8 / "surface" / "facts.jsonl"
    good = facts8.read_bytes()
    later = json.dumps({"seq": 3, "id": "sys.tool.result#3", "kind": "sys.tool.result", "source": "runtime",
                        "payload": {}, "digest": "sha256:" + "0" * 64}).encode() + b"\n"
    facts8.write_bytes(good + b'{"seq": 2, broken\n' + later)
    try:
        facts_mod.read_facts(fresh8)
        check("midstream_corruption_errors", False, "read_facts silently dropped facts")
    except ValueError as exc:
        check("midstream_corruption_errors", "corrupt fact stream at physical line 2" in str(exc), str(exc))
    try:
        round_mod.run_round(fresh8, provider.FauxProvider([]), max_steps=1)
        check("midstream_corruption_blocks_round", False, "run_round proceeded on a corrupt stream")
    except ValueError as exc:
        check("midstream_corruption_blocks_round", "corrupt fact stream" in str(exc), str(exc))
    check("midstream_corruption_does_not_truncate", facts8.read_bytes().endswith(later))

    # (11) acceptance A-R5: retrying a publish must not duplicate the trace row
    fresh9 = layout.create_task(root, "c-10", ROOT / "lore_harness" / "goal")
    round_mod.admit(fresh9, "obj-10", "task.objective.set", {"objective": "produce final.txt"})
    round_mod.run_round(fresh9, provider.FauxProvider(COMPLETE), max_steps=4)
    for _ in range(2):
        head9 = layout.read_json(fresh9 / "surface" / "head")
        head9["facts_end"] = {"seq": 0, "digest": head9["facts_end"]["digest"]}
        head9["round_id"] = None
        layout.write_json(fresh9 / "surface" / "head", head9)
        round_mod.recover(fresh9)
    published = [r for r in ledger.read_jsonl(fresh9 / "ledger" / "repairs.jsonl")
                 if r.get("action") == "published_commit"]
    check("publish_trace_not_duplicated", len(published) == 1, json.dumps(published))
    check("published_head_correct",
          layout.read_json(fresh9 / "surface" / "head")["facts_end"]["seq"] == len(facts_mod.read_facts(fresh9)),
          json.dumps(layout.read_json(fresh9 / "surface" / "head")))

    # (12) acceptance A-R6: Unicode line separators in a LEGITIMATE payload must not
    #      be mistaken for line breaks by the reader (JSONL is "\n"-delimited only)
    for label, char in (("U+2028", "\u2028"), ("U+2029", "\u2029"), ("U+0085", "\u0085")):
        freshA = layout.create_task(root, "c-" + label.replace("+", ""), ROOT / "lore_harness" / "goal")
        objective = "before" + char + "after"
        round_mod.admit(freshA, "obj-" + label, "task.objective.set", {"objective": objective})
        parsed = facts_mod.read_facts(freshA)
        check("unicode_%s_roundtrip" % label.replace("+", ""),
              len(parsed) == 1 and parsed[0]["payload"]["objective"] == objective,
              json.dumps(parsed)[:150])
        out = round_mod.run_round(freshA, provider.FauxProvider(
            [json.dumps({"action": {"type": "final", "text": "stop"}})]), max_steps=2)
        check("unicode_%s_round_ok" % label.replace("+", ""), out.get("status") == "committed", json.dumps(out))

    # (13) acceptance A-R7: the reported physical line number counts real lines
    freshB = layout.create_task(root, "c-line", ROOT / "lore_harness" / "goal")
    round_mod.admit(freshB, "obj-line", "task.objective.set", {"objective": "x"})
    factsB = freshB / "surface" / "facts.jsonl"
    factsB.write_bytes(factsB.read_bytes() + b"\n\n" + b'{"broken\n')
    try:
        facts_mod.read_facts(freshB)
        check("physical_line_number_reported", False, "no error raised")
    except ValueError as exc:
        check("physical_line_number_reported", "physical line 4" in str(exc), str(exc))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"task_root": str(root), "kinds": kinds}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
