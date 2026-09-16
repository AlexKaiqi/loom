"""Protocol-002 probe: does the user endpoint accept multimodal image content?

Same credential handling as probe.py (runtime read from user ~/.env, Bearer
only, never printed or saved). Bodies contain only the fixed generated image
and fixed probe text. This fixes the wire-level modality matrix for the M07
prerequisite; it is not M07 evidence and does not change the M01 baseline.
"""
import base64
import hashlib
import json
import struct
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lore_provider.transport import exchange
from probe import endpoint, load_env, assess

OUT = Path(__file__).resolve().parent / "evidence-004"
HOME = Path.home() / ".env"

PROBE_TEXT = "This message includes one image. Reply with exactly the word OK."


def tiny_png(size=32, rgba=(255, 0, 0, 255)):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    row = b"\x00" + bytes(rgba) * size
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(row * size, 9)) + chunk(b"IEND", b""))


def body_image_parts(model, data_url):
    return dict(model=model, n=1, stream=False, max_completion_tokens=2048,
                messages=[dict(role="user", content=[
                    dict(type="text", text=PROBE_TEXT),
                    dict(type="image_url", image_url=dict(url=data_url)),
                ])])


def classify(row):
    problems = row["problems"]
    status = row["transport"]["http_status"]
    if row.get("transport_error"):
        return "inconclusive"
    if status == 200 and not problems:
        return "accepted"
    if 400 <= status < 500:
        return "rejected_image_content"
    if status != 200:
        return "inconclusive"
    return "accepted_with_problems" if problems else "accepted"


def run(model, authorization, image, data_url):
    body = body_image_parts(model, data_url)
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    started = time.monotonic()
    transport_error = None
    try:
        payload, transport, headers = exchange(endpoint(), raw, 60.0, authorization=authorization)
    except Exception as error:
        payload, transport, headers = b"", dict(http_status=None), []
        transport_error = f"{type(error).__name__}: {error}"
    header_names = sorted({key.lower() for key, _ in headers})
    problems, facts = {}, {}
    parsed = None
    if transport.get("http_status") == 200:
        try:
            parsed = json.loads(payload)
            problem_list, facts = assess(parsed, "stop")
            problems = {str(i): p for i, p in enumerate(problem_list)}
        except Exception as error:
            problems["parse"] = f"{type(error).__name__}: {error}"
            facts["body_prefix"] = payload[:400].decode("utf-8", "replace")
    else:
        # Protocol-002 step 4: the verbatim provider error is decisive evidence.
        facts["body_prefix"] = payload[:400].decode("utf-8", "replace")
    row = dict(probe="image_parts", model=model, expect_finish="stop",
               request_bytes=len(raw), response_bytes=len(payload),
               elapsed_seconds=round(time.monotonic() - started, 3),
               transport=transport, transport_error=transport_error,
               response_header_names=header_names, problems=problems, facts=facts,
               request_body=json.loads(raw.decode()),
               response_body=payload.decode("utf-8", "replace") if transport.get("http_status") == 200 else None)
    row["classification"] = classify(row)
    if parsed is not None:
        choice = (parsed.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        row["observation"] = dict(content_type=type(content).__name__,
                                  content_prefix=(content or "")[:200] if isinstance(content, str) else None)
    return row


def main():
    OUT.mkdir(exist_ok=False)
    env = load_env(HOME)
    key = env["VOLCENGINE_API_KEY"]
    assert isinstance(key, str) and 0 < len(key) <= 4096 and key.isascii()
    authorization = "Bearer " + key
    image = tiny_png()
    image_sha256 = hashlib.sha256(image).hexdigest()
    data_url = "data:image/png;base64," + base64.b64encode(image).decode()
    models = [m.strip() for m in env.get("VOLCENGINE_AVAILABLE_MODELS", "").split(",") if m.strip()]
    results = {model: run(model, authorization, image, data_url) for model in models}
    verdict = {model: dict(classification=row["classification"],
                           finish_reason=row["facts"].get("finish_reason"),
                           model_echo=row["facts"].get("model_echo"),
                           usage=row["facts"].get("usage"),
                           http_status=row["transport"].get("http_status"))
               for model, row in results.items()}
    record = dict(protocol="provider-compatibility-002", endpoint_host=endpoint()["host"],
                  path_prefix=endpoint()["path_prefix"], credential_source=str(HOME),
                  credential_in_evidence=False,
                  image=dict(sha256=image_sha256, bytes=len(image), size=32, rgba=[255, 0, 0, 255]),
                  models=models, results=results, verdict=verdict)
    (OUT / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(protocol="provider-compatibility-002", image_sha256=image_sha256,
                          verdict=verdict), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
