"""Observes raw NATS sequence records and immutable input bytes, never E reports."""
import hashlib
import json
from pathlib import Path

def raw_history(observed, expected):
    if not isinstance(observed,list) or len(observed)!=len(expected):
        raise AssertionError("missing or duplicate history")
    for actual,want in zip(observed,expected):
        if set(actual)!={"sequence","subject","data"} or type(actual["sequence"]) is not int:
            raise AssertionError("invalid raw NATS record")
        if actual != want:
            raise AssertionError("raw identity/order/content mismatch")

def input_files(directory, expected_files):
    directory=Path(directory)
    if not expected_files:
        raise AssertionError("no independently specified input files")
    for relative, raw in expected_files.items():
        p=directory/relative
        if p.is_symlink() or not p.is_file():
            raise AssertionError("missing or aliased input")
        actual=p.read_bytes()
        if actual != raw:
            raise AssertionError("input bytes not equal original source")
    return {p:hashlib.sha256(raw).hexdigest() for p,raw in expected_files.items()}

def application_origin(envelope, source):
    if envelope.get("origin")!="application" or envelope.get("source")!=source:
        raise AssertionError("source spoofed or application promoted to system fact")
