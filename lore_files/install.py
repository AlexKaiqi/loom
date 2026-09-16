"""One directory exchange per durable original request; restart reconciles objects."""
import ctypes
import sys
from pathlib import Path
from .errors import FileError, require
from .metadata import walk
from .util import canonical, identity, ordinary_path, sync_dir
from .window import StableWindow

_LIBC = None


def _renameat2():
    """Lazy Linux syscall binding; importing stays safe on every platform."""
    global _LIBC
    require(sys.platform == "linux", "UNSUPPORTED", "renameat2 exchange requires Linux")
    if _LIBC is None:
        _LIBC = ctypes.CDLL(None, use_errno=True)
        _LIBC.renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    return _LIBC.renameat2


class Installer:
    def __init__(self, store):
        self.store = store

    def _layout(self, intent):
        values = []
        for key in ("binding", "staged_path"):
            path = intent["binding"]["path"] if key == "binding" else intent[key]
            try:
                values.append(identity(ordinary_path(path)))
            except (OSError, FileError):
                values.append(None)
        return values

    def query(self, request_id):
        record = self.store.journal.get(request_id)
        require(record is not None and record["inputs"]["operation"] == "install",
                "PUBLICATION_UNKNOWN", "original install request absent")
        intent = record["inputs"]["intent"]
        current, retired = self._layout(intent)
        old, staged = intent["binding"]["root"], intent["staged_root"]
        if (current, retired) == (old, staged):
            status = "not_installed" if record["state"] == "intent" else "conflicting"
        elif (current, retired) == (staged, old):
            status = "installed_pending_confirmation"
        elif current is None or retired is None:
            status = "unknown"
        else:
            status = "conflicting"
        observation_error = None
        if status in ("not_installed", "installed_pending_confirmation"):
            # Surviving inode identities alone do not prove content stayed intact
            # while this process was absent. Revalidate both actual complete sets.
            _, base, _ = self.store.versions.load(intent["base_ref"])
            _, output, _ = self.store.versions.load(intent["version_ref"])
            expected = (base, output) if status == "not_installed" else (output, base)
            paths = (ordinary_path(intent["binding"]["path"]), ordinary_path(intent["staged_path"]))
            try:
                with StableWindow(list(zip(paths, (current, retired))), self.store.limits) as window:
                    trees = tuple(walk(path, self.store.limits, tick=window.tick)[0] for path in paths)
                    window.assert_clean()
                    window.verify_roots()
                    if canonical(trees) != canonical(expected):
                        status = "conflicting"
            except (FileError, OSError) as exc:
                status = "unknown"
                observation_error = getattr(exc, "code", "OBSERVATION_LOST")
        if record.get("state") == "uncertain":
            status = "conflicting"
        return dict(status=status, observation_error=observation_error,
                    original_intent=intent, current_root=current,
                    retired_root=retired, version_ref=intent["version_ref"],
                    stopped_ref=record["inputs"]["stopped_ref"], request_id=request_id)

    def install(self, request_id, intent, stopped_ref):
        inputs = dict(operation="install", intent=intent, stopped_ref=stopped_ref)
        old_record = self.store.journal.get(request_id, inputs)
        current_root,staged_root=self._layout(intent)
        context=self.store.context("install",request_id=request_id,intent=intent,stopped_ref=stopped_ref,actual_current_root=current_root,actual_staged_root=staged_root)
        self.store.authorize(intent["binding"]["authorization"], "install",context)
        self.store.check_reference(intent["intent_ref"], "intent",context)
        self.store.check_reference(stopped_ref, "stop",context)
        require(stopped_ref.get("execution_id") == intent.get("execution_id") and
                canonical(stopped_ref.get("generation")) == canonical(intent.get("generation")),
                "REFERENCE_INVALID", "stop refers to another execution or generation")
        require(intent["resource_id"] == intent["binding"]["resource_id"] and
                intent["domain"] == intent["binding"]["domain"], "REFERENCE_INVALID", "intent resource mismatch")
        if old_record is not None:
            # An existing durable intent is never permission for another exchange.
            return self.query(request_id)
        bound = intent["binding"]
        root, staged = ordinary_path(bound["path"]), ordinary_path(intent["staged_path"])
        self.store.external_path(root)
        self.store.external_path(staged)
        require(root != staged and not root.is_relative_to(staged) and not staged.is_relative_to(root),
                "UNSUPPORTED", "overlapping install roots")
        require(bound["root"]["dev"] == intent["staged_root"]["dev"], "UNSUPPORTED", "cross-filesystem exchange")
        for ref in (intent["base_ref"], intent["version_ref"]):
            self.store.check_scope(ref, bound)
        _, base_tree, _ = self.store.versions.load(intent["base_ref"])
        _, output_tree, _ = self.store.versions.load(intent["version_ref"])
        record = dict(inputs=inputs, state="intent")
        self.store.journal.put(request_id, record)
        swapped = False
        try:
            with StableWindow([(root, bound["root"]), (staged, intent["staged_root"])], self.store.limits) as window:
                before, _ = walk(root, self.store.limits, tick=window.tick)
                after, _ = walk(staged, self.store.limits, tick=window.tick)
                require(before == base_tree and after == output_tree, "BASE_CHANGED", "actual base or staged set changed")
                window.assert_clean()
                window.verify_roots()
                self.store.checkpoint("before_exchange", dict(request_id=request_id, **window.facts()))
                window.assert_clean()
                window.verify_roots()
                result = _renameat2()(-100, bytes(root), -100, bytes(staged), 2)
                if result != 0:
                    raise FileError("PUBLICATION_UNKNOWN", "rename exchange failed errno=" + str(ctypes.get_errno()))
                swapped = True
                # This exact point must remain before the local installed record for crash reconciliation.
                self.store.checkpoint("after_exchange_before_record", dict(request_id=request_id))
                sync_dir(root.parent)
                if staged.parent != root.parent:
                    sync_dir(staged.parent)
                window.assert_clean(exchange=(root, staged))
                window.verify_roots(exchanged=True)
                actual_new, _ = walk(root, self.store.limits, tick=window.tick)
                actual_old, _ = walk(staged, self.store.limits, tick=window.tick)
                require(actual_new == output_tree and actual_old == base_tree,
                        "BASE_CHANGED", "actual directory changed at exchange")
                window.assert_clean()
                record["state"] = "installed"
                self.store.journal.put(request_id, record)
                window.assert_clean()
                window.verify_roots(exchanged=True)
                self.store.checkpoint("after_record_before_reply", dict(request_id=request_id))
                window.assert_clean()
            return self.query(request_id)
        except FileError:
            if swapped:
                record["state"] = "uncertain"
                self.store.journal.put(request_id, record)
            raise
