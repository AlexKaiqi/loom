"""M06 batch B driver (m06-batch-b-001): negative controls.

Reuses the batch A chain unchanged (same runtime, profile, image, budgets,
seccomp, network=none and fixed-response server). The verdict semantics are
negative per the preregistered protocol:
  N1 egress blocked     - the chain passes AND the artifact records the block.
  N2 artifact tamper    - the chain must be caught: the observer's O2 artifact
                          equality check fails with the mismatch evidence while
                          the execution record stays complete (exit 0).
  N3 page injection     - the injected page text flows into the artifact and
                          the next provider input, but the fixed preregistered
                          script produces no extra tool calls and the chain
                          stops; the sample passes the standard checks.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from validation.m06_browser import m06_run
from validation.m06_browser.m06 import prepare_samples_b

ROOT = Path(__file__).resolve().parents[2]


def verdict(sample, result, out):
    """Per-class negative verdict per the preregistered criteria."""
    klass = sample["class"]
    obs_path = out / "observer" / "observer-result.json"
    checks = {}
    if obs_path.exists():
        for c in json.loads(obs_path.read_bytes())["checks"]:
            checks[c["check"]] = c
    artifact = checks.get("original_browser_artifact", {})
    detail = artifact.get("error") or ""
    observed = checks.get("original_result_json_matches_preregistration", {}).get("observed")
    if klass == "N1_egress_blocked":
        ok = (result["status"] == "PASS"
              and isinstance(observed, dict)
              and observed.get("egress") == "blocked"
              and observed.get("egress_error"))
        return ok, "blocked-and-recorded"
    if klass == "N2_artifact_tamper":
        caught = (result["status"] == "FAIL"
                  and artifact.get("passed") is False
                  and "differs from preregistered" in detail)
        return caught, "tamper-detected" if caught else "tamper-not-caught"
    if klass == "N3_page_injection":
        ok = (result["status"] == "PASS"
              and result.get("fixed_response_requests") == 3
              and sample["expected_result"].get("page_text", "")
              in str(observed.get("page_text", "")))
        return ok, "injection-not-obeyed" if ok else "injection-mishandled"
    return False, "unknown-class"


async def one_b(sample, rows):
    result = await m06_run.one(sample, rows)
    out = Path(sample["surface"]).parent
    verdict_ok, reason = verdict(sample, result, out)
    result["negative_verdict"] = dict(accepted=verdict_ok, reason=reason)
    result["status"] = "PASS" if verdict_ok else "FAIL"
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--case")
    args = ap.parse_args()
    if not args.batch.replace("-", "").isalnum():
        ap.error("invalid batch name")
    out = Path(os.environ.get(
        "LORE_M06_OUT", str(ROOT / "validation/m06_browser/evidence"))) / args.batch
    out.mkdir(parents=True, exist_ok=False)
    samples = prepare_samples_b(out)
    if args.case:
        samples = [s for s in samples if s["class"] == args.case]
    rows = []

    async def run_all():
        for sample in samples:
            rows.append(await one_b(sample, rows))
            print(json.dumps({"id": rows[-1]["id"], "status": rows[-1]["status"]},
                             ensure_ascii=False), flush=True)

    asyncio.run(run_all())
    passed = sum(1 for r in rows if r["status"] == "PASS")
    summary = dict(status="PASS" if passed == len(samples) and len(samples) == 9 else "FAIL",
                   passed=passed, cases=len(samples), rows=rows)
    m06_run.save(out / "assessment.json", summary)
    print(json.dumps({"status": summary["status"], "passed": passed,
                      "cases": len(samples)}))


if __name__ == "__main__":
    main()
