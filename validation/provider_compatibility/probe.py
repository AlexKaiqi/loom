"""Fixed no-secret provider compatibility probe for the user-provided endpoint.

Reads the credential at runtime from the user home .env (VOLCENGINE_API_KEY);
the key is used only in the Authorization header and never printed, logged or
saved. Bodies contain no task data or secrets. This probe does not establish
M01 PASS; it only fixes the provider_model baseline per protocol-001.json.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lore_provider.transport import exchange  # production transport only; no credential here
from lore_provider.request import SHELL

HOME = Path.home() / ".env"
OUT = Path(__file__).resolve().parent / "evidence-001"


def load_env(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


def endpoint():
    base = load_env(HOME)["VOLCENGINE_BASE_URL"]
    assert base.startswith("https://"), base
    rest = base[len("https://"):]
    host, _, prefix = rest.partition("/")
    return dict(scheme="https", host=host, port=443, path_prefix="/" + prefix.rstrip("/"))


def minimal(model):
    return dict(model=model, n=1, stream=False, max_completion_tokens=16,
                messages=[dict(role="user", content="Reply with exactly the word OK")])


def toolcall(model):
    return dict(model=model, n=1, stream=False, max_completion_tokens=256,
                messages=[dict(role="user",
                               content="Call the shell tool once with target=workspace and script=echo hi. Do not answer in words.")],
                tools=[dict(type="function", function=SHELL)])


def assess(body, expect_finish):
    problems = []
    if not isinstance(body, dict) or body.get("object") != "chat.completion":
        problems.append("object != chat.completion")
        return problems, {}
    choice = (body.get("choices") or [{}])[0]
    finish = choice.get("finish_reason")
    usage = body.get("usage")
    message = choice.get("message") or {}
    facts = dict(finish_reason=finish, model_echo=body.get("model"), usage=usage,
                 reasoning_content_present="reasoning_content" in message,
                 content_present=message.get("content") is not None)
    if finish != expect_finish:
        problems.append(f"finish_reason {finish!r} != {expect_finish!r}")
    if not isinstance(usage, dict):
        problems.append("usage missing")
    else:
        try:
            if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
                problems.append("usage total inconsistent")
        except (KeyError, TypeError):
            problems.append("usage fields missing")
    if expect_finish == "tool_calls":
        calls = message.get("tool_calls") or []
        if not calls:
            problems.append("no tool_calls")
        else:
            call = calls[0]
            if call.get("type") != "function" or (call.get("function") or {}).get("name") != "shell":
                problems.append("first call is not the shell function")
            else:
                try:
                    arguments = json.loads(call["function"]["arguments"])
                    if set(arguments) != {"target", "script"}:
                        problems.append("shell arguments shape differs")
                except Exception as error:
                    problems.append(f"arguments not JSON object: {error}")
    return problems, facts


def run(model, authorization):
    rows = []
    for name, body, expect in (("minimal", minimal(model), "stop"),
                               ("toolcall", toolcall(model), "tool_calls")):
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        started = time.monotonic()
        payload, transport, headers = exchange(endpoint(), raw, 60.0, authorization=authorization)
        header_names = sorted({key.lower() for key, _ in headers})
        problems, facts = {}, {}
        if transport["http_status"] != 200:
            problems["http"] = transport["http_status"]
            facts["body_prefix"] = payload[:400].decode("utf-8", "replace")
        else:
            try:
                parsed = json.loads(payload)
                problems_list, facts = assess(parsed, expect)
                problems = {str(i): p for i, p in enumerate(problems_list)}
            except Exception as error:
                problems["parse"] = f"{type(error).__name__}: {error}"
                facts["body_prefix"] = payload[:400].decode("utf-8", "replace")
        rows.append(dict(probe=name, model=model, expect_finish=expect,
                         request_bytes=len(raw), response_bytes=len(payload),
                         elapsed_seconds=round(time.monotonic() - started, 3),
                         transport=transport, response_header_names=header_names,
                         problems=problems, facts=facts,
                         request_body=json.loads(raw.decode()),
                         response_body=payload.decode("utf-8", "replace") if transport["http_status"] == 200 else None))
    return rows


def main():
    OUT.mkdir(exist_ok=False)
    env = load_env(HOME)
    key = env["VOLCENGINE_API_KEY"]
    assert isinstance(key, str) and 0 < len(key) <= 4096 and key.isascii()
    authorization = "Bearer " + key
    models = [m.strip() for m in env.get("VOLCENGINE_AVAILABLE_MODELS", "").split(",") if m.strip()]
    results = {model: run(model, authorization) for model in models}
    verdict = {}
    for model, rows in results.items():
        ok = all(not row["problems"] for row in rows)
        no_reasoning = all(not row["facts"].get("reasoning_content_present") for row in rows)
        latency = sum(row["elapsed_seconds"] for row in rows)
        verdict[model] = dict(passed=ok, reasoning_content=no_reasoning, latency_sum=latency)
    ranked = sorted(verdict, key=lambda m: (not verdict[m]["passed"], not verdict[m]["reasoning_content"], verdict[m]["latency_sum"]))
    record = dict(protocol="provider-compatibility-001", endpoint_host=endpoint()["host"],
                  path_prefix=endpoint()["path_prefix"], credential_source=str(HOME),
                  credential_in_evidence=False, results=results, verdict=verdict,
                  selected_model=ranked[0] if verdict.get(ranked[0], {}).get("passed") else None,
                  selection_rule="protocol-001.json step 5")
    (OUT / "compatibility.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(selected_model=record["selected_model"], verdict=verdict), ensure_ascii=False))


if __name__ == "__main__":
    main()
