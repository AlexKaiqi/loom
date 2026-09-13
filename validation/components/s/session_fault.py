"""S025 storage-fault fixture. Ordinary bytes, never a confirmed Pi owner.

Only the trusted test peer calls prepare_fault. X still validates its ordinary
snapshot/hash/profile; SnapshotStore never confirms this corrupt copy.
"""
import base64
import copy
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import uuid

from validation.components.x_node_profile.artifacts import (
    archive_bytes, canonical, file_fact, read_ref, save, sha_bytes, snapshot,
)
from lore_session.snapshots import SnapshotStore
from validation.components.s.f_peer import require

FAULT = "append_complete_invalid_jsonl_line"
BAD_LINE = b'{"lore_fixture_invalid":]\n'
SCOPE = ("namespace", "surface_id", "session_id", "session_generation")


def _protected(plans, reference, scope):
    require("fixture_fault_ref" not in reference, "fault cannot replace the protected valid source")
    bundle, full = plans._snapshot({"session_snapshot_ref": reference}, scope)
    owner_ref = reference["owner_record_ref"]
    owner = json.loads(read_ref(owner_ref, 2097152)[1])
    charge = json.loads(read_ref(reference["storage_charge_ref"], 2097152)[1])
    owner_path = Path(owner_ref["path"])
    require(owner_path.name == "owner.json", "original confirmation owner file required")
    store = SnapshotStore(owner_path.parent.parent, scope["namespace"], plans.register,
                          global_budget_bytes=charge["global_budget_bytes"])
    require(store.query(owner["confirmation_request_id"]) == bundle,
            "protected source is not the real original S confirmation")
    record = json.loads(file_fact(full["record_path"], 2097152)[1])
    expected = dict(scope, original_execution=record["original_execution"])
    observed = snapshot(full, expected)
    paths = [full["archive_path"], full["manifest_path"], full["record_path"],
             owner_ref["path"], reference["storage_charge_ref"]["path"],
             str(owner_path.with_name("request.json")), str(owner_path.with_name("result.json"))]
    protected = {path: file_fact(path)[0] for path in paths}
    return observed, expected, protected


def _same_originals(protected):
    require(all(file_fact(path)[0] == fact for path, fact in protected.items()),
            "protected original bytes or inode changed")


def _write_raw(path, raw):
    require(len(raw) <= 18874368, "fault fixture exceeds original archive limit")
    with path.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return file_fact(path)[0]


def prepare_fault(plans, reference, fault, authority):
    """Return an explicitly unconfirmed fault envelope; no Node or Engine calls."""
    require(authority == plans.peer.authority and fault == FAULT,
            "explicit actual fixture authority and original S025 fault required")
    require("fixture_fault_ref" not in reference, "nested storage fault forbidden")
    owner = json.loads(read_ref(reference["owner_record_ref"], 2097152)[1])
    scope = owner["scope"]
    require(set(scope) == set(SCOPE) and scope["namespace"] == plans.namespace,
            "protected original Session scope differs")
    original, expected, protected = _protected(plans, reference, scope)
    files = original["files"]
    metadata = json.loads(files["metadata.json"])
    selected = PurePosixPath(metadata["path"]).relative_to(metadata["cwd"]).as_posix()
    require(selected in files and files[selected].endswith(b"\n"), "complete original JSONL required")
    altered = files[selected] + BAD_LINE
    raw = read_ref(reference["original_archive"])[1]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as source:
        with tarfile.open(fileobj=buffer, mode="w:", format=tarfile.PAX_FORMAT) as target:
            for member in source:
                item = copy.deepcopy(member)
                name = member.name[2:] if member.name.startswith("./") else member.name
                data = source.extractfile(member).read() if member.isfile() else None
                if name == selected:
                    data = altered; item.size = len(data); item.pax_headers.pop("size", None)
                target.addfile(item, io.BytesIO(data) if data is not None else None)
    raw = buffer.getvalue()
    entries, changed, logical = archive_bytes(raw)
    require(changed == {**files, selected: altered}, "fault altered another original member")
    expected_entries = copy.deepcopy(original["manifest"]["entries"])
    expected_entries[selected].update(byte_length=len(altered), sha256=sha_bytes(altered))
    require(entries == expected_entries, "fault altered original metadata or member identity")
    folder = plans.root / "fault-inputs" / uuid.uuid4().hex
    folder.mkdir(mode=0o700, parents=True)
    archive_ref = _write_raw(folder / "fault.tar", raw)
    require(archive_ref["root"] != protected[reference["original_archive"]["path"]]["root"],
            "fault copy aliases protected original")
    manifest = {**original["manifest"], "entries": entries, "logical_bytes": logical,
                "archive_sha256": archive_ref["sha256"], "archive_bytes": archive_ref["bytes"]}
    save(folder / "manifest.json", manifest); manifest_ref = file_fact(folder / "manifest.json")[0]
    record = {**original["record"], "archive": archive_ref, "manifest": manifest_ref}
    save(folder / "record.json", record); record_ref = file_fact(folder / "record.json")[0]
    full = {**reference["snapshot_ref"], "id": "unconfirmed-fault-"+folder.name,
            "record_path": record_ref["path"], "record_sha256": record_ref["sha256"]}
    for prefix, fact in (("archive", archive_ref), ("manifest", manifest_ref)):
        for key in ("path", "sha256", "bytes"): full[prefix+"_"+key] = fact[key]
    fault_record = dict(schema="lore-s-validation-storage-fault/v1", fault=FAULT,
        semantic_state="UNCONFIRMED_CORRUPT_FIXTURE", authority_sha256=sha_bytes(canonical(authority)),
        scope=scope, protected_reference=reference, protected_files=protected, expected=expected,
        jsonl_relative_path=selected, appended_line_b64=base64.b64encode(BAD_LINE).decode(),
        snapshot_ref=full, original_archive=archive_ref,
        ownership_note="owner=S names the existing X ordinary source domain only; no SnapshotStore confirmation or ownership-transfer receipt exists for this copy")
    save(folder / "fault.json", fault_record)
    envelope = dict(owner="S", **scope, snapshot_ref=full, original_archive=archive_ref,
                    fixture_fault_ref=file_fact(folder / "fault.json")[0])
    save(folder / "envelope.json", envelope)
    _same_originals(protected)
    resolve_fault_snapshot(plans, envelope, scope)
    return envelope


def resolve_fault_snapshot(plans, envelope, scope):
    """Narrow trusted test branch. Normal snapshots still require real owner/charge."""
    require(set(envelope) == {"owner", *SCOPE, "snapshot_ref", "original_archive", "fixture_fault_ref"},
            "fault envelope cannot claim a valid owner or charge")
    ref = envelope["fixture_fault_ref"]; path = Path(ref["path"])
    root = plans.root / "fault-inputs"
    require(path.name == "fault.json" and path.parent.parent == root and path.resolve(strict=True) == path,
            "fault source outside this explicit trusted fixture")
    fault = json.loads(read_ref(ref, 2097152)[1])
    require(fault["schema"] == "lore-s-validation-storage-fault/v1" and fault["fault"] == FAULT and
            fault["semantic_state"] == "UNCONFIRMED_CORRUPT_FIXTURE" and
            fault["authority_sha256"] == sha_bytes(canonical(plans.peer.authority)), "fault authority differs")
    require(fault["scope"] == scope and all(envelope[k] == scope[k] for k in SCOPE) and
            envelope["owner"] == "S" and fault["snapshot_ref"] == envelope["snapshot_ref"] and
            fault["original_archive"] == envelope["original_archive"], "fault complete association differs")
    original, expected, protected = _protected(plans, fault["protected_reference"], scope)
    require(fault["protected_files"] == protected and fault["expected"] == expected,
            "fault source is not the exact retained original")
    observed = snapshot(envelope["snapshot_ref"], expected)
    require(read_ref(envelope["original_archive"])[0] == observed["archive_fact"], "fault archive ref differs")
    selected = fault["jsonl_relative_path"]
    metadata = json.loads(original["files"]["metadata.json"])
    require(selected == PurePosixPath(metadata["path"]).relative_to(metadata["cwd"]).as_posix(),
            "fault does not name the original metadata-selected JSONL")
    require(fault["appended_line_b64"] == base64.b64encode(BAD_LINE).decode() and selected in original["files"] and
            observed["files"] == {**original["files"], selected: original["files"][selected]+BAD_LINE},
            "not the exact preregistered complete invalid line")
    _same_originals(protected)
    plans.register("snapshot", envelope["snapshot_ref"], expected)
    # No storage-charge or owner receipt is invented for the invalid Session.
    return dict(snapshot_ref=envelope["snapshot_ref"], fixture_fault_ref=ref), envelope["snapshot_ref"]
