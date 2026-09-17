"""Harness manifest: declaration-first resolution (landing §4.5 R1-R6).

- R1 declaration first, conventional default path as fallback
- R2 registration is strict: refs must exist, kinds must be well formed
- R3 unknown entries are preserved and never interpreted
- R5 `runtime` kinds must use the reserved `sys.` prefix; harness kinds must not
- R6 the manifest never embeds its own digest (recorded in work.json)
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

from .layout import RESERVED_KIND_PREFIXES, read_json, ref_digest

DEFAULT_ROLE_PATHS = {
    "conventions": "conventions",
    "projection": "projection",
    "organization": "organization",
    "rounds": "rounds",
    "admission": "admission",
    "logic": "logic",
    "views": "views",
    "presentation": "presentation",
    "tools": "tools",
    "budget": "budget",
}

PRODUCERS = ("runtime", "harness", "external")


class ManifestError(ValueError):
    pass


class Manifest:
    def __init__(self, base, data):
        self.base = Path(base)
        self.data = data
        self.roles = dict(data.get("roles") or {})
        facts = data.get("facts") or {}
        self.kinds = {k["kind"]: k for k in facts.get("kinds", [])}
        self.triggers = list(facts.get("triggers", []))
        self.views = list(data.get("views", []))
        self.extensions = list(data.get("extensions", []))
        self._modules = {}

    # -- resolution -------------------------------------------------------
    def entries(self, role: str) -> list:
        declared = self.roles.get(role) or []
        if declared:
            return declared
        default = DEFAULT_ROLE_PATHS.get(role, role)
        p = self.base / default
        if p.exists():
            return [{"id": "default", "ref": default}]
        return []

    def module(self, role: str, instance=None):
        entries = self.entries(role)
        if instance is not None:
            entries = [e for e in entries if e.get("id") == instance]
        if not entries:
            return None
        entry = entries[0]
        return self._load(entry["ref"])

    def _load(self, ref: str):
        if ref in self._modules:
            return self._modules[ref]
        p = self.base / ref
        if p.is_dir():
            p = p / "main.py"
        if not p.is_file():
            raise ManifestError(f"role ref is not loadable: {ref}")
        name = "lore_harness_" + hashlib.sha256(str(p).encode()).hexdigest()[:16]
        spec = importlib.util.spec_from_file_location(name, p)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        # The harness area is registered read-only: never let the interpreter
        # write __pycache__ into it (that would change the harness digest).
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
            sys.modules.pop(name, None)
        self._modules[ref] = module
        return module

    # -- validation -------------------------------------------------------
    def require_kind(self, kind: str, *, producer=None) -> dict:
        entry = self.kinds.get(kind)
        if entry is None:
            raise ManifestError(f"undeclared fact kind: {kind}")
        if producer and entry.get("producer") != producer:
            raise ManifestError(f"kind {kind} producer is {entry.get('producer')!r}, not {producer!r}")
        return entry


def digest(base) -> str:
    p = Path(base) / "harness"
    from .layout import tree_digest
    return tree_digest(p)


def load(base, *, verify: bool = True) -> Manifest:
    base = Path(base)
    harness_base = base / "harness"
    path = harness_base / "manifest.json"
    if not path.is_file():
        raise ManifestError("missing harness/manifest.json")
    data = read_json(path)
    if data.get("schema") != "lore-harness/v1":
        raise ManifestError(f"unsupported harness schema: {data.get('schema')!r}")

    for role, entries in (data.get("roles") or {}).items():
        if not isinstance(entries, list):
            raise ManifestError(f"roles.{role} must be a list")
        ids = set()
        for entry in entries:
            if set(entry) - {"id", "ref", "digest"} or "id" not in entry or "ref" not in entry:
                raise ManifestError(f"malformed role entry in {role}: {entry!r}")
            if entry["id"] in ids:
                raise ManifestError(f"duplicate role instance id in {role}: {entry['id']}")
            ids.add(entry["id"])
            if verify:
                actual = ref_digest(harness_base, entry["ref"])
                declared = entry.get("digest")
                if not declared:
                    raise ManifestError(
                        "role %s entry %s declares a ref without digest (R2: registration is strict)"
                        % (role, entry["id"]))
                if declared != actual:
                    raise ManifestError("role %s entry %s digest mismatch: declared %s, actual %s"
                                        % (role, entry["id"], declared, actual))

    for kind, entry in ((k["kind"], k) for k in (data.get("facts") or {}).get("kinds", [])):
        if set(entry) - {"kind", "contract", "producer", "requires_relation"} or not kind or "producer" not in entry:
            raise ManifestError(f"malformed kind entry: {entry!r}")
        if entry["producer"] not in PRODUCERS:
            raise ManifestError(f"unknown producer for {kind}: {entry['producer']!r}")
        reserved = kind.startswith(RESERVED_KIND_PREFIXES)
        if entry["producer"] == "runtime" and not reserved:
            raise ManifestError(f"runtime-produced kind must use reserved prefix: {kind}")
        if entry["producer"] != "runtime" and reserved:
            raise ManifestError(f"reserved prefix must not be claimed: {kind}")
        contract = entry.get("contract")
        if contract:
            if "ref" not in contract:
                raise ManifestError(f"kind {kind} contract without ref")
            if verify:
                actual = ref_digest(harness_base, contract["ref"])
                declared = contract.get("digest")
                if not declared:
                    raise ManifestError(
                        f"kind {kind} contract ref without digest (R2: registration is strict)")
                if declared != actual:
                    raise ManifestError("kind %s contract digest mismatch: declared %s, actual %s"
                                        % (kind, declared, actual))

    for trig in (data.get("facts") or {}).get("triggers", []):
        if "id" not in trig or "on" not in trig or not isinstance(trig["on"], list):
            raise ManifestError(f"malformed trigger: {trig!r}")
        for kind in trig["on"]:
            if kind not in {k["kind"] for k in (data.get("facts") or {}).get("kinds", [])}:
                raise ManifestError(f"trigger {trig['id']} references undeclared kind {kind}")
        when = trig.get("when")
        if when and verify:
            actual = ref_digest(harness_base, when["ref"])
            declared = when.get("digest")
            if not declared:
                raise ManifestError(
                    f"trigger {trig['id']} when-ref without digest (R2: registration is strict)")
            if declared != actual:
                raise ManifestError("trigger %s when digest mismatch: declared %s, actual %s"
                                    % (trig["id"], declared, actual))

    for view in data.get("views", []):
        if "id" not in view or "source" not in view:
            raise ManifestError(f"malformed view: {view!r}")
        resolver = view.get("resolver")
        if resolver and verify:
            actual = ref_digest(harness_base, resolver["ref"])
            declared = resolver.get("digest")
            if not declared:
                raise ManifestError(
                    "view %s resolver ref without digest (R2: registration is strict)" % view["id"])
            if declared != actual:
                raise ManifestError("view %s resolver digest mismatch: declared %s, actual %s"
                                    % (view["id"], declared, actual))

    return Manifest(harness_base, data)
