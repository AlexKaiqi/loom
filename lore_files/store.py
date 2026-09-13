"""Host-authorized file versions, exact historical reads and installation records."""
import json
import os
from pathlib import Path
from .archive import pack, unpack
from .authority import FileAuthority, detached
from .history import HistoricalFiles
from .errors import FileError, require
from .install import Installer
from .metadata import walk
from .util import DEFAULT_LIMITS, Journal, canonical, digest, identity, ordinary_path
from .versions import Versions
from .window import StableWindow


class FileStore(HistoricalFiles, FileAuthority):
    def __init__(self, control_dir, authorization_checker, reference_checker, checkpoint=None, limits=None):
        require(callable(authorization_checker) and callable(reference_checker), "UNAUTHORIZED", "trusted checkers required")
        self.authorization_checker, self.reference_checker = authorization_checker, reference_checker
        self.checkpoint = checkpoint if checkpoint is not None else lambda label, record: None
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        require(set(self.limits) == set(DEFAULT_LIMITS), "UNSUPPORTED", "unknown limit")
        for key in ("max_entries", "max_logical_bytes", "max_archive_bytes"):
            require(type(self.limits[key]) is int and self.limits[key] > 0, "UNSUPPORTED", "invalid finite budget")
        require(type(self.limits["window_seconds"]) in (int, float) and
                0 < self.limits["window_seconds"] <= 10, "UNSUPPORTED", "invalid finite window")
        self.control = ordinary_path(control_dir)
        self.control.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.journal = Journal(self.control)
        with self.journal.lock():
            self.versions = Versions(self.control, self.limits)
        self.installer = Installer(self)

    def check_scope(self, ref, binding):
        require(ref["resource_id"] == binding["resource_id"] and ref["domain"] == binding["domain"],
                "REFERENCE_INVALID", "resource/domain association mismatch")

    def external_path(self, path):
        require(not path.is_relative_to(self.control) and not self.control.is_relative_to(path),
                "UNAUTHORIZED", "file resource overlaps control store")

    def bound_root(self, binding):
        require(binding["domain"] in ("surface", "workspace") and isinstance(binding["resource_id"], str),
                "REFERENCE_INVALID", "invalid resource domain")
        path = ordinary_path(binding["path"])
        self.external_path(path)
        try:
            actual = identity(path)
        except OSError as exc:
            raise FileError("STALE_BINDING", "bound root absent") from exc
        require(actual == binding["root"], "STALE_BINDING", "bound root replaced")
        return path

    def _existing(self, request_id, inputs):
        record = self.journal.get(request_id, inputs)
        if record is None:
            return None
        require(record["state"] == "complete", "PUBLICATION_UNKNOWN", "original request not confirmed")
        return record["result"]

    def _complete(self, request_id, inputs, result):
        self.journal.put(request_id, dict(inputs=inputs, state="complete", result=result))
        return result

    def capture(self, request_id, binding, coordination, base_ref=None):
        binding,coordination,base_ref=self.binding_value(binding),detached(coordination),detached(base_ref)
        inputs = dict(operation="capture", binding=binding, coordination=coordination, base_ref=base_ref)
        with self.journal.lock():
            root=self.bound_root(binding)
            context=self.context("capture",request_id=request_id,binding=binding,actual_root=identity(root),profile="host-v1",base_ref=base_ref,coordination=coordination)
            self.authorize(binding["authorization"],"capture",context)
            self.check_reference(coordination,"coordination",context)
            old = self._existing(request_id, inputs)
            if old is not None:
                self.versions.validate_bundle(old)
                return old
            root = self.bound_root(binding)
            if base_ref is not None:
                self.check_scope(base_ref, binding)
                self.versions.load(base_ref)
            with StableWindow([(root, binding["root"])], self.limits) as window:
                self.checkpoint("capture_leases_acquired", window.facts())
                window.assert_clean()
                tree, contents = walk(root, self.limits, tick=window.tick)
                raw = pack(tree, contents, self.limits)
                decoded, _ = unpack(raw, self.limits)
                require(canonical(decoded) == canonical(tree), "UNSUPPORTED", "archive encoding lost ordinary metadata")
                again, _ = walk(root, self.limits, tick=window.tick)
                require(canonical(again) == canonical(tree), "CHANGE_OBSERVED", "complete member set changed")
                window.assert_clean()
                window.verify_roots()
                result = self.versions.seal(raw, tree, binding, "host-v1", inputs)
                window.assert_clean()
                window.verify_roots()
                return self._complete(request_id, inputs, result)

    def import_archive(self,request_id,binding,archive_path,source_ref,base_ref,profile):
        binding,source_ref,base_ref=self.binding_value(binding),detached(source_ref),detached(base_ref)
        archive_path=ordinary_path(archive_path)
        inputs=dict(operation="import_archive",binding=binding,archive_path=str(archive_path),source_ref=source_ref,base_ref=base_ref,profile=profile)
        with self.journal.lock():
            require(profile=="host-v1","UNSUPPORTED","unknown materialization profile")
            root=self.bound_root(binding)
            try:
                fd=os.open(archive_path,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,"rb") as stream:raw=stream.read(self.limits["max_archive_bytes"]+1)
            except OSError as exc:raise FileError("ARCHIVE_INVALID","archive source unavailable") from exc
            context=self.context("import_archive",request_id=request_id,binding=binding,actual_root=identity(root),profile=profile,base_ref=base_ref,source_ref=source_ref,archive=dict(path=str(archive_path),bytes=len(raw),sha256=digest(raw)))
            self.authorize(binding["authorization"],"import_archive",context)
            self.check_reference(source_ref,"source",context)
            old=self._existing(request_id,inputs)
            if old is not None:
                self.versions.validate_bundle(old)
                return old
            if base_ref is not None:
                self.check_scope(base_ref,binding);self.versions.load(base_ref)
            tree,_=unpack(raw,self.limits)
            return self._complete(request_id,inputs,self.versions.seal(raw,tree,binding,profile,inputs))

    def install(self, request_id, intent, stopped_ref):
        intent,stopped_ref=detached(intent),detached(stopped_ref)
        with self.journal.lock():
            return self.installer.install(request_id, intent, stopped_ref)

    def query_install(self, request_id):
        with self.journal.lock():
            return self.installer.query(request_id)
