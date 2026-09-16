"""Trusted one-pending-response bridge. Pi owns history; this module never drives it."""
import copy
import hashlib
import os
from pathlib import Path

from lore_provider import WireClient, WireError
from lore_provider.jsoncodec import encode, strict_load
from lore_provider.persistence import save_json
from lore_provider.request import BINDING, MODEL, encode_request
from lore_provider.response import normalize
from lore_provider.transport import _request_path


class ProviderBridgeError(WireError):
    def __init__(self, reason):
        super().__init__(reason)
        self.code = reason


def require(value, reason="invalid_request"):
    if not value:
        raise ProviderBridgeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def same(left, right):
    return encode(left) == encode(right)


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ProviderBridge:
    """Constructor and original_scope are trusted host inputs, never Node fields.

    model_scope: model, max_completion_tokens, session_scope and the three exact
    Wire compact references. original_scope additionally binds operation_id,
    response_entry_id and source_result_ref. query has no transport side effects.
    Only a fresh, accepted wire may be delivered by the host's original callback;
    a retained receipt is evidence for reconciliation, not permission to replay.
    """
    def __init__(self, root, endpoint, model_scope, credential_provider=None, timeout=2.0):
        self.root = Path(root).absolute()
        require(self.root.parent.is_dir() and self.root.resolve() == self.root)
        self.endpoint, self.model_scope = copy.deepcopy((endpoint, model_scope))
        require(type(endpoint) is dict and set(endpoint) in
                ({"scheme", "host", "port"}, {"scheme", "host", "port", "path_prefix"}))
        require(endpoint["scheme"] in ("http", "https") and type(endpoint["host"]) is str
                and endpoint["host"] and type(endpoint["port"]) is int and 0 < endpoint["port"] <= 65535)
        require(type(model_scope) is dict and set(model_scope) ==
                {"model", "max_completion_tokens", "reasoning_effort", "session_scope", "input_ref", "harness_ref", "capability_ref"})
        # Bridge cap revised 2026-09-14 (m01-output-budget amendment): 2048 -> 16384.
        require(model_scope["model"] == MODEL and type(model_scope["max_completion_tokens"]) is int
                and 0 < model_scope["max_completion_tokens"] <= 16384)
        # Bridge timeout ceiling revised 2026-09-14 (m01-output-budget amendment):
        # 60 -> 300 so real reasoning-model round trips fit the transport budget.
        require(type(timeout) in (int, float) and 0 < timeout <= 300)
        require(model_scope["reasoning_effort"] in ("low", "medium", "high", "max"))
        require(credential_provider is None or callable(credential_provider))
        self.credential_provider, self.timeout = credential_provider, timeout
        scope = model_scope["session_scope"]
        require(type(scope) is dict and set(scope) == {"namespace", "surface_id", "session_id", "session_generation"})
        require(all(type(scope[k]) is str and 0 < len(scope[k]) <= 256 for k in ("namespace", "surface_id", "session_id")))
        require(type(scope["session_generation"]) is int and 1 <= scope["session_generation"] <= 9007199254740991)
        for key in ("input_ref", "harness_ref", "capability_ref"):
            ref = model_scope[key]
            require(type(ref) is dict and set(ref) == {"id", "sha256"})
            require(type(ref["id"]) is str and ref["id"] and type(ref["sha256"]) is str
                    and len(ref["sha256"]) == 64 and all(c in "0123456789abcdef" for c in ref["sha256"]))

    def _scope(self, binding):
        require(type(binding) is dict and set(binding) == BINDING | {"session_scope", "source_result_ref"})
        require(same(binding["session_scope"], self.model_scope["session_scope"]), "conflict")
        require(binding["session_id"] == self.model_scope["session_scope"]["session_id"], "conflict")
        for key in ("input_ref", "harness_ref", "capability_ref"):
            require(same(binding[key], self.model_scope[key]), "conflict")
        for key in ("operation_id", "response_entry_id"):
            require(type(binding[key]) is str and 0 < len(binding[key]) <= 256)
        require(binding["source_result_ref"] is None or type(binding["source_result_ref"]) is dict)
        require(len(encode(binding)) <= 1048576)
        return "s-provider-" + digest(encode([binding["session_scope"], binding["operation_id"], binding["response_entry_id"]]))

    def _prepared(self, binding, frame):
        effect = self._scope(binding)
        require(type(frame) is dict and set(frame) ==
                {"type", "session_id", "operation_id", "effect_id", "response_entry_id", "payload"})
        require(frame["type"] == "provider.request")
        require(frame["effect_id"] == effect and all(frame[k] == binding[k]
                for k in ("session_id", "operation_id", "response_entry_id")), "conflict")
        require(len(encode(frame)) <= 1048576)
        wire_scope = {k: copy.deepcopy(binding[k]) for k in BINDING}
        intent = dict(binding=wire_scope, model=self.model_scope["model"],
                      max_completion_tokens=self.model_scope["max_completion_tokens"],
                      reasoning_effort=self.model_scope["reasoning_effort"], context=copy.deepcopy(frame["payload"]))
        raw = encode_request(intent, wire_scope)  # Full validation precedes directory claim or credential read.
        prepared = dict(schema="lore-s-provider-prepared/1", effect_id=effect,
                        binding=copy.deepcopy(binding), model_scope=self.model_scope,
                        endpoint=self.endpoint, timeout=self.timeout, frame=copy.deepcopy(frame))
        require(len(encode(prepared)) <= 2097152)
        return prepared, intent, raw

    def _folder(self, effect):
        return self.root / digest(effect.encode("utf-8"))

    def _read(self, path, limit):
        require(path.resolve() == path and path.is_file() and not path.is_symlink(), "integrity_mismatch")
        st = path.stat()
        require(st.st_size <= limit, "integrity_mismatch")
        raw = path.read_bytes()
        require(len(raw) == st.st_size, "integrity_mismatch")
        return raw

    def _file_ref(self, path, limit):
        raw = self._read(path, limit)
        return dict(path=str(path), sha256=digest(raw), bytes=len(raw))

    def _wire_files(self, folder):
        return {name: self._file_ref(folder / "wire" / name, limit) for name, limit in
                [("request.body", 65536), ("response.body", 1048576), ("transport.json", 65536),
                 ("association.json", 65536), ("response.headers.json", 1048576)]}

    def _verify_wire(self, folder, intent, raw_request, wire):
        home = folder / "wire"
        require(self._read(home / "request.body", 65536) == raw_request, "integrity_mismatch")
        raw = self._read(home / "response.body", 1048576)
        transport = strict_load(self._read(home / "transport.json", 65536))
        association = strict_load(self._read(home / "association.json", 65536))
        require(same(association, dict(binding=intent["binding"], scope=intent["binding"],
                request_sha256=digest(raw_request), response_sha256=digest(raw))), "integrity_mismatch")
        expected = dict(request=dict(method="POST",
                        path=_request_path(self.endpoint), size=len(raw_request),
                        sha256=digest(raw_request)), transport=transport,
                        artifacts={key+"_path": str(home / name) for key, name in
                                   [("request", "request.body"), ("response", "response.body"),
                                    ("transport", "transport.json"), ("association", "association.json")]})
        try:
            expected.update(accepted=True, normalized=normalize(raw, transport))
        except WireError as error:
            expected.update(accepted=False, reason=error.reason)
        require(same(expected, wire), "integrity_mismatch")

    def _existing(self, effect, binding, prepared=None):
        folder = self._folder(effect)
        unknown = dict(status="UNKNOWN", effect_id=effect, fresh=False)
        if not folder.exists():
            return unknown
        require(folder.is_dir() and not folder.is_symlink(), "integrity_mismatch")
        original = folder / "prepared.json"
        if not original.exists():
            return unknown
        original_bytes = self._read(original, 2097152)
        saved = strict_load(original_bytes)
        require(same(saved["binding"], binding), "conflict")
        actual, intent, raw = self._prepared(binding, saved["frame"])
        require(same(saved, actual) and (prepared is None or same(prepared, saved)), "conflict")
        path = folder / "receipt.json"
        if not path.exists():
            return unknown
        receipt = strict_load(self._read(path, 2097152))
        require(receipt["schema"] == "lore-s-provider-receipt/1" and receipt["effect_id"] == effect
                and receipt["prepared_sha256"] == digest(original_bytes), "integrity_mismatch")
        require(same(receipt["files"], self._wire_files(folder)), "integrity_mismatch")
        self._verify_wire(folder, intent, raw, receipt["wire"])
        return dict(status="RECEIVED" if receipt["wire"]["transport"]["complete"] else "UNKNOWN",
                    effect_id=effect, fresh=False, wire=receipt["wire"], receipt_ref=self._file_ref(path, 2097152))

    def complete(self, original_scope, provider_frame):
        prepared, intent, raw = self._prepared(original_scope, provider_frame)
        effect = prepared["effect_id"]
        folder = self._folder(effect)
        if folder.exists():
            return self._existing(effect, original_scope, prepared)
        self.root.mkdir(mode=0o700, exist_ok=True)
        fsync_directory(self.root.parent)
        try:
            folder.mkdir(mode=0o700)
        except FileExistsError:
            return self._existing(effect, original_scope, prepared)
        fsync_directory(self.root)
        save_json(folder / "prepared.json", prepared)
        client = WireClient(self.endpoint, intent["binding"], folder / "wire", timeout=self.timeout,
                            credential_provider=self.credential_provider)
        wire = client.complete(intent)
        self._verify_wire(folder, intent, raw, wire)
        receipt = dict(schema="lore-s-provider-receipt/1", effect_id=effect,
                       prepared_sha256=digest(self._read(folder / "prepared.json", 2097152)),
                       wire=wire, files=self._wire_files(folder))
        save_json(folder / "receipt.json", receipt)
        result = self._existing(effect, original_scope, prepared)
        result["fresh"] = True
        return result

    def query(self, effect_id, binding):
        require(effect_id == self._scope(binding), "conflict")
        return self._existing(effect_id, binding)
