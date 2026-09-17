"""Append-only fact stream. Runtime is the single writer (E1/E2/E4).

Base representation is one file `surface/facts.jsonl`; segmentation is a later
mechanism that must not change replay semantics (landing §4.2, §9-1).

Durability rules (landing §6):
- only complete lines are facts;
- a torn trailing line is truncated **with a trace** (payload bytes kept base64 in
  `ledger/repairs.jsonl`) before any new append, so a torn write can never corrupt
  the next fact.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

from .layout import atomic_write, paths


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fact_digest(body: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def read_facts(base) -> list:
    """Read complete lines only; a torn trailing line is reported, not parsed."""
    p = paths(base)["facts"]
    if not p.exists():
        return []
    rows = []
    # JSONL is newline-delimited: split on "\n" ONLY. `str.splitlines()` would also
    # split on U+2028/U+2029/U+0085, which json.dumps(ensure_ascii=False) writes
    # literally, so a legitimate payload could be mis-read as a corrupt stream (A-R6).
    for number, raw_line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            # landing §6 / E contract: a corrupt fact line is an error, never a
            # silent truncation of everything after it. `repair_torn_tail` handles
            # the tail case before callers read.
            raise ValueError("corrupt fact stream at physical line %d: %s" % (number, exc)) from exc
    return rows


def torn_tail(base) -> bool:
    p = paths(base)["facts"]
    if not p.exists():
        return False
    raw = p.read_text(encoding="utf-8")
    if not raw or raw.endswith("\n"):
        return False
    try:
        json.loads(raw.rsplit("\n", 1)[-1])
        return False
    except json.JSONDecodeError:
        return True


def repair_torn_tail(base) -> dict:
    """Make the fact file safe to append to, and record anything discarded.

    Three damaged-tail shapes are handled:
    - a partial last line that is not valid JSON (with or without a trailing
      newline) -> truncate it and keep its exact bytes in the repair trace;
    - a complete JSON last line whose trailing newline was lost -> append the
      newline (without it the next append would concatenate two objects);
    - a clean file -> no-op.
    Returns {"discarded_bytes": n, "kept_seq": k, "action": str|None}. Idempotent.
    """
    p = paths(base)["facts"]
    if not p.exists():
        return {"discarded_bytes": 0, "kept_seq": 0, "action": None}
    raw = p.read_bytes()
    if not raw:
        return {"discarded_bytes": 0, "kept_seq": 0, "action": None}
    terminated = raw.endswith(b"\n")
    lines = raw.split(b"\n")
    if terminated and lines and lines[-1] == b"":
        lines = lines[:-1]
    last = len(lines) - 1
    while last >= 0 and not lines[last].strip():
        last -= 1
    if last < 0:
        return {"discarded_bytes": 0, "kept_seq": 0, "action": None}
    try:
        json.loads(lines[last].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        damaged = True
    else:
        damaged = False

    if not damaged and terminated:
        return {"discarded_bytes": 0, "kept_seq": last + 1, "action": None}
    if not damaged:
        # complete last line, only the newline is missing: restore it (traced)
        atomic_write(p, raw + b"\n")
        _trace_repair(base, {"kind": "repair", "action": "restore_missing_newline",
                             "discarded_len": 0, "at": int(time.time())})
        return {"discarded_bytes": 0, "kept_seq": last + 1, "action": "restore_missing_newline"}

    kept = b"".join(line + b"\n" for line in lines[:last])
    discarded = raw[len(kept):]
    atomic_write(p, kept)
    _trace_repair(base, {
        "kind": "repair",
        "action": "truncate_torn_tail",
        "discarded_len": len(discarded),
        "discarded_b64": base64.b64encode(discarded).decode("ascii"),
        "at": int(time.time()),
    })
    return {"discarded_bytes": len(discarded), "kept_seq": last,
            "action": "truncate_torn_tail"}


def _trace_repair(base, row: dict) -> None:
    repairs = paths(base)["ledger"] / "repairs.jsonl"
    repairs.parent.mkdir(parents=True, exist_ok=True)
    with open(repairs, "ab") as fh:
        fh.write(_canonical(row) + b"\n")
        fh.flush()
        os.fsync(fh.fileno())


def append_fact(base, kind: str, payload: dict, *, source: str = "runtime", fact_id=None) -> dict:
    repair_torn_tail(base)  # never concatenate onto a torn line
    rows = read_facts(base)
    seq = (rows[-1]["seq"] + 1) if rows else 1
    body = {
        "seq": seq,
        "id": fact_id or f"{kind}#{seq}",
        "kind": kind,
        "source": source,
        "payload": payload,
    }
    body["digest"] = fact_digest(body)
    p = paths(base)["facts"]
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "ab") as fh:
        fh.write(_canonical(body) + b"\n")
        fh.flush()
        os.fsync(fh.fileno())
    return body


def since(base, seq: int) -> list:
    return [f for f in read_facts(base) if f["seq"] > seq]
