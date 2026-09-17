"""Runtime ledger: admission dedupe + round records.

Event != private ledger (glossary 禁混表). Accepted admission rows are derivable
from facts; rejected rows are the only original record of a refusal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .layout import paths


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def append_jsonl(path, row: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as fh:
        fh.write(_canonical(row) + b"\n")
        fh.flush()
        os.fsync(fh.fileno())
    return row


def read_jsonl(path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        # JSONL: "\n" only (A-R6). A corrupt row is an error, never a silent
        # truncation of the ledger history (asymmetric strictness with facts).
        line = raw_line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError("corrupt ledger row %d in %s: %s" % (number, path, exc)) from exc
    return out


def admission_digest(kind: str, payload: dict) -> str:
    return "sha256:" + __import__("hashlib").sha256(_canonical({"kind": kind, "payload": payload})).hexdigest()


def admit(base, foreign_id: str, kind: str, payload: dict, *, accepted: bool, fact: dict = None) -> tuple:
    """Fact Admission gate: idempotent by foreign id; conflict on changed content."""
    p = paths(base)["admission"]
    digest = admission_digest(kind, payload)
    for row in read_jsonl(p):
        if row.get("foreign_id") != foreign_id:
            continue
        if row.get("digest") != digest:
            raise ValueError(f"admission conflict: same foreign id {foreign_id!r}, different content")
        return row, False
    row = {
        "foreign_id": foreign_id,
        "kind": kind,
        "digest": digest,
        "decision": "accepted" if accepted else "rejected",
        "fact_id": (fact or {}).get("id"),
    }
    append_jsonl(p, row)
    return row, True


def record_round(base, record: dict) -> dict:
    return append_jsonl(paths(base)["rounds"], record)


def round_records(base) -> list:
    """Committed Round records only (start markers and repairs are not rounds)."""
    return [row for row in read_jsonl(paths(base)["rounds"]) if row.get("phase", "commit") == "commit"]


def last_row(base):
    rows = read_jsonl(paths(base)["rounds"])
    return rows[-1] if rows else None


def round_count(base) -> int:
    return len(round_records(base))
