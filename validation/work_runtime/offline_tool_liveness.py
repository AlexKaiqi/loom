#!/usr/bin/env python3.12
"""Executable pre-registered criteria VO37-VO42 (tool liveness).

Source of truth: design/g3/voice-assistant/validation-plan.md E4 and
design/g3/amendment-task-tool-liveness-2026-09-17.md section 6 (implementation
order: pre-register cases FIRST, then implement, then re-run independently).
This file was written before the implementation landed and its assertions were
not relaxed afterwards; the implementation had to satisfy them.

Fixture: validation/work_runtime/fixture_liveness/ (declares sys.tool.started /
check / abandoned / action.rejected; ends a Round only on `final`).

Old semantics that must stay true: exit 126 (unauthorized target) and exit 0
(success) are unchanged; `exit` survives only as a compatibility mirror, the
authoritative field is `outcome`.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lore_work import facts as facts_mod  # noqa: E402
from lore_work import layout  # noqa: E402
from lore_work import round as round_mod  # noqa: E402

FIXTURE = ROOT / "validation" / "work_runtime" / "fixture_liveness"

FAILURES = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  :: " + str(detail)[:300]))
    if not ok:
        FAILURES.append(name)


def facts_of(base, kind):
    return [f for f in facts_mod.read_facts(base) if f["kind"] == kind]


def run_case(case, responses, **kwargs):
    root = Path(tempfile.mkdtemp(prefix="lore-liveness-"))
    base = layout.create_work(root, case, FIXTURE)
    round_mod.admit(base, case + "-1", "liveness.request", {"case": case})
    result = round_mod.run_round(base, _provider(responses), **kwargs)
    return base, result


def _provider(responses):
    from lore_work import provider
    return provider.FauxProvider([json.dumps(r) for r in responses])


def payload_field_ok(fact, contract_path):
    """Every field named in the contract's payload must be present on the fact."""
    contract = json.loads(contract_path.read_text())
    return all(k in fact["payload"] for k in contract["payload"])


def vo37_vo38():
    """VO37 default observability + VO38 no auto-kill at the check point."""
    base, result = run_case(
        "vo37-38",
        [{"action": {"type": "shell", "script": "sleep 1.1"}},
         {"action": {"type": "final", "text": "long call finished on its own"}}],
        tool_check_interval=0.25)
    check("vo37_round_committed", result.get("status") == "committed", json.dumps(result))
    checks = facts_of(base, "sys.tool.check")
    started = facts_of(base, "sys.tool.started")
    results = facts_of(base, "sys.tool.result")
    check("vo37_checks_emitted", len(checks) >= 2, "checks=%d" % len(checks))
    check("vo37_check_seq_increasing",
          [c["payload"]["check_seq"] for c in checks] == sorted(c["payload"]["check_seq"] for c in checks),
          json.dumps([c["payload"]["check_seq"] for c in checks]))
    check("vo37_elapsed_grows",
          all(b["payload"]["elapsed_ms"] > a["payload"]["elapsed_ms"] for a, b in zip(checks, checks[1:])),
          json.dumps([c["payload"]["elapsed_ms"] for c in checks]))
    check("vo37_silent_for_present", all("silent_for_ms" in c["payload"] for c in checks), "")
    check("vo37_backoff_doubles", len(checks) >= 2 and checks[1]["payload"]["backoff_ms"] == 2 * checks[0]["payload"]["backoff_ms"],
          json.dumps([c["payload"]["backoff_ms"] for c in checks]))
    check("vo37_observations_before_result",
          all(c["seq"] < results[0]["seq"] for c in checks) and started and started[0]["seq"] < checks[0]["seq"],
          json.dumps({"started": started[0]["seq"] if started else None,
                      "checks": [c["seq"] for c in checks], "result": results[0]["seq"] if results else None}))
    # VO38: the check point does not kill; the 1.1s call completed naturally.
    check("vo38_no_kill_at_check", len(results) == 1 and results[0]["payload"]["outcome"] == "ok"
          and results[0]["payload"]["exit"] == 0, json.dumps(results[0]["payload"] if results else None))
    check("vo38_no_abandoned", not facts_of(base, "sys.tool.abandoned"),
          json.dumps([f["payload"] for f in facts_of(base, "sys.tool.abandoned")]))
    for path, kind in (("contracts/sys-tool-started.json", "sys.tool.started"),
                       ("contracts/sys-tool-check.json", "sys.tool.check")):
        check("vo37_contract_fields_" + kind.replace(".", "_"),
              all(payload_field_ok(f, FIXTURE / path) for f in facts_of(base, kind)), kind)


def vo39():
    """VO39 four-way outcome classification, distinguishable on one stream."""
    base, result = run_case(
        "vo39",
        [{"action": {"type": "shell", "script": "true"}},
         {"action": {"type": "shell", "script": "false"}},
         {"action": {"type": "shell", "script": "sleep 5", "budget_ms": 350}},
         {"action": {"type": "shell", "script": "sleep 5"}}],
        max_steps=4, tool_check_interval=10.0, tool_hard_cap=0.6)
    results = facts_of(base, "sys.tool.result")
    outcomes = [r["payload"]["outcome"] for r in results]
    check("vo39_four_results", len(results) == 4, json.dumps(outcomes))
    check("vo39_outcomes_ok_failed_timeout_unknown",
          outcomes == ["ok", "failed", "timeout", "unknown"], json.dumps(outcomes))
    ok_r, failed_r, timeout_r, unknown_r = (r["payload"] for r in results)
    check("vo39_exit_mirror_ok", ok_r["exit"] == 0, json.dumps(ok_r))
    check("vo39_exit_mirror_failed", failed_r["exit"] != 0, json.dumps(failed_r))
    check("vo39_timeout_killed_not_failed",
          timeout_r["outcome"] == "timeout" and (timeout_r["exit"] is None or timeout_r["exit"] < 0 or timeout_r["exit"] >= 128)
          and timeout_r["duration_ms"] < 5000, json.dumps(timeout_r))
    check("vo39_timeout_side_effects", timeout_r["side_effects"] == "possible", json.dumps(timeout_r))
    check("vo39_unknown_side_effects", unknown_r["side_effects"] == "unknown", json.dumps(unknown_r))
    check("vo39_timeout_not_abandoned",
          all(a["payload"]["call_id"] != timeout_r["call_id"] for a in facts_of(base, "sys.tool.abandoned")),
          "budget-timeout is a policy stop, not a safety-net abandonment")


def vo40():
    """VO40 resource safety net: reclaim, record unknown, never retry silently."""
    base, result = run_case(
        "vo40",
        [{"action": {"type": "shell", "script": "sleep 5"}},
         {"action": {"type": "final", "text": "abandoned path observed"}}],
        tool_check_interval=10.0, tool_hard_cap=0.6)
    started = facts_of(base, "sys.tool.started")
    results = facts_of(base, "sys.tool.result")
    abandoned = facts_of(base, "sys.tool.abandoned")
    check("vo40_single_attempt", len(started) == 1, "attempts=%d" % len(started))
    check("vo40_result_unknown", len(results) == 1 and results[0]["payload"]["outcome"] == "unknown",
          json.dumps(results[0]["payload"] if results else None))
    check("vo40_not_written_as_failed", results[0]["payload"]["exit"] in (None,) or results[0]["payload"]["exit"] < 0
          or results[0]["payload"]["exit"] >= 128, json.dumps(results[0]["payload"]))
    check("vo40_abandoned_recorded", len(abandoned) == 1 and abandoned[0]["payload"]["reason"] == "resource_limit"
          and abandoned[0]["payload"]["call_id"] == started[0]["payload"]["call_id"], json.dumps(abandoned))
    check("vo40_abandoned_contract_fields",
          payload_field_ok(abandoned[0], FIXTURE / "contracts/sys-tool-abandoned.json"), "")
    # Recovery discipline (runtime half): the fact stream lets recovery query
    # first — abandonment (reclaim) is recorded, then the closing result marks
    # the call unknown; no rerun was started (vo40_single_attempt).
    check("vo40_queryable_unknown", abandoned[0]["seq"] < results[0]["seq"],
          "reclaim observation precedes the closing unknown result")


def vo41():
    """VO41 explicit values above the runtime cap are refused and recorded."""
    base, result = run_case(
        "vo41",
        [{"action": {"type": "shell", "script": "echo affected > probe.txt", "budget_ms": 999999999}},
         {"action": {"type": "final", "text": "refusal observed"}}],
        tool_check_interval=10.0)
    rejected = facts_of(base, "sys.action.rejected")
    check("vo41_refusal_recorded", len(rejected) == 1 and "hard cap" in rejected[0]["payload"]["reason"],
          json.dumps(rejected))
    check("vo41_never_started", not facts_of(base, "sys.tool.started") and not facts_of(base, "sys.tool.result"),
          json.dumps([f["kind"] for f in facts_mod.read_facts(base)]))
    probe = base / "surface" / "content" / "probe.txt"
    check("vo41_no_side_effect", not probe.exists(), "probe.txt exists: the refused call ran")


def vo42():
    """VO42 in-band timeout is defense in depth: it works, runtime stays quiet."""
    in_band = ("sleep 5 & P=$!; ( sleep 1; kill $P ) & W=$!; wait $P; RC=$?; "
               "kill $W 2>/dev/null; exit $RC")
    base, result = run_case(
        "vo42",
        [{"action": {"type": "shell", "script": in_band}},
         {"action": {"type": "final", "text": "in-band path observed"}}],
        tool_check_interval=10.0)
    results = facts_of(base, "sys.tool.result")
    check("vo42_in_band_self_terminated",
          len(results) == 1 and results[0]["payload"]["outcome"] == "failed"
          and results[0]["payload"]["exit"] == 143 and results[0]["payload"]["duration_ms"] < 3000,
          json.dumps(results[0]["payload"] if results else None))
    check("vo42_runtime_stayed_out", not facts_of(base, "sys.tool.abandoned"), "runtime must not kill on its own")


def vo38_regression_exit_126():
    """Preserved semantics: unauthorized target still exits 126 (never executes)."""
    base, result = run_case(
        "vo38-126",
        [{"action": {"type": "shell", "script": "echo nope", "target": "nowhere"}},
         {"action": {"type": "final", "text": "refusal observed"}}],
        tool_check_interval=10.0)
    results = facts_of(base, "sys.tool.result")
    check("vo126_exit_preserved", len(results) == 1 and results[0]["payload"]["exit"] == 126
          and results[0]["payload"]["outcome"] == "failed" and results[0]["payload"]["side_effects"] == "none",
          json.dumps(results[0]["payload"] if results else None))


def main() -> int:
    vo37_vo38()
    vo39()
    vo40()
    vo41()
    vo42()
    vo38_regression_exit_126()
    print(json.dumps({"case": "offline_tool_liveness", "failures": FAILURES, "ok": not FAILURES}))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
