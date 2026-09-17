"""Work directory layout: base tree, atomic writes, digests.

Design: design/g3/work-directory-landing.md §4.2 (base = 4 top-level entries),
§6 (commit ordering), §10 (layout_version).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

LAYOUT_VERSION = 1
WORK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

RESERVED_TOP = ("work.json", "harness", "surface", "session", "ledger", "derived")
RESERVED_SURFACE = ("content", "head", "facts.jsonl", "facts")
RESERVED_KIND_PREFIXES = ("sys.",)


def atomic_write(path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        dirfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path, value) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tree_digest(root) -> str:
    """Deterministic digest over a directory tree (paths + bytes)."""
    h = hashlib.sha256()
    root = Path(root)
    if not root.exists():
        return "sha256:" + h.hexdigest()
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root)).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        if p.is_file():
            h.update(p.read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def file_digest(path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref_digest(base, ref: str) -> str:
    p = Path(base) / ref
    if not p.exists():
        raise FileNotFoundError(f"missing declared ref: {ref}")
    return tree_digest(p) if p.is_dir() else file_digest(p)


def work_path(root, work_id: str) -> Path:
    if not WORK_ID.match(work_id or ""):
        raise ValueError(f"invalid work id: {work_id!r}")
    return Path(root) / work_id


def paths(base) -> dict:
    base = Path(base)
    return {
        "base": base,
        "work": base / "work.json",
        "harness": base / "harness",
        "manifest": base / "harness" / "manifest.json",
        "content": base / "surface" / "content",
        "head": base / "surface" / "head",
        "facts": base / "surface" / "facts.jsonl",
        "ledger": base / "ledger",
        "admission": base / "ledger" / "admission.jsonl",
        "rounds": base / "ledger" / "rounds.jsonl",
        "session": base / "session",
        "derived": base / "derived",
    }


AUTHORITY_FILE = ".lore-authority.json"


def authority_path(root) -> Path:
    return Path(root) / AUTHORITY_FILE


def register_authority(root, work_id: str, base) -> dict:
    """Record a work's real location in the host authority file (outside the work dir).

    Cross-work authorization is host-side state: a copied work directory carries
    its `relations` text but not an entry here, so a copy never inherits authority
    (landing §9-3 / I8).
    """
    path = authority_path(root)
    data = read_json(path) if path.exists() else {"schema": "lore-authority/v1", "works": {}}
    works = data.setdefault("works", {})
    works[work_id] = {"root": str(Path(base).resolve())}
    write_json(path, data)
    return works[work_id]


def authority_entry(root, work_id: str):
    path = authority_path(root)
    if not path.exists():
        return None
    return (read_json(path).get("works") or {}).get(work_id)


def stamp_manifest_digests(harness_dir) -> dict:
    """Fill per-ref digests into manifest.json (landing §4.5 R2).

    A harness template ships unstamped; registration stamps every declared ref
    (role entries, kind contracts, trigger `when`, view resolvers) with its
    content digest so load-time verification is exact, not existence-only.
    Idempotent: an already-correct digest is kept. Default-path fallbacks stay
    unstamped — they are covered by the whole-harness digest in work.json.
    """
    harness_dir = Path(harness_dir)
    mpath = harness_dir / "manifest.json"
    data = read_json(mpath)
    stamped = []

    def _stamp(entry: dict) -> None:
        ref = entry.get("ref")
        if not ref:
            return
        actual = ref_digest(harness_dir, ref)
        if entry.get("digest") != actual:
            entry["digest"] = actual
            stamped.append(ref)

    for entries in (data.get("roles") or {}).values():
        for entry in entries:
            _stamp(entry)
    for kind in (data.get("facts") or {}).get("kinds", []):
        contract = kind.get("contract")
        if contract and contract.get("ref"):
            _stamp(contract)
    for trig in (data.get("facts") or {}).get("triggers", []):
        when = trig.get("when")
        if when and when.get("ref"):
            _stamp(when)
    for view in data.get("views", []):
        resolver = view.get("resolver")
        if resolver and resolver.get("ref"):
            _stamp(resolver)
    if stamped:
        write_json(mpath, data)
    return {"stamped": stamped}


def create_work(root, work_id: str, harness_src, meta=None, userspaces=None) -> Path:
    base = work_path(root, work_id)
    if base.exists() and any(base.iterdir()):
        raise FileExistsError(f"work directory not empty: {base}")
    harness_src = Path(harness_src)
    if not (harness_src / "manifest.json").is_file():
        raise FileNotFoundError(f"harness template without manifest.json: {harness_src}")
    p = paths(base)
    p["content"].mkdir(parents=True, exist_ok=True)
    p["ledger"].mkdir(parents=True, exist_ok=True)
    shutil.copytree(harness_src, p["harness"])
    stamp = stamp_manifest_digests(p["harness"])
    p["facts"].write_bytes(b"")
    p["admission"].write_bytes(b"")
    p["rounds"].write_bytes(b"")
    work = {
        "schema": "lore-work/v1",
        "layout_version": LAYOUT_VERSION,
        "work_id": work_id,
        "state": {"lifecycle": "active"},
        "harness": {"digest": tree_digest(p["harness"])},
        "model_refs": {},
        "userspaces": list(userspaces or []),
        "relations": {"wants": [], "grants": []},
    }
    if meta:
        work.update(meta)
    write_json(p["work"], work)
    write_json(p["head"], {
        "layout_version": LAYOUT_VERSION,
        "revision": tree_digest(p["content"]),
        "facts_end": {"seq": 0, "digest": "sha256:" + hashlib.sha256(b"").hexdigest()},
        "round_id": None,
        "ledger_seq": 0,
    })
    register_authority(root, work_id, base)
    return base
