"""Protocol-003 addendum: send the real post-switch encode_request bytes live.

Closes the system-message gap left by probe_004 (whose hand-built body omitted
the system message that encode_request always prepends). Runs after the
baseline switch; same credential handling as probe.py; not M07 evidence.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lore_provider.request import MODEL, SHELL, encode_request
from lore_provider.transport import exchange
from probe import endpoint, load_env, assess
from probe_004 import BUDGET, scope

OUT = Path(__file__).resolve().parent / "evidence-006"
HOME = Path.home() / ".env"


def main():
    OUT.mkdir(exist_ok=False)
    env = load_env(HOME)
    key = env["VOLCENGINE_API_KEY"]
    assert isinstance(key, str) and 0 < len(key) <= 4096 and key.isascii()
    authorization = "Bearer " + key
    binding = scope()
    intent = dict(binding=binding, model=MODEL, max_completion_tokens=BUDGET,
                  reasoning_effort="medium",
                  context=dict(systemPrompt="You are a wire compatibility probe.",
                               messages=[dict(role="user", timestamp=0,
                                              content="Reply with exactly the word OK.")],
                               tools=[SHELL]))
    raw = encode_request(intent, binding)
    started = time.monotonic()
    payload, transport, headers = exchange(endpoint(), raw, 300.0, authorization=authorization)
    problems, facts = {}, {}
    if transport["http_status"] == 200:
        parsed = json.loads(payload)
        problem_list, facts = assess(parsed, "stop")
        problems = {str(i): p for i, p in enumerate(problem_list)}
        echo = parsed.get("model")
        if not (isinstance(echo, str) and echo.startswith(MODEL)):
            problems["model_echo"] = repr(echo)
    else:
        facts["body_prefix"] = payload[:400].decode("utf-8", "replace")
        problems["http"] = transport["http_status"]
    record = dict(protocol="provider-compatibility-003-addendum", endpoint_host=endpoint()["host"],
                  path_prefix=endpoint()["path_prefix"], credential_source=str(HOME),
                  credential_in_evidence=False, model=MODEL, budget=BUDGET,
                  request_sha256=hashlib.sha256(raw).hexdigest(), request_bytes=len(raw),
                  response_bytes=len(payload),
                  elapsed_seconds=round(time.monotonic() - started, 3),
                  transport=transport, problems=problems, facts=facts,
                  request_body=json.loads(raw.decode()),
                  response_body=payload.decode("utf-8", "replace") if transport["http_status"] == 200 else None)
    (OUT / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(accepted=not problems, problems=problems,
                          facts={k: facts.get(k) for k in ("finish_reason", "model_echo", "usage")}),
                    ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
