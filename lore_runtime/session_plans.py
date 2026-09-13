"""Trusted, synchronous Session request assembly from original R/E/F/S facts."""
import copy
from pathlib import Path, PurePosixPath
from lore_control.values import ControlError
from lore_session.execution import session_reference
from lore_events.input_files import validate as validate_input
from lore_execution.errors import require
from lore_execution.journal import canonical, digest
from lore_execution.node_profile import NodeProfile, guarded
from lore_execution.ordinary_sources import SCOPE, EXEC, document, file_object, json_value, snapshot
from .session_plan_files import InputFiles, compact, json_file, history_catalog


class SessionPlans:
    @guarded
    def __init__(self, control, files, snapshots, host, resolve_reference, register):
        require(callable(resolve_reference) and callable(register), "UNAUTHORIZED", "trusted owners required")
        self.control, self.files, self.snapshots = control, files, snapshots
        self.host = copy.deepcopy(host)
        self.resolve_reference, self.register = resolve_reference, register
        self.projections = InputFiles(files, self.host, register)
        self._read_context = None

    def _sources(self, principal, invocation_id):
        h = self.host
        require(principal == h["principal"], "UNAUTHORIZED", "fixed Runtime principal differs")
        row = self.control.query(principal, invocation_id)
        require(row is not None and row["kind"] == "invocation" and row["namespace"] == h["namespace"],
                "UNAUTHORIZED", "original accepted invocation required")
        payload = row["payload"]
        bound = self.control.query_input(principal, invocation_id)
        require(bound is not None and bound["invocation_id"] == invocation_id
                and bound["binding"] == payload["input_binding"],
                "UNAUTHORIZED", "original E input not bound")
        selector = bound["binding"]
        require(selector["namespace"] == h["namespace"], "UNAUTHORIZED", "original selector namespace differs")
        e_files, input_manifest = validate_input(bound["input_ref"], selector, h["event_input_root"])
        registrations, views = {}, {}
        expected = dict(invocation=row, selector=selector, input_range=input_manifest["range"])
        targets = selector["execution_targets"]
        require(type(targets) is list and len(targets) == 2, "UNAUTHORIZED", "both original execution domains required")
        for target in targets:
            reg = self.control.resolve(principal, h["namespace"], target["resource_id"], "read")
            require(reg["kind"] in ("surface", "workspace") and reg["kind"] not in views,
                    "UNAUTHORIZED", "ambiguous original execution domain")
            version = target["version_ref"]
            require(version["resource_id"] == reg["id"] and version["domain"] == reg["kind"],
                    "UNAUTHORIZED", "original F version resource differs")
            view = self.resolve_reference(version, "F-view", dict(expected, registration=reg))
            self.projections.checked_view(view, version, reg)
            registrations[reg["kind"]], views[reg["kind"]] = reg, copy.deepcopy(view)
        surface = registrations["surface"]
        require(surface["id"] == payload["resource_id"] and surface["revision"] == payload["resource_revision"]
                and surface["harness_ref"] == payload["harness_ref"]
                and selector["surface_ref"] == views["surface"]["bundle"]["version_ref"],
                "UNAUTHORIZED", "accepted Surface revision/Harness/version changed")
        expected["registrations"] = registrations
        descriptors = {}
        for purpose in ("harness", "capability"):
            ref = payload[purpose + "_ref"]
            raw = self.resolve_reference(ref, purpose, expected)
            require(raw == self.files.read_reference(ref, h["authorization"]),
                    "INVALID_REQUEST", "original F descriptor content differs")
            descriptors[purpose] = json_value(raw)
        require(descriptors["capability"]["targets"] == ["runtime", "workspace"],
                "UNAUTHORIZED", "original capability domains differ")
        self.projections.checked_view(descriptors["harness"]["code"])
        session = self.resolve_reference(payload["session_ref"], "session", expected)
        scope = session["scope"]
        require(set(scope) == set(SCOPE) and scope["namespace"] == h["namespace"]
                and scope["surface_id"] == surface["id"]
                and all(type(scope[k]) is str and scope[k] for k in SCOPE[:-1])
                and type(scope["session_generation"]) is int and scope["session_generation"] > 0,
                "UNAUTHORIZED", "original owner Session scope differs")
        for key in SCOPE:
            if key in payload["session_ref"]:
                require(payload["session_ref"][key] == scope[key], "UNAUTHORIZED", "accepted Session association differs")
        return row, bound, e_files, views, descriptors, session, expected

    def _snapshot(self, session):
        scope = session["scope"]
        id = session["confirmation_request_id"]
        bundle = self.snapshots.empty("empty-" + digest(canonical(scope)), scope) if id is None else self.snapshots.query(id)
        owner = document(bundle["owner_record_ref"])
        require(owner["scope"] == scope and not owner.get("retention_only", False),
                "UNAUTHORIZED", "original owner is not this healthy Session")
        full = bundle["snapshot_ref"]
        record = document(dict(path=full["record_path"], sha256=full["record_sha256"]))
        expected = dict(scope, original_execution=record["original_execution"])
        snapshot(full, expected)
        self.register("snapshot", full, expected)
        self.register("storage-charge", bundle["storage_charge_ref"], expected)
        return bundle

    def _originals(self, capability, expected):
        result = {}
        for name, row in capability.get("original_refs", {}).items():
            require(type(name) is str and name and "/" not in name and name not in (".", "..")
                    and row["read_path"] == "/input/originals/" + name,
                    "UNAUTHORIZED", "authorized original input mapping differs")
            data = self.resolve_reference(row["source_ref"], "original-file", expected)
            require(data == self.files.read_reference(row["source_ref"], self.host["authorization"]),
                    "INVALID_REQUEST", "original F bytes differ")
            result[name] = dict(source_ref=row["source_ref"], read_path=row["read_path"],
                                path=row["read_path"], bytes=len(data), sha256=digest(data), raw=data)
        return result

    def _facility(self, action, node, expected):
        parent = expected["invocation"]
        id = "s-exec-" + digest(canonical([parent["id"], action]))
        row = self.control.query(self.host["principal"], id)
        wanted = dict(parent_id=parent["id"], action=action, execution_id=id, node_request=node)
        require(row["id"] == id and row["kind"] == "execution" and row["namespace"] == parent["namespace"]
                and row["principal"] == self.host["principal"] and row["payload"] == wanted
                and row["phase"] == "confirmed", "UNAUTHORIZED", "original Session facility is not confirmed")
        receipt = row["receipt_ref"]
        require(receipt["outcome"] == "positive", "UNAUTHORIZED", "Session facility has no healthy positive receipt")
        # Existing R operation revalidates the already immutable receipt without changing it.
        require(self.control.confirm_delivery(self.host["principal"], id, receipt) == row,
                "UNAUTHORIZED", "original R facility receipt changed")
        selected = self.resolve_reference(receipt, "session-source", dict(expected, facility=row, action=action))
        confirmation_id = "s-" + digest(canonical([id, "s-service-final"]))
        require(selected == dict(facility_id=id, confirmation_request_id=confirmation_id),
                "UNAUTHORIZED", "resolver selected another facility confirmation")
        facility = receipt["facility_ref"]
        require(facility["owner"] == "X" and facility["kind"] == "session_execution"
                and facility["execution_id"] == id and facility["confirmation_request_id"] == confirmation_id
                and facility["node_request_digest"] == digest(canonical(node)),
                "UNAUTHORIZED", "facility original Node association differs")
        bundle = self.snapshots.query(confirmation_id)
        require(bundle == facility["session_confirmation"], "UNAUTHORIZED", "receipt and healthy S original differ")
        owner = document(bundle["owner_record_ref"])
        scope = {k: expected["session_scope"][k] for k in SCOPE}
        require(owner["scope"] == scope and not owner.get("retention_only", False),
                "UNAUTHORIZED", "facility belongs to another or quarantined Session")
        cp = owner["source"]["original_checkpoint_full_ref"]
        require(cp is not None and cp["source_binding"]["execution_id"] == id,
                "UNAUTHORIZED", "facility original checkpoint execution differs")
        for response in (facility["original_execution_response"], facility["original_stopped_response"]):
            require(all(response["binding"].get(k) == cp["source_binding"].get(k) for k in EXEC),
                    "UNAUTHORIZED", "original stop/release and snapshot tuple differ")
        full = bundle["snapshot_ref"]
        original = document(dict(path=full["record_path"], sha256=full["record_sha256"]))
        source_scope = dict(scope, original_execution=original["original_execution"])
        require(all(source_scope["original_execution"].get(k) == cp["source_binding"].get(k) for k in EXEC),
                "UNAUTHORIZED", "S retained execution differs from original checkpoint")
        snapshot(full, source_scope)
        self.register("snapshot", full, source_scope)
        self.register("storage-charge", bundle["storage_charge_ref"], source_scope)
        return bundle

    def _selected(self, action, initial, node, expected):
        if action == "accept": return initial
        accepted = self._facility("accept", node, expected)
        if action == "drive": return accepted
        drive_id = "s-exec-" + digest(canonical([expected["invocation"]["id"], "drive"]))
        try: drive = self.control.query(self.host["principal"], drive_id)
        except ControlError as exc:
            if exc.code != "not_found": raise
            return accepted
        require(drive["phase"] == "confirmed", "UNAUTHORIZED", "issued/unknown drive cannot fall back to acceptance")
        return self._facility("drive", dict(node, action="drive", session_ref=session_reference(accepted)), expected)

    @guarded
    def prepare(self, principal, invocation_id, *, execution_id):
        return self._assemble(principal, invocation_id, execution_id=execution_id, action="accept")

    def _assemble(self, principal, invocation_id, *, execution_id, action):
        require(type(execution_id) is str and 0 < len(execution_id) <= 256,
                "INVALID_REQUEST", "trusted stable execution ID required")
        row, bound, e_files, views, descriptors, session, expected = self._sources(principal, invocation_id)
        h, payload, scope = self.host, row["payload"], session["scope"]
        # These are original fixed host files; profile checks never choose a new budget.
        profile = document(h["profile_ref"])
        request = document(h["request_template_ref"])
        validator = NodeProfile(h["trusted_config_ref"]["path"], h["trusted_config_ref"]["sha256"], h["state_root"])
        require(h["model"].keys() <= {"id", "name", "api", "provider", "reasoning", "input", "cost", "contextWindow", "maxTokens"},
                "UNAUTHORIZED", "model configuration cannot carry credentials or endpoints")
        directory = self.projections.root / digest(canonical([invocation_id, execution_id]))
        directory.mkdir(exist_ok=True)
        bundle = self._snapshot(session)
        originals = self._originals(descriptors["capability"], expected)
        source_result = payload["source_result_ref"]
        feedback = self.resolve_reference(source_result, "source-result", expected) if source_result is not None else b""
        require(type(feedback) is bytes, "INVALID_REQUEST", "source result must resolve original bytes")
        provenance = dict(invocation_id=invocation_id, E_input_ref=bound["input_ref"],
                          selector=bound["binding"], F_sources={k:v["bundle"]["version_ref"] for k,v in views.items()},
                          harness_ref=payload["harness_ref"], capability_ref=payload["capability_ref"],
                          source_result_ref=source_result)
        descriptor_directory = self.projections.root / ("invocation-" + digest(invocation_id.encode()))
        descriptor_directory.mkdir(exist_ok=True)
        input_full = self.projections.descriptor(descriptor_directory, invocation_id, provenance)
        node = dict(protocol="lore.s/1", action="accept", session_ref=session_reference(bundle),
                    operation_id=invocation_id, harness_ref=compact(payload["harness_ref"]),
                    input_ref=compact(input_full), source_result_ref=source_result,
                    capability_ref=compact(payload["capability_ref"]))
        bundle = self._selected(action, bundle, node, dict(expected, session_scope=scope))
        node.update(action=action, session_ref=session_reference(bundle))
        harness, capability = descriptors["harness"], descriptors["capability"]
        config = dict(schema="lore.s.node/1", pi_root="/opt/lore/research/repos/pi", work_root="/work",
                      harness_entry="/harness/" + harness["harness_entry"], session_scope=scope,
                      harness_ref=node["harness_ref"], capability_ref=node["capability_ref"], model=copy.deepcopy(h["model"]),
                      input=dict(ref=node["input_ref"], paths=dict(surface="/input/surface", events="/input/events.jsonl",
                           feedback="/input/feedback.txt", runtime="/input/surface", workspace="/workspace"),
                           history_views=history_catalog(views["workspace"]["bundle"]["version_ref"]),
                           limits=capability["limits"], original_refs={k:{a:b for a,b in v.items() if a!="raw"} for k,v in originals.items()}))
        drive_id = "s-exec-" + digest(canonical([invocation_id, "drive"]))
        config["runtime_context"] = dict(
            invocation={k: row[k] for k in ("id", "principal", "namespace", "kind", "payload")},
            node_binding=dict(session_id=scope["session_id"], session_scope=scope,
                              **{k:node[k] for k in ("operation_id", "harness_ref", "input_ref", "source_result_ref", "capability_ref")}),
            input=dict(selector=bound["binding"], range=expected["input_range"]),
            execution_id=drive_id,
            continuation_session_ref=dict(owner="S", kind="confirmation",
                confirmation_request_id="s-" + digest(canonical([drive_id, "s-service-final"])), session_scope=scope))
        input_view = self.projections.input(directory, invocation_id, views["surface"], e_files,
                                           originals, feedback, config, dict(provenance, input_descriptor=input_full, node_config_sha256=digest(canonical(config)+b"\n")), history_view=views["workspace"])
        mounts = [copy.deepcopy(h["deps_mount"]), self.projections.mount(harness["code"], "harness", directory),
                  self.projections.mount(input_view, "input", directory), self.projections.mount(views["workspace"], "workspace", directory)]
        self.register("readonly-view", mounts[0], dict(namespace=h["namespace"], role="dependencies"))
        request.update(execution_id=execution_id, caller="trusted-S", invocation_id=invocation_id,
                       step_id=invocation_id, source_result=source_result, harness_version=harness["code"]["bundle"]["version_ref"],
                       session_binding=scope, object_generation=scope["session_generation"], profile_sha256=h["profile_ref"]["sha256"],
                       base_version=digest(canonical(bundle["snapshot_ref"])), snapshot_ref=bundle["snapshot_ref"],
                       readonly_mounts=mounts, command_argv=[*profile["argv_prefix"], "/harness/"+harness["entry"], "--config", "/input/node-config.json"])
        grant = dict(principal="trusted-S", operations=["execute", "query", "checkpoint", "stop"],
                     original_request=request, request_digest=digest(canonical(request)), scope=scope,
                     slot_ref=h["slot_ref"], role="session")
        fact = json_file(Path(h["authority_root"]) / ("grant-" + grant["request_digest"] + ".json"), grant)
        ref = dict(owner="trusted-X-configuration", id=grant["request_digest"], record_path=fact["path"], sha256=fact["sha256"])
        self.register("grant", ref, scope)
        authority = dict(grant_ref=ref, slot_ref=h["slot_ref"])
        validator.prepare(request, authority); validator.role_slot(request, authority)
        return copy.deepcopy(dict(node_request=node, request=request, authority=authority, node_config=config,
                 original_request=row, input_view=input_view, snapshot_bundle=bundle))

    @guarded
    def session(self, node_request, *, execution_id):
        node_request = copy.deepcopy(node_request)
        self._read_context = None
        allowed = {"protocol", "action", "session_ref", "operation_id", "harness_ref", "input_ref", "source_result_ref", "capability_ref"}
        action = node_request["action"]
        require(action in ("accept", "query", "drive", "export_read") and
                set(node_request) == (allowed | ({"read_ref"} if action == "export_read" else set())),
                "UNAUTHORIZED", "only original Session operation fields allowed")
        plan = self._assemble(self.host["principal"], node_request["operation_id"], execution_id=execution_id, action=action)
        require({k:v for k,v in node_request.items() if k not in ("action", "read_ref")} ==
                {k:v for k,v in plan["node_request"].items() if k != "action"},
                "UNAUTHORIZED", "Node binding differs from original R invocation")
        if action == "export_read":
            require(any(v["source_ref"] == node_request["read_ref"] for v in plan["node_config"]["input"]["original_refs"].values()),
                    "UNAUTHORIZED", "read reference outside original capability")
        self._read_context = (node_request["operation_id"], execution_id, action)
        return plan

    @guarded
    def resolve_read(self, original_full_F_ref, node_descriptor):
        require(self._read_context is not None, "UNAUTHORIZED", "original Session context required")
        id, execution_id, action = self._read_context
        plan = self._assemble(self.host["principal"], id, execution_id=execution_id, action=action)
        matches = [v for v in plan["node_config"]["input"]["original_refs"].values() if v["source_ref"] == original_full_F_ref]
        require(len(matches) == 1, "UNAUTHORIZED", "read outside original F capability")
        row = matches[0]
        require(type(node_descriptor) is dict and all(node_descriptor.get(k) == row[k] for k in ("path", "bytes", "sha256")),
                "UNAUTHORIZED", "Node read descriptor differs from original mapping")
        relative = PurePosixPath(row["path"]).relative_to("/input")
        root = Path(plan["input_view"]["materialized"]["path"])
        path = root / relative
        require(path.resolve().is_relative_to(root), "UNAUTHORIZED", "read mapping escapes F input")
        fact, data = file_object(path)
        require(data == self.files.read_reference(original_full_F_ref, self.host["authorization"])
                and fact["bytes"] == row["bytes"] and fact["sha256"] == row["sha256"],
                "INVALID_REQUEST", "original read projection content differs")
        return {k:fact[k] for k in ("path", "bytes", "sha256")}
