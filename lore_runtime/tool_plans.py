"""Ordinary Shell plans derived from original R/E/F/S references; no dispatch."""
import base64
import copy
from pathlib import Path
from lore_control.values import decode
from lore_execution.errors import require
from lore_execution.journal import canonical, digest
from lore_execution.node_profile import NodeProfile, guarded
from lore_execution.requests import validate
from lore_session.tool_authority import require_tool_target
from lore_session.transport import original, pending
from .session_plan_files import json_file


class ToolPlans:
    def __init__(self, session_plans, snapshots):
        self.sessions, self.snapshots = session_plans, snapshots
        self.host = session_plans.host
        self.control, self.files = session_plans.control, session_plans.files

    @guarded
    def prepare(self, binding, frame, original_session_snapshot_ref):
        binding, frame, envelope = copy.deepcopy((binding, frame, original_session_snapshot_ref))
        parent_id = binding["operation_id"]
        eid = "s-exec-" + digest(canonical([parent_id, "accept"]))
        original_plan = self.sessions.prepare(self.host["principal"], parent_id, execution_id=eid)
        expected = original_plan["node_config"]["runtime_context"]["node_binding"]
        require(binding == expected, "UNAUTHORIZED", "tool binding differs from original R/E invocation")
        observed = original(self.snapshots, dict(original_session_snapshot_ref=envelope), binding)
        pending(observed, binding, frame)
        require(frame["type"] == "tool.request" and set(frame["request"]) == {"target", "script"},
                "UNAUTHORIZED", "ordinary delegated Shell fields required")
        target, script = frame["request"]["target"], frame["request"]["script"]
        require_tool_target(target, script)
        domain = "surface" if target == "runtime" else "workspace"
        row = original_plan["original_request"]
        selector = row["payload"]["input_binding"]
        choices = [item for item in selector["execution_targets"] if item["version_ref"]["domain"] == domain]
        require(len(choices) == 1, "UNAUTHORIZED", "original target selection is ambiguous")
        version = choices[0]["version_ref"]
        resource = self.control.resolve(self.host["principal"], row["namespace"], choices[0]["resource_id"], "write")
        view = self.sessions.resolve_reference(version, "F-view", dict(invocation=row, selector=selector, registration=resource))
        path, tree, _ = self.sessions.projections.checked_view(view, version, resource)
        entries = tree["entries"]
        require(len(entries) <= 1024 and not any(v["xattrs"] for v in entries.values()),
                "INVALID_REQUEST", "complete ordinary tool input exceeds admitted metadata/inodes")
        files = [dict(path=n, size=v["size"], sha256=v["sha256"]) for n,v in entries.items() if v["kind"] == "file"]
        budgets = dict(memory_bytes=134217728, pids=32, cpu=.25, volume_bytes=6291456,
                       inodes=128 if len(entries) <= 128 else 1024, tmp_bytes=1048576, shm_bytes=1048576,
                       stdout_bytes=65536, stderr_bytes=65536, combined_output_bytes=98304,
                       archive_bytes=8388608, expanded_bytes=12582912, deadline_seconds=20)
        request = dict(schema_version=1, execution_id=frame["effect_id"], caller="trusted-S",
                       invocation_id=parent_id, step_id=frame["invocation_id"], source_result=binding["source_result_ref"],
                       harness_version=digest(canonical(binding["harness_ref"])),
                       target_selector=dict(target_id=resource["id"], location=str(path)), target_id=resource["id"],
                       binding_generation=resource["revision"], domain="runtime" if domain=="surface" else "task",
                       base_version=digest(canonical(version)), input_manifest=dict(files=files), input_root=str(path),
                       cwd=".", environment="fixed-python-linux-v1", endpoints=[], network="none", budgets=budgets,
                       stdin_base64="", io_mode="finite", interpreter_argv=["/bin/sh","-c"],
                       script_base64=base64.b64encode(script.encode("utf8")).decode())
        if target == "runtime":
            inputs = [m for m in original_plan["request"]["readonly_mounts"] if m["role"] == "input"]
            require(len(inputs) == 1, "UNAUTHORIZED", "original accepted runtime input is ambiguous")
            request["readonly_mounts"] = copy.deepcopy(inputs)
        slot = dict(self.host["slot_ref"], role="tool")
        grant = dict(principal="trusted-S", operations=["execute","query","checkpoint","stop"],
                     original_request=request, request_digest=digest(canonical(request)),
                     scope=binding["session_scope"], slot_ref=slot, role="tool")
        grant_path = Path(self.host["authority_root"]) / ("grant-"+grant["request_digest"]+".json")
        grant_ref = dict(owner="trusted-X-configuration", id=grant["request_digest"], record_path=str(grant_path),
                         sha256=digest(canonical(grant)+b"\n"))
        holder = dict(resource_id=resource["id"], execution_id=frame["effect_id"], base_ref=version)
        authority = dict(namespace=row["namespace"], caller="trusted-S", target_id=resource["id"],
                         domain=request["domain"], target_path=str(path), target_identity=view["materialized"]["root"],
                         binding_generation=resource["revision"], base_version=request["base_version"],
                         write_token="R-holder-"+digest(canonical(holder)), state_dir=self.host["state_root"],
                         allowed_parent=None, grants=["execute","query","checkpoint","stop"],
                         metadata_profile="ordinary-posix-no-xattr-acl", grant_ref=grant_ref, slot_ref=slot)
        validate(request, authority, self.host["state_root"])
        directory = Path(self.host["plan_root"]) / ("tool-"+digest(frame["effect_id"].encode()))
        directory.mkdir(exist_ok=True)
        return copy.deepcopy(dict(request=request, authority=authority, grant=grant, resource=resource,
            base_ref=version, F=view, directory=str(directory), binding=binding, frame=frame,
            original_session_snapshot_ref=envelope,
            original_invocation={k:row[k] for k in ("id","principal","namespace","kind","payload")}))

    @guarded
    def grant(self, plan):
        """Register this exact ordinary execution only after its real R holder exists."""
        eid=plan["request"]["execution_id"]
        row=self.control.query(self.host["principal"],eid)
        require(row["kind"]=="execution" and row["payload"]["plan"]==plan,
                "UNAUTHORIZED","original accepted tool plan differs")
        with self.control._lock:
            holder=self.control.db.execute("SELECT * FROM holders WHERE resource_id=?",(plan["resource"]["id"],)).fetchone()
        require(holder is not None and holder["execution_id"]==eid and decode(holder["base_ref_json"])==plan["base_ref"],
                "UNAUTHORIZED","tool lacks original R writer responsibility")
        ref=plan["authority"]["grant_ref"]
        fact=json_file(Path(ref["record_path"]),plan["grant"])
        require(fact["sha256"]==ref["sha256"],"UNAUTHORIZED","original grant bytes differ")
        self.sessions.register("grant",ref,plan["binding"]["session_scope"])
        validator=NodeProfile(self.host["trusted_config_ref"]["path"],self.host["trusted_config_ref"]["sha256"],self.host["state_root"])
        return validator.role_slot(plan["request"],plan["authority"])
