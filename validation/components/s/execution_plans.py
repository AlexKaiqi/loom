"""Trusted S test assembly over existing F, S snapshots and X configuration.
No Engine calls. The caller holds the F peer .fixture-lock while using this object.
"""
from pathlib import Path
import base64
import copy
import json
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/components/x_node_profile"))
from validation.components.x_node_profile.fixtures import dependencies, readonly_manifest, register, identity
from validation.components.x_node_profile.artifacts import canonical, file_fact, read_ref, save, sha_bytes, snapshot
from validation.components.s.f_peer import require
from lore_session.snapshots import SnapshotStore
from lore_session.tool_authority import require_tool_target

DESIGN = ROOT / "design/g3/x-node-profile"
SCOPE = ("namespace", "surface_id", "session_id", "session_generation")
MODEL = {"id": "faux-1", "name": "Faux Model", "api": "faux", "provider": "faux",
         "reasoning": False, "input": ["text", "image"],
         "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
         "contextWindow": 128000, "maxTokens": 16384}


class ExecutionPlans:
    def __init__(self, root, peer, namespace, *, deps_mount=None, state_root=None):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        require(self.root.is_relative_to(peer.case_root), "execution fixture outside F fixture scope")
        require(isinstance(namespace, str) and namespace, "trusted namespace required")
        self.peer = peer; self.namespace = namespace
        self.state_root = Path(state_root or self.root / "X-state").resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.authority_root = self.root / "authority"; self.authority_root.mkdir(exist_ok=True)
        self.snapshots = SnapshotStore(self.root / "S-originals", namespace, self.register)
        deps_path = self.root / "dependencies-view.json"
        if deps_mount is not None: self.deps = copy.deepcopy(deps_mount)
        elif deps_path.exists(): self.deps = json.loads(deps_path.read_bytes())
        else: self.deps = dependencies(self.root / "fixed-dependencies")
        if deps_path.exists(): require(json.loads(deps_path.read_bytes()) == self.deps, "fixed dependency view changed")
        else: save(deps_path, self.deps)
        profile_ref, raw = file_fact(DESIGN / "profile.json")
        self.profile = json.loads(raw)
        self.slot_ref = dict(owner="trusted-X-configuration", slot_id="s-fixture-slot", revision=1,
                             plan_sha256=sha_bytes(canonical(self.profile["slot_reservation"])), role="session")
        slot = dict(slot_id=self.slot_ref["slot_id"], revision=1, namespace=namespace,
                    plan_sha256=self.slot_ref["plan_sha256"], plan=self.profile["slot_reservation"],
                    allowed_principals=["trusted-S"], state_root=str(self.state_root))
        self.config = dict(schema="lore-x-trusted-node-test-config/v1", transport_principal="trusted-S",
            state_root=str(self.state_root), profiles=[dict(id=self.profile["id"], **profile_ref)],
            slots=[slot], grants=[], references=dict(snapshots=[], F_views=[], owner_receipts=[]), read_only_roots=[],
            allowed_harness_entries=[dict(path="/harness/lore_session/node/entry.mts",
                sha256=file_fact(ROOT / "lore_session/node/entry.mts")[0]["sha256"], argv_modes=["--config"])],
            dynamic_reference_authorities=[dict(root=str(self.authority_root), identity="trusted-S-F-validation-owner",
                namespace=namespace, allowed_kinds=["snapshot", "readonly-view", "owner-receipt", "grant", "storage-charge"],
                rule="immutable-full-ref-registration/v1")])
        self.config_path = self.root / "trusted-X-config.json"
        if self.config_path.exists():
            require(json.loads(self.config_path.read_bytes()) == self.config, "trusted X fixture configuration changed")
        else: save(self.config_path, self.config)
        self.config_sha = file_fact(self.config_path)[0]["sha256"]

    def register(self, kind, ref, scope):
        require(scope["namespace"] == self.namespace, "fixture registration crosses namespace")
        return register(self.authority_root, kind, ref, scope)

    def _refresh(self):
        index = json.loads(self.peer.index_path.read_bytes())
        require(index["authority"] == self.peer.authority and index["schema"] == "lore-s-f-fixture/v1",
                "trusted F fixture index changed authority")
        self.peer.index = index

    def _scope(self, original):
        scope = copy.deepcopy(original["session_scope"])
        require(set(scope) == set(SCOPE) and scope["namespace"] == self.namespace,
                "complete original Session scope required")
        require(all(isinstance(scope[k], str) and scope[k] for k in SCOPE[:-1]) and
                type(scope["session_generation"]) is int and scope["session_generation"] > 0,
                "invalid original Session identity")
        for key in ("input_ref", "harness_ref", "capability_ref"):
            ref = original[key]
            require(type(ref) is dict and set(ref) == {"id", "sha256"} and
                    all(isinstance(v, str) and v for v in ref.values()), "strict compact original reference required")
        require(isinstance(original["operation_id"], str) and original["operation_id"], "original operation ID missing")
        require("source_result_ref" in original and "session_snapshot_ref" in original, "complete original request required")
        return scope

    def _mount(self, view, role, directory, provenance=None):
        target = Path(view["materialized"]["path"])
        original = file_fact(view["bundle"]["manifest_path"])[0]
        content = dict(owner="F", version_ref=view["bundle"]["version_ref"], original_manifest=original,
                       materialized_root=dict(path=str(target), **identity(target)))
        if provenance is not None: content["fixture_source"] = provenance
        manifest = readonly_manifest(target, role, content, directory / (role + "-readonly.json"))
        mount = dict(role=role, source=content["materialized_root"], target="/" + role,
                     read_only=True, manifest_ref=manifest, content_ref=content)
        self.register("readonly-view", mount, dict(namespace=self.namespace, role=role))
        return mount

    def _snapshot(self, original, scope):
        envelope = original["session_snapshot_ref"]
        if isinstance(envelope, dict) and "fixture_fault_ref" in envelope:
            from validation.components.s.session_fault import resolve_fault_snapshot
            return resolve_fault_snapshot(self, envelope, scope)
        if envelope is None:
            bundle = self.snapshots.empty("empty-" + sha_bytes(canonical(scope)), scope)
            return bundle, bundle["snapshot_ref"]
        require(envelope.get("owner") == "S" and envelope["session_id"] == scope["session_id"],
                "original snapshot envelope differs")
        full = envelope["snapshot_ref"]
        record = json.loads(file_fact(full["record_path"], 2097152)[1])
        expected = dict(scope, original_execution=record["original_execution"])
        observed = snapshot(full, expected)
        fact = read_ref(envelope["original_archive"])[0]
        require(all(fact[k] == observed["archive_fact"][k] for k in ("path", "bytes", "sha256", "root")),
                "original envelope does not name S retained archive")
        owner = json.loads(read_ref(envelope["owner_record_ref"])[1])
        require(not owner.get("retention_only", False), "quarantine is not a healthy restore source")
        confirmed = self.snapshots.query(owner["confirmation_request_id"])
        require(confirmed == {k:envelope[k] for k in ("snapshot_ref", "owner_record_ref", "storage_charge_ref")},
                "restore does not name an original healthy confirmation")
        charge = json.loads(read_ref(envelope["storage_charge_ref"])[1])
        require(owner["scope"] == scope and owner["snapshot_ref"] == full and
                owner["storage_charge_ref"] == envelope["storage_charge_ref"] and
                owner["actual_archive_object"] == fact["root"] and
                charge["scope"] == scope and charge["snapshot_ref"] == full and charge["archive_fact"] == fact,
                "actual original owner or storage association differs")
        self.register("snapshot", full, expected)
        self.register("storage-charge", envelope["storage_charge_ref"], expected)
        return {k: envelope[k] for k in ("snapshot_ref", "owner_record_ref", "storage_charge_ref")}, full

    def _grant(self, request, scope, role):
        slot_ref = dict(self.slot_ref, role=role)
        record = dict(principal="trusted-S", operations=["execute", "query", "checkpoint", "stop"],
                      original_request=copy.deepcopy(request), request_digest=sha_bytes(canonical(request)),
                      scope=copy.deepcopy(scope), slot_ref=slot_ref, role=role)
        path = self.authority_root / ("grant-" + record["request_digest"] + ".json")
        if path.exists(): require(json.loads(path.read_bytes()) == record, "immutable grant changed")
        else: save(path, record)
        ref = dict(owner="trusted-X-configuration", id=record["request_digest"], record_path=str(path),
                   sha256=file_fact(path)[0]["sha256"])
        self.register("grant", ref, scope)
        return dict(grant_ref=ref, slot_ref=slot_ref)

    def _result(self, directory, request, authority, **extra):
        result = dict(request=request, authority=authority, trusted_config=str(self.config_path),
                      trusted_config_sha256=self.config_sha, state_root=str(self.state_root), **extra)
        save(directory / "plan.json", result)
        return result

    def session(self, original_request, *, execution_id=None):
        self._refresh()
        original = copy.deepcopy(original_request); scope = self._scope(original)
        descriptors = {name: self.peer.lookup(section, original[name]) for name, section in
                       [("input_ref", "inputs"), ("harness_ref", "harnesses"), ("capability_ref", "capabilities")]}
        input_item = descriptors["input_ref"]; body = input_item["document"]
        harness = descriptors["harness_ref"]["document"]
        capability = descriptors["capability_ref"]["document"]
        require(capability["targets"] == ["runtime", "workspace"], "original capability target set differs")
        bundle, full = self._snapshot(original, scope)
        directory = self.peer.area("session-plan")
        original_refs = {name: dict(source_ref=row["source_ref"], read_path=row["read_path"],
                            path=row["read_path"], bytes=row["bytes"], sha256=row["sha256"])
                         for name, row in body["original_refs"].items()}
        node_config = dict(schema="lore.s.node/1", pi_root="/opt/lore/research/repos/pi", work_root="/work",
            harness_entry="/harness/" + harness["harness_entry"], session_scope=scope,
            harness_ref=original["harness_ref"], capability_ref=original["capability_ref"], model=copy.deepcopy(MODEL),
            input=dict(ref=original["input_ref"], paths=body["paths"], limits=capability["limits"], original_refs=original_refs))
        # Read projection faults select a distinct real F capture; protected original refs remain unchanged.
        selected = input_item.get("read_copy_override", body["input"])
        source = self.peer.area("configured-input-source")
        shutil.copytree(selected["materialized"]["path"], source, dirs_exist_ok=True, symlinks=True)
        require(not (source / "node-config.json").exists(), "generated config collides with original input")
        save(source / "node-config.json", node_config)
        input_view = self.peer.capture(source, "input")
        provenance = dict(original_input_ref=original["input_ref"], descriptor_F_ref=input_item["full_ref"],
                          selected_F_version=selected["bundle"]["version_ref"], generated_config=file_fact(source / "node-config.json")[0])
        mounts = [copy.deepcopy(self.deps), self._mount(harness["code"], "harness", directory),
                  self._mount(input_view, "input", directory, provenance), self._mount(body["workspace"], "workspace", directory)]
        self.register("readonly-view", mounts[0], dict(namespace=self.namespace, role="dependencies"))
        request = json.loads((DESIGN / "request-template.json").read_bytes())
        request.update(execution_id=execution_id or "s-" + uuid.uuid4().hex, caller="trusted-S",
            invocation_id=original["operation_id"], step_id=original["operation_id"], source_result=original["source_result_ref"],
            harness_version=harness["code"]["bundle"]["version_ref"], session_binding=scope,
            object_generation=scope["session_generation"], profile_sha256=file_fact(DESIGN / "profile.json")[0]["sha256"],
            base_version=sha_bytes(canonical(full)), snapshot_ref=full, readonly_mounts=mounts,
            command_argv=[*self.profile["argv_prefix"], "/harness/" + harness["entry"], "--config", "/input/node-config.json"])
        authority = self._grant(request, scope, "session")
        return self._result(directory, request, authority, original_request=original, node_config=node_config,
                            input_view=input_view, snapshot_bundle=bundle, fixture_source=provenance)

    def tool(self, session_request, target, script, *, execution_id, source_result_ref):
        self._refresh()
        scope = self._scope(session_request)
        require_tool_target(target, script)
        descriptor = self.peer.lookup("inputs", session_request["input_ref"])
        body = descriptor["document"]
        view = body["source_F"]["surface"] if target == "runtime" else body["workspace"]
        path = Path(view["materialized"]["path"])
        manifest = json.loads(Path(view["bundle"]["manifest_path"]).read_bytes())
        entries = manifest["tree"]["entries"]
        require(len(entries) <= 1024, "complete original tool input exceeds admitted F entries")
        files = [dict(path=name, size=row["size"], sha256=row["sha256"]) for name, row in entries.items() if row["kind"] == "file"]
        domain = "runtime" if target == "runtime" else "task"
        target_id = view["bundle"]["version_ref"]["resource_id"]
        version = sha_bytes(canonical(view["bundle"]["version_ref"]))
        budgets = dict(memory_bytes=134217728, pids=32, cpu=.25, volume_bytes=6291456,
            inodes=128 if len(entries) <= 128 else 1024, tmp_bytes=1048576, shm_bytes=1048576,
            stdout_bytes=65536, stderr_bytes=65536, combined_output_bytes=98304,
            archive_bytes=8388608, expanded_bytes=12582912, deadline_seconds=20)
        request = dict(schema_version=1, execution_id=execution_id, caller="trusted-S",
            invocation_id=session_request["operation_id"], step_id=session_request["operation_id"],
            source_result=copy.deepcopy(source_result_ref), harness_version=sha_bytes(canonical(session_request["harness_ref"])),
            target_selector=dict(target_id=target_id, location=str(path)), target_id=target_id,
            binding_generation=1, domain=domain, base_version=version,
            input_manifest=dict(files=files), input_root=str(path), cwd=".", environment="fixed-python-linux-v1",
            endpoints=[], network="none", budgets=budgets, stdin_base64="", io_mode="finite",
            interpreter_argv=["/bin/sh", "-c"], script_base64=base64.b64encode(script.encode("utf8")).decode())
        authority = dict(namespace=self.namespace, caller="trusted-S", target_id=target_id, domain=domain,
            target_path=str(path), target_identity=identity(path), binding_generation=1, base_version=version,
            write_token="trusted-fixture-" + execution_id, state_dir=str(self.state_root), allowed_parent=None,
            grants=["execute", "query", "checkpoint", "stop"], metadata_profile="ordinary-posix-no-xattr-acl")
        authority.update(self._grant(request, scope, "tool"))
        return self._result(self.peer.area("tool-plan"), request, authority, target=target, F=view,
                            original_input_ref=session_request["input_ref"], original_full_manifest=file_fact(view["bundle"]["manifest_path"])[0])
