"""Amendment-001 verification: glm-5.3 under the production 2048 budget.

Same credential handling as probe.py; evidence records request/response bodies
only. This run fixes the M01 provider_model baseline; it is not M01 evidence.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lore_provider.transport import exchange
from lore_provider.request import SHELL
from probe import endpoint, load_env, assess

OUT = Path(__file__).resolve().parent / "evidence-002"
OUT.mkdir(exist_ok=False)


def body_minimal(model):
    return dict(model=model, n=1, stream=False, max_completion_tokens=2048,
                messages=[dict(role="user", content="Reply with exactly the word OK")])


def body_toolcall(model):
    return dict(model=model, n=1, stream=False, max_completion_tokens=2048,
                messages=[dict(role="user",
                               content="Call the shell tool once with target=workspace and script=echo hi. Do not answer in words.")],
                tools=[dict(type="function", function=SHELL)])


def main():
    env = load_env(Path.home() / ".env")
    key = env["VOLCENGINE_API_KEY"]
    authorization = "Bearer " + key
    model = "glm-5.3"
    rows = []
    for name, body, expect in (("minimal-2048", body_minimal(model), "stop"),
                               ("toolcall-2048", body_toolcall(model), "tool_calls")):
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        started = time.monotonic()
        payload, transport, headers = exchange(endpoint(), raw, 60.0, authorization=authorization)
        parsed = json.loads(payload)
        problems, facts = assess(parsed, expect)
        rows.append(dict(probe=name, model=model, expect_finish=expect,
                         elapsed_seconds=round(time.monotonic() - started, 3),
                         transport=transport, problems={str(i): p for i, p in enumerate(problems)},
                         facts=facts, request_body=json.loads(raw.decode()),
                         response_body=payload.decode("utf-8", "replace")))
    passed = all(not row["problems"] for row in rows)
    record = dict(amendment="provider-compatibility-001-amendment-001", model=model,
                  passed=passed, rows=rows)
    (OUT / "compatibility.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(model=model, passed=passed,
                          finishes=[r["facts"].get("finish_reason") for r in rows],
                          usage=[r["facts"].get("usage") for r in rows]), ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
