"""Protocol-003 probe: production-shape wire compatibility for deepseek-v4-flash.

Builds the exact production body shape (post-switch encode_request field set)
independently, because the pre-switch MODEL gate would reject the deepseek
intent. Same credential handling as probe.py; evidence records request/response
bodies only. This is the gate for the 2026-09-15 baseline switch; it is not M07
evidence and does not change M01 batch-z records.
"""
import copy
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lore_provider.request import SHELL
from lore_provider.transport import exchange
from probe import endpoint, load_env, assess

OUT = Path(__file__).resolve().parent / "evidence-005"
HOME = Path.home() / ".env"
CANDIDATE = "deepseek-v4-flash"
BUDGET = 16384


def scope():
    digest = hashlib.sha256(b"protocol-003 production shape probe").hexdigest()
    ref = lambda name: dict(id=name, sha256=digest)
    return dict(session_id="protocol-003-probe", operation_id="op-003-probe",
                response_entry_id="entry-003-probe", input_ref=ref("protocol-003-input"),
                harness_ref=ref("protocol-003-harness"), capability_ref=ref("protocol-003-capability"))


def production_body(model, messages):
    return dict(model=model, n=1, stream=False, max_completion_tokens=BUDGET,
                parallel_tool_calls=False, reasoning_effort="medium",
                messages=messages, tools=[copy.deepcopy(dict(type="function", function=SHELL))])


def run(label, body, expect, authorization):
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    started = time.monotonic()
    payload, transport, headers = exchange(endpoint(), raw, 300.0, authorization=authorization)
    problems, facts = {}, {}
    parsed = None
    if transport["http_status"] == 200:
        try:
            parsed = json.loads(payload)
            problem_list, facts = assess(parsed, expect)
            problems = {str(i): p for i, p in enumerate(problem_list)}
            echo = parsed.get("model")
            if not (isinstance(echo, str) and echo.startswith(CANDIDATE)):
                problems["model_echo"] = f"{echo!r} does not start with {CANDIDATE!r}"
        except Exception as error:
            problems["parse"] = f"{type(error).__name__}: {error}"
            facts["body_prefix"] = payload[:400].decode("utf-8", "replace")
    else:
        facts["body_prefix"] = payload[:400].decode("utf-8", "replace")
        problems["http"] = transport["http_status"]
    return dict(probe=label, expect_finish=expect, request_bytes=len(raw),
                response_bytes=len(payload), elapsed_seconds=round(time.monotonic() - started, 3),
                transport=transport, response_header_names=sorted({k.lower() for k, _ in headers}),
                problems=problems, facts=facts,
                request_body=json.loads(raw.decode()),
                response_body=payload.decode("utf-8", "replace") if transport["http_status"] == 200 else None)


def main():
    OUT.mkdir(exist_ok=False)
    env = load_env(HOME)
    key = env["VOLCENGINE_API_KEY"]
    assert isinstance(key, str) and 0 < len(key) <= 4096 and key.isascii()
    authorization = "Bearer " + key
    binding = scope()
    rows = [
        run("production_text",
            production_body(CANDIDATE, [dict(role="user", content="Reply with exactly the word OK")]),
            "stop", authorization),
        run("production_toolcall",
            production_body(CANDIDATE, [dict(role="user", content=(
                "Call the shell tool once with target=workspace and script=echo hi. "
                "Do not answer in words."))]),
            "tool_calls", authorization),
    ]
    for row in rows:
        row["binding"] = binding
    echoes = [json.loads(json.dumps(row["facts"].get("model_echo"))) for row in rows
              if row["facts"].get("model_echo")]
    verdict = dict(
        all_accepted=all(not row["problems"] for row in rows),
        echoed_models=sorted(set(echoes)),
        elapsed_sum=round(sum(row["elapsed_seconds"] for row in rows), 3))
    record = dict(protocol="provider-compatibility-003", endpoint_host=endpoint()["host"],
                  path_prefix=endpoint()["path_prefix"], credential_source=str(HOME),
                  credential_in_evidence=False, candidate=CANDIDATE,
                  budget=BUDGET, results=rows, verdict=verdict)
    (OUT / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(protocol="provider-compatibility-003", verdict=verdict,
                          problems={r["probe"]: r["problems"] for r in rows}),
                    ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
