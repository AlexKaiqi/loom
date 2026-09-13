"""Finite boundary protocol model; no production isolation guarantees.

State carries fixture facts separately from controller records and observations.
The independent runner supplies only initial state and semantic operations.
"""
from copy import deepcopy
from .boundary_execution import ExecutionOperations
from .boundary_writers import WriterOperations
from .boundary_versions import VersionOperations
from .boundary_records import RecordOperations


class BoundaryModel(ExecutionOperations, WriterOperations,
                    VersionOperations, RecordOperations):
    VARIANTS = {
        "promote_runtime_worker", "caller_profile_override",
        "host_fallback_on_invalid", "ambiguous_first_match", "path_prefix_only",
        "check_then_reopen_alias", "route_from_cd", "inherit_parent_handles",
        "owner_record_as_revocation", "surface_lock_is_workspace_lock",
        "parent_exit_as_tree_stop", "ignore_external_edit",
        "read_latest_during_render", "tracked_only_snapshot",
        "rollback_erases_history", "event_name_is_authority", "view_is_authority",
        "stale_registration_cache", "latest_harness_each_phase",
        "trim_deletes_raw", "trim_drops_unknown", "auto_execute_blocks",
    }
    # Only these environmental/configuration facts can be injected. Witness
    # operations control effective writers and process exit independently.
    EXTERNAL_ROOTS = {
        "objects", "aliases", "grants", "current_input", "artifact_paths",
        "directory_identity", "bindings", "harness_versions", "versions",
        "locations", "read_grants", "submission_grants", "available_inputs",
    }
    OPERATIONS = {
        "execute", "external_change", "prepare_execution", "execute_prepared",
        "start_process", "start_child", "use_handle", "change_owner_record",
        "request_takeover", "attempt_write", "observe_revocation",
        "request_cancel", "observe_process_exit", "read_object",
        "conditional_edit", "capture_object_version", "begin_render",
        "render_read", "finish_render", "render_all", "capture_snapshot",
        "restore_snapshot", "discard_volatile", "restore_domains",
        "replay_history", "submit_message", "read_untrusted_content",
        "read_input_view", "mutate_private_view", "notify_existing_input",
        "regenerate_input_view", "update_registration", "begin_step",
        "step_phase", "trim_projection", "read_source", "retry_operation",
        "query_effect", "project_context",
    }

    def __init__(self, initial_state, variant=None):
        if variant is not None and variant not in self.VARIANTS:
            raise ValueError(f"Unknown boundary mutation: {variant}")
        self.variant = variant
        self._state = deepcopy(initial_state)
        required = {
            "objects", "targets", "grants", "locations", "directory_identity",
            "aliases", "observations", "counters", "records", "control",
            "effective_writers", "processes", "versions", "snapshots",
            "restored", "events", "registry", "bindings", "harness_versions",
            "steps", "external_effects", "renders",
        }
        missing = required - self._state.keys()
        if missing:
            raise ValueError(f"Incomplete initial state: {sorted(missing)}")
        self._state["counters"].setdefault("model_launches", 0)
        self._state["records"].setdefault("rejected_edits", [])
        self._prepared = {}

    def snapshot(self):
        return deepcopy(self._state)

    def apply(self, op, args):
        if op not in self.OPERATIONS:
            raise ValueError(f"Unknown boundary operation: {op}")
        if not isinstance(args, dict):
            raise TypeError("Operation args must be a mapping")
        getattr(self, "_op_" + op)(deepcopy(args))

    def _observe(self, args, **values):
        if "observation" in args:
            self._state["observations"][args["observation"]] = deepcopy(values)

    def _write_object(self, reference, value):
        obj = self._state["objects"][reference]
        obj["value"] = deepcopy(value)
        obj["revision"] += 1

    def _op_external_change(self, args):
        path = args["path"]
        if not path or path[0] not in self.EXTERNAL_ROOTS:
            raise ValueError("External injection must address a fixture/config fact")
        target = self._state
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = deepcopy(args["value"])
        self._observe(args, status="changed", path=path, value=target[path[-1]])

    def _op_discard_volatile(self, args):
        scope = args["scope"]
        if scope not in {
            "current-environment", "input-connection", "step-worker",
            "projection-view",
        }:
            raise ValueError(f"Unknown volatile scope: {scope}")
        if scope == "input-connection":
            self._state["input_views"] = {}
        elif scope == "projection-view":
            self._state["records"]["projection"] = {}
        elif scope == "current-environment":
            self._prepared.clear()
        # Losing a worker/connection is not evidence that its capabilities were
        # revoked. Version references, Steps and unresolved duties survive.
        self._observe(args, status="discarded", scope=scope)
