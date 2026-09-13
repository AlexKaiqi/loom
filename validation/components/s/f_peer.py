"""Trusted S validation peer over real F; fixture indexes contain only original references."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from lore_files import FileStore

LIMITS = dict(max_entries=1024, max_logical_bytes=2097152,
              max_archive_bytes=4194304, window_seconds=10)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def identity(path):
    st = Path(path).lstat()
    return dict(dev=st.st_dev, ino=st.st_ino)


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".new-" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(canonical(value) + b"\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def file_fact(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), "actual regular source required")
    raw = path.read_bytes()
    require(len(raw) <= 4194304, "fixture source exceeds fixed F archive budget")
    return dict(path=str(path), bytes=len(raw), sha256=digest(raw))


class Peer:
    def __init__(self, root, authority):
        self.root = Path(root).resolve(strict=True)
        self.case_root = self.root.parent.parent
        self.authority = copy.deepcopy(authority)
        require(isinstance(authority, dict) and authority, "explicit trusted fixture authority required")
        self.index_path = self.root / "fixture-manifest.json"
        self.index = json.loads(self.index_path.read_bytes()) if self.index_path.exists() else {
            "schema": "lore-s-f-fixture/v1", "authority": authority, "inputs": {},
            "harnesses": {}, "capabilities": {}, "execution_outputs": {}, "outputs": {}}
        require(self.index["authority"] == authority, "fixture authority changed")
        self.allowed = {}
        self.store = FileStore(self.root / "F-control", self.auth, self.reference, limits=LIMITS)

    def check(self, kind, value, operation, context):
        accepted = (value, context) == self.allowed.get((kind, operation))
        with (self.root / "F-authority-calls.jsonl").open("ab") as stream:
            stream.write(canonical(dict(kind=kind, value=value, operation=operation, context=context, accepted=accepted)) + b"\n")
        return accepted

    def auth(self, value, operation, context):
        return self.check("authorization", value, operation, context)

    def reference(self, value, operation, context):
        return self.check("reference", value, operation, context)

    def allow(self, kind, operation, value, context):
        self.allowed[kind, operation] = (copy.deepcopy(value), copy.deepcopy(context))

    def area(self, label):
        path = self.root / (label + "-" + uuid.uuid4().hex)
        path.mkdir(mode=0o700)
        return path

    def source(self, path):
        path = Path(path)
        require(path.is_absolute() and not path.is_symlink(), "ordinary absolute fixture source required")
        path = path.resolve(strict=True)
        require(path.is_dir() and path.is_relative_to(self.case_root), "source outside this trusted fixture scope")
        return path

    def capture(self, source, role):
        source = self.source(source)
        rid = "s-fixture-" + role + "-" + uuid.uuid4().hex
        grant = dict(owner="trusted-S-validation", id=rid, authority=self.authority)
        binding = dict(resource_id=rid, domain="workspace" if role == "workspace" else "surface",
                       path=str(source), root=identity(source), revision=1, authorization=grant)
        coordination = dict(owner="controlled-writer-fixture", id=rid, binding=binding)
        context = dict(schema="lore-f-authority-context/v1", operation="capture", request_id=rid,
                       binding=binding, actual_root=binding["root"], profile="host-v1", base_ref=None, coordination=coordination)
        self.allow("authorization", "capture", grant, context)
        self.allow("reference", "coordination", coordination, context)
        bundle = self.store.capture(rid, binding, coordination)
        parent = self.area("view")
        target = parent / role
        context = dict(schema="lore-f-authority-context/v1", operation="materialize", request_id="read-" + rid,
                       version_ref=bundle["version_ref"], target_path=str(target),
                       target_parent=dict(path=str(parent), root=identity(parent)), profile="host-v1")
        self.allow("authorization", "materialize", grant, context)
        materialized = self.store.materialize("read-" + rid, bundle["version_ref"], str(target), grant)
        return dict(bundle=bundle, materialized=materialized, original_source=dict(path=str(source), root=binding["root"]))

    def original_file(self, view, name):
        manifest = json.loads(Path(view["bundle"]["manifest_path"]).read_bytes())
        entry = manifest["tree"]["entries"][name]
        require(entry["kind"] == "file", "reference is not a real F file")
        ref = dict(owner="F", kind="file", path=name, version_ref=view["bundle"]["version_ref"], sha256=entry["sha256"])
        raw = self.read_F(ref)
        path = Path(view["materialized"]["path"]) / name
        require(path.read_bytes() == raw, "F materialized bytes differ from actual historical read")
        return ref, file_fact(path)

    def read_F(self, ref):
        grant = dict(owner="trusted-S-validation", authority=self.authority, reference_sha256=digest(canonical(ref)))
        context = dict(schema="lore-f-authority-context/v1", operation="read_reference", reference=ref)
        self.allow("authorization", "read_reference", grant, context)
        return self.store.read_reference(ref, grant)

    def document(self, section, body):
        folder = self.area(section + "-source")
        save(folder / "descriptor.json", body)
        view = self.capture(folder, section)
        full, actual = self.original_file(view, "descriptor.json")
        compact = dict(id=digest(canonical(full)), sha256=actual["sha256"])
        descriptor = dict(ref=compact, full_ref=full, document=body, F=view)
        self.index[section][compact["id"]] = descriptor
        return compact, descriptor

    def lookup(self, section, ref):
        item = self.index[section][ref["id"]]
        require(ref == item["ref"], "compact reference changed")
        raw = self.read_F(item["full_ref"])
        require(digest(raw) == ref["sha256"] and json.loads(raw) == item["document"], "actual F descriptor changed")
        return item

    def prepare_fixture_input(self, **params):
        source = {role: self.capture(params[key], role) for role, key in
                  [("surface", "surface"), ("workspace", "workspace"), ("events", "input_dir"), ("originals", "originals")]}
        combined = self.area("combined-input-source")
        shutil.copytree(source["events"]["materialized"]["path"], combined, dirs_exist_ok=True, symlinks=True)
        require(not (combined / "surface").exists() and not (combined / "originals").exists(), "input namespace collision")
        for role in ("surface", "originals"):
            shutil.copytree(source[role]["materialized"]["path"], combined / role, symlinks=True)
        input_view = self.capture(combined, "input")
        harness_source = self.area("harness-source")
        originals = []
        for prefix, names in [("lore_session/node", ["entry", "adapter", "session", "callbacks", "stdio", "common"]),
                              ("harnesses/minimal", ["index", "projection"])]:
            for name in names:
                original = ROOT / prefix / (name + ".mts")
                target = harness_source / prefix / original.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target); originals.append(file_fact(original))
        harness_view = self.capture(harness_source, "harness")
        harness_ref, _ = self.document("harnesses", dict(version=params["version"], code=harness_view, source_files=originals,
                                                       entry="lore_session/node/entry.mts", harness_entry="harnesses/minimal/index.mts"))
        capability_ref, _ = self.document("capabilities", dict(targets=["runtime", "workspace"], limits={}))
        original_refs = {}
        if (Path(source["originals"]["materialized"]["path"]) / "log").exists():
            full, retained = self.original_file(source["originals"], "log")
            _, selected = self.original_file(input_view, "originals/log")
            original_refs["log"] = dict(source_ref=full, retained=retained, selected=selected,
                                        read_path="/input/originals/log", bytes=retained["bytes"], sha256=retained["sha256"])
        body = dict(version=params["version"], source_F=source, input=input_view, workspace=source["workspace"],
                    harness_ref=harness_ref, capability_ref=capability_ref, original_refs=original_refs,
                    paths=dict(surface="/input/surface", events="/input/events.jsonl", feedback="/input/feedback.txt",
                               runtime="/input/surface", workspace="/workspace"))
        input_ref, item = self.document("inputs", body)
        self.index["latest_input_ref"] = input_ref
        return dict(input_ref=input_ref, harness_ref=harness_ref, capability_ref=capability_ref,
                    original_refs={name: value["source_ref"] for name, value in original_refs.items()},
                    fixture_manifest=str(self.index_path), materialized_paths=dict(input=input_view["materialized"],
                                                                                workspace=source["workspace"]["materialized"], harness=harness_view["materialized"]))

    def prepare_fixture_limit_binding(self, original, limits, **_):
        require(set(limits) == {"max_steps"} and type(limits["max_steps"]) is int and 0 < limits["max_steps"] <= 64, "invalid fixture step budget")
        body = copy.deepcopy(self.lookup("capabilities", original)["document"])
        body["limits"] = limits
        return self.document("capabilities", body)[0]

    def prepare_alternate_fixture_binding(self, field, original, **_):
        section = {"input_ref": "inputs", "harness_ref": "harnesses", "capability_ref": "capabilities"}[field]
        body = copy.deepcopy(self.lookup(section, original)["document"])
        body["fixture_revision"] = uuid.uuid4().hex
        return self.document(section, body)[0]

    def latest(self):
        return self.lookup("inputs", self.index["latest_input_ref"])

    def fixture_full_output_reference(self, **_):
        return self.latest()["document"]["original_refs"]["log"]["source_ref"]

    def resolve_fixture_original(self, **_):
        value = self.latest()["document"]["original_refs"]["log"]
        require(Path(value["retained"]["path"]).read_bytes() == self.read_F(value["source_ref"]), "protected original bytes changed")
        return value["retained"]

    def test_corrupt_fixture_read(self, same_size, **_):
        require(same_size is True, "only original same-size fault is prepared")
        item = self.latest(); body = item["document"]
        folder = self.area("fault-read-source")
        shutil.copytree(body["input"]["materialized"]["path"], folder, dirs_exist_ok=True, symlinks=True)
        target = folder / "originals/log"; raw = target.read_bytes(); require(raw, "empty original cannot be same-size corrupted")
        target.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        item["read_copy_override"] = self.capture(folder, "input")
        item["fault"] = dict(kind="same_size_read_corruption", original=body["original_refs"]["log"]["source_ref"], actual=file_fact(Path(item["read_copy_override"]["materialized"]["path"]) / "originals/log"))
        self.resolve_fixture_original()
        return dict(applied=True, fault=item["fault"])

    def read_fixture_effects(self, original_execution_ref, **_):
        key = digest(canonical(original_execution_ref))
        mapping = self.index["execution_outputs"][key]
        require(mapping["original_execution_ref"] == original_execution_ref, "original X execution reference differs")
        # Resolve original X immutable bytes unchanged; associations live only in this trusted fixture index.
        fact = mapping["original_receipt_file"]
        actual = file_fact(fact["path"])
        require(actual == fact, "original X receipt bytes changed")
        raw = Path(fact["path"]).read_bytes()
        require(json.loads(raw) == mapping["original_receipt"], "original X receipt content changed")
        pieces = []
        for output in mapping["files"]:
            data = self.read_F(output["full_ref"])
            require(Path(output["file_ref"]["path"]).read_bytes() == data, "published original F output differs")
            pieces.append(data)
            self.index["outputs"][output["target"]] = output
        folder = self.area("effect-read-source"); (folder / "effects").write_bytes(b"".join(pieces))
        view = self.capture(folder, "effects"); _, returned = self.original_file(view, "effects")
        return returned

    def resolve_fixture_output(self, target, **_):
        require(target in ("runtime", "workspace"), "unknown ordinary output target")
        output = self.index["outputs"][target]
        require(Path(output["file_ref"]["path"]).read_bytes() == self.read_F(output["full_ref"]), "actual output differs from F original")
        return output["file_ref"]

    def call(self, method, params):
        require(params.get("authority") == self.authority, "untrusted fixture caller")
        allowed = {"prepare_fixture_input", "prepare_fixture_limit_binding", "prepare_alternate_fixture_binding",
                   "fixture_full_output_reference", "resolve_fixture_original", "test_corrupt_fixture_read",
                   "read_fixture_effects", "resolve_fixture_output"}
        require(method in allowed, "unknown original S F fixture method")
        result = getattr(self, method)(**params)
        save(self.index_path, self.index)
        return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--authority", type=Path, required=True)
    options = parser.parse_args()
    request = json.loads(sys.stdin.buffer.read(2097153))
    require(request["protocol"] == "LORE_COMPONENT_TEST/1", "unknown fixture protocol")
    root = Path(request["fixture_root"]); require(root.is_absolute() and root.is_dir() and not root.is_symlink(), "real fixture root required")
    authority = json.loads(options.authority.read_bytes())
    with (root / ".fixture-lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        peer = Peer(root, authority)
        try: result = dict(result=peer.call(request["method"], request["params"]))
        except KeyError as error: result = dict(status="MISSING", error="actual dependency/fixture reference absent: " + str(error))
        except Exception as error: result = dict(error=repr(error))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
