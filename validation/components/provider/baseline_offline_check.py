"""Offline baseline-switch check: alias echo rule and production encode shape.

Preregistered with amendment-model-baseline-2026-09-15. Two parts:
1. alias-echo-cases.json through lore_provider.response.normalize (the changed
   model_mismatch rule; the historical PW fixtures are absent from this working
   copy so run_contract.py cannot run here);
2. encode_request field-set reproduction of the protocol-003 production shape,
   byte-identical to the live-sent probe_005 request (evidence-006).
No HTTP, no Engine, no credential use.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import begin

BUDGET = 16384


def binding():
    digest = "3d1f7a5c2b8e46d09a13c7f25b60d4e8" * 2  # 64 hex, same shape as probes
    ref = lambda name: dict(id=name, sha256=digest)
    return dict(session_id="protocol-003-probe", operation_id="op-003-probe",
                response_entry_id="entry-003-probe", input_ref=ref("protocol-003-input"),
                harness_ref=ref("protocol-003-harness"), capability_ref=ref("protocol-003-capability"))


def main():
    out, hashes = begin("baseline-offline-001", "lore_provider")
    from lore_provider.jsoncodec import WireError
    from lore_provider.request import MODEL, MODEL_ALIAS, SHELL, encode_request
    from lore_provider.response import normalize

    rows = []
    cases = json.loads((ROOT / "design/g3/provider/alias-echo-cases.json").read_bytes())["cases"]
    for case in cases:
        raw = case["raw_body"].encode()
        try:
            message = normalize(raw, {"complete": True, "http_status": 200})
            accepted, reason, model = True, None, message["message"]["model"]
        except WireError as error:
            accepted, model = False, None
            reason = str(error.args[0]) if error.args else "invalid_wire"
        expected = case["expected"]
        ok = accepted == expected["accepted"] and (
            not accepted or model == expected["message_model"]) and (
            accepted or reason == expected["reason"])
        rows.append(dict(case=case["id"], accepted=accepted, reason=reason,
                         message_model=model, expected=expected, passed=ok))

    scope = binding()
    intent = dict(binding=scope, model=MODEL, max_completion_tokens=BUDGET,
                  reasoning_effort="medium",
                  context=dict(systemPrompt="You are a wire compatibility probe.",
                               messages=[dict(role="user", timestamp=0,
                                              content="Reply with exactly the word OK.")],
                               tools=[SHELL]))
    raw = encode_request(intent, scope)
    body = json.loads(raw.decode())
    evidence = json.loads((ROOT / "validation/provider_compatibility/evidence-006/record.json").read_bytes())
    sent = evidence["request_body"]
    field_set_ok = (
        body["model"] == MODEL and body["n"] == 1 and body["stream"] is False
        and body["max_completion_tokens"] == BUDGET
        and body["parallel_tool_calls"] is False and body["reasoning_effort"] == "medium"
        and body["messages"] == sent["messages"] and body["tools"] == sent["tools"])
    byte_ok = raw.decode() == json.dumps(sent, ensure_ascii=False, separators=(",", ":"))
    rows.append(dict(case="production-encode-reproduction", field_set_ok=field_set_ok,
                     byte_identical_to_evidence_006=byte_ok,
                     passed=field_set_ok and byte_ok))

    record = dict(check="baseline-offline-001", model=MODEL, model_alias=MODEL_ALIAS,
                  rows=rows, passed=all(row["passed"] for row in rows))
    (out / "assessment.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(passed=record["passed"],
                          failed=[r["case"] for r in rows if not r["passed"]]),
                    ensure_ascii=False))


if __name__ == "__main__":
    main()
