#!/usr/bin/env python3
"""探索性测量：火山方舟 plan LLM + 豆包 plan 语音端点（不是验收证据）。

地位：**探索性探针**。用途是支撑 design/g3/voice-assistant/providers.md 的协议观测与
validation-plan.md 的测量项；其结果**不得**充当正式性质通过（AGENTS.md：探索结果不充当验收）。

待检验问题 / 观测 / 停止条件见 design/g3/voice-assistant/research-notes.md §1。
凭据：只从仓库外 `~/.env` 读取变量名 `ARC_PLAN_API_KEY`；**只打印变量名，绝不打印值**。

依赖：`websocket-client`（仅 TTS/ASR 需要）；LLM 探测用标准库。
用法：
    python3 probe_plan_endpoints.py llm
    python3 probe_plan_endpoints.py tts
    python3 probe_plan_endpoints.py asr
"""
from __future__ import annotations

import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid

ENV_PATH = os.environ.get("ARC_ENV_FILE", "~/.env")
ENV_NAME = "ARC_PLAN_API_KEY"

PLAN_LLM = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
PLAN_TTS_STREAM = "wss://openspeech.bytedance.com/api/v3/plan/tts/unidirectional/stream"
PLAN_TTS_BIDI = "wss://openspeech.bytedance.com/api/v3/plan/tts/bidirection"
PLAN_ASR_ASYNC = "wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_async"
RES_TTS = "seed-tts-2.0"
RES_ASR = "volc.seedasr.sauc.duration"
VOICE = "zh_female_vv_uranus_bigtts"  # 实测被 seed-tts-2.0 接受；*_mars_* 会被拒


def load_key() -> str:
    path = os.path.expanduser(ENV_PATH)
    values: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    print(f"[env] {path}: variables={sorted(values)} (values not printed)")
    if ENV_NAME not in values:
        raise SystemExit(f"missing {ENV_NAME} in {path}")
    return values[ENV_NAME]


# ---------------------------------------------------------------- LLM (stdlib)

def probe_llm(key: str) -> None:
    for label, extra in (("default", {}), ("reasoning_effort=minimal", {"reasoning_effort": "minimal"})):
        body = {
            "model": "glm-5.3-flash",
            "messages": [{"role": "user", "content": "用两三句话说明什么是全双工语音对话。"}],
            "stream": True,
            "max_tokens": 2048,
        }
        body.update(extra)
        req = urllib.request.Request(
            PLAN_LLM, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        t0 = time.time(); first_any = first_content = None; content = ""; finish = None
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    obj = json.loads(payload)
                    choice = obj["choices"][0]
                    delta = choice.get("delta") or {}
                    if first_any is None:
                        first_any = round(time.time() - t0, 3)
                    if delta.get("content"):
                        if first_content is None:
                            first_content = round(time.time() - t0, 3)
                        content += delta["content"]
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        except urllib.error.HTTPError as err:
            print(f"[llm {label}] HTTP {err.code}: {err.read()[:200]!r}")
            continue
        print(f"[llm {label}] first_delta={first_any}s first_content={first_content}s "
              f"total={round(time.time() - t0, 3)}s finish={finish} content_len={len(content)}")


# ------------------------------------------------------- Doubao plan protocol

def _header(mt: int, flags: int) -> bytes:
    # protocol_version=1, header_size=1; serialization=JSON(1), compression=none(0)
    return bytes([0x11, (mt << 4) | flags, 0x10, 0x00])


def _v1_frame(body: bytes) -> bytes:
    """V1 帧：header + u32 body 长度 + body（实测用于 unidirectional/stream）。"""
    return _header(0x1, 0x0) + struct.pack(">I", len(body)) + body


def _event_frame(event: int, sid: bytes = b"", payload: bytes = b"", mt: int = 0x1) -> bytes:
    """事件帧：header + i32 event + [u32 sid 长度 + sid] + u32 payload 长度 + payload。"""
    out = bytearray(_header(mt, 0x4))
    out += struct.pack(">i", event)
    if sid:
        out += struct.pack(">I", len(sid)) + sid
    out += struct.pack(">I", len(payload)) + payload
    return bytes(out)


_SID_CHARS = set(b"0123456789abcdef-")  # session id is a UUID rendered as ascii hex + '-'

def _parse(data: bytes) -> dict:
    out: dict = {"mt": data[1] >> 4, "flags": data[1] & 0xF, "bytes": len(data)}
    off = 4
    if out["flags"] & 0x4:
        out["event"] = struct.unpack(">i", data[off:off + 4])[0]; off += 4
    if len(data) >= off + 4:
        size = struct.unpack(">I", data[off:off + 4])[0]; off += 4
        if 0 < size <= len(data) - off and all(c in _SID_CHARS for c in data[off:off + size]):
            off += size  # session id present; next u32 is the payload size
            if len(data) >= off + 4:
                out["payload_bytes"] = struct.unpack(">I", data[off:off + 4])[0]
        else:
            out["payload_bytes"] = size
            payload = data[off:off + size]
            try:
                out["payload"] = json.loads(payload.decode())
            except Exception:
                out["audio"] = True
    return out


def _connect(url: str, key: str, resource: str):
    import websocket  # websocket-client
    headers = [f"X-Api-Key: {key}", f"X-Api-Resource-Id: {resource}",
               "X-Api-Connect-Id: " + str(uuid.uuid4())]
    return websocket.create_connection(url, header=headers, timeout=15)


def probe_tts(key: str) -> None:
    body = json.dumps({
        "user": {"uid": "probe"},
        "req_params": {"text": "你好，这是一次语音合成探测。", "speaker": VOICE,
                       "audio_params": {"format": "mp3", "sample_rate": 24000}},
    }).encode()
    ws = _connect(PLAN_TTS_STREAM, key, RES_TTS)
    t0 = time.time()
    ws.send_binary(_v1_frame(body))
    first_audio = None; audio_frames = 0; events = []
    for _ in range(80):
        data = ws.recv()
        parsed = _parse(data)
        if parsed["mt"] == 0xB:  # AudioOnlyServerResponse
            if first_audio is None:
                first_audio = round(time.time() - t0, 3)
            audio_frames += 1
        if "event" in parsed:
            events.append(parsed["event"])
        if parsed.get("event") == 152:
            break
    ws.close()
    print(f"[tts] voice={VOICE} first_audio={first_audio}s total={round(time.time() - t0, 3)}s "
          f"audio_frames={audio_frames} events={events[:8]}")


def _seq_frame(mt: int, flags: int, seq: int, payload: bytes) -> bytes:
    """ASR 序列帧：header + i32 seq + u32 payload 长度 + payload（payload 不压缩）。"""
    return _header(mt, flags) + struct.pack(">i", seq) + struct.pack(">I", len(payload)) + payload


def probe_asr(key: str) -> None:
    """ASR 用序列帧（不是事件帧）；详见 providers.md §3。"""
    import websocket

    headers = [f"X-Api-Key: {key}", f"X-Api-Resource-Id: {RES_ASR}",
               "X-Api-Connect-Id: " + str(uuid.uuid4()), "X-Api-Sequence: -1"]
    ws = websocket.create_connection(PLAN_ASR_ASYNC, header=headers, timeout=20)
    req = {"user": {"uid": "probe"},
           "audio": {"format": "pcm", "rate": 16000, "bits": 16, "channel": 1},
           "request": {"model_name": "bigmodel", "enable_punc": True, "enable_itn": True,
                       "enable_nonstream": False, "show_utterances": True}}
    ws.send_binary(_seq_frame(0x1, 0b0001, 1, json.dumps(req).encode()))
    pcm = b"\x00\x00" * 16000  # 1s 静音；真实转写见 providers.md §3（TTS→ASR 往返已跑通）
    chunk = 16000 * 2 // 5    # 200 ms
    seq = 2
    for i in range(0, len(pcm), chunk):
        last = i + chunk >= len(pcm)
        ws.send_binary(_seq_frame(0x2, 0b0011 if last else 0b0001, -seq if last else seq, pcm[i:i + chunk]))
        if not last:
            seq += 1
    try:
        ws.settimeout(5.0)
        print("[asr] first_response ->", _parse(ws.recv()))
    except Exception as err:  # 静音常返回 20000003 silent，或以超时结束
        print("[asr] no response / silent:", type(err).__name__)
    ws.close()
    print("[asr] note: 静音探针只验证帧路由；语音往返见 providers.md §3.1")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "llm"
    key = load_key()
    {"llm": probe_llm, "tts": probe_tts, "asr": probe_asr}[which](key)
