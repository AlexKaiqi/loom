"""Trusted Node execution configuration and complete original source associations."""

from pathlib import Path
import base64, copy, math, os
from .errors import ExecutionError, require
from .journal import canonical, digest
from .ordinary_sources import (
    SCOPE,
    EXEC,
    document,
    file_object,
    reference,
    readonly,
    snapshot,
)

OPERATIONS = {
    "execute": "execute",
    "query": "query",
    "await_exit": "query",
    "channel_read": "query",
    "channel_write": "execute",
    "close_stdin": "execute",
    "checkpoint": "checkpoint",
    "resume": "execute",
    "seal": "stop",
    "release": "stop",
    "request_stop": "stop",
    "stop": "stop",
    "query_call": "query",
    "release_checkpoint": "checkpoint",
    "query_checkpoint": "query",
}
FIELDS = set(
    "schema_version execution_id caller invocation_id step_id source_result harness_version domain session_binding object_generation environment profile_sha256 base_version snapshot_ref readonly_mounts command_argv cwd environment_values stdin_base64 io_mode budgets".split()
)
LIMITS = {
    "memory_bytes": 536870912,
    "memory_swap_bytes": 536870912,
    "pids": 64,
    "cpu": 0.5,
    "work_bytes": 16777216,
    "work_inodes": 512,
    "tmp_bytes": 33554432,
    "tmp_inodes": 2048,
    "shm_bytes": 1048576,
    "shm_inodes": 64,
    "stdout_bytes": 1048576,
    "stderr_bytes": 1048576,
    "combined_output_bytes": 2097152,
    "stdin_write_bytes": 1048576,
    "archive_bytes": 18874368,
    "expanded_bytes": 16777216,
    "archive_entries": 512,
    # 2026-09-14 (m01-output-budget amendment): the step deadline rises 30 -> 300
    # to cover real reasoning-model round trips at the step boundary; 300 -> 600
    # after threshold archiving made per-step model re-exploration realistic
    # (m01-real-2026-09-14aa counterexample: drive killed at 300s mid-tool).
    "deadline_seconds": 600,
}


def guarded(method):
    def invoke(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except ExecutionError:
            raise
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
            RecursionError,
        ) as exc:
            # Surface the wrapped cause (m01-real-2026-09-14au: the bare message
            # hid the value-dependent failure behind the new Node profile).
            tb = exc.__traceback__
            while tb is not None and tb.tb_next is not None:
                tb = tb.tb_next
            raise ExecutionError(
                "INVALID_REQUEST",
                "incomplete or invalid ordinary execution source: "
                + type(exc).__name__ + ": " + str(exc)
                + " at " + (tb.tb_frame.f_code.co_filename + ":"
                            + str(tb.tb_lineno) if tb else "?"),
            ) from exc

    return invoke


class NodeProfile:
    @guarded
    def __init__(self, config_path, expected_sha, state_root):
        self.config = document({"path": str(config_path), "sha256": expected_sha})
        self.state_root = Path(state_root).resolve()
        require(
            self.config.get("schema") == "lore-x-trusted-node-test-config/v1"
            and Path(self.config["state_root"]).resolve() == self.state_root,
            "UNAUTHORIZED",
            "trusted configuration scope differs",
        )
        self.principal = self.config["transport_principal"]
        self.roots = []
        for item in self.config["dynamic_reference_authorities"]:
            root = Path(item["root"])
            require(
                root.is_absolute()
                and root.resolve() == root
                and root.is_dir()
                and item["rule"] == "immutable-full-ref-registration/v1",
                "UNAUTHORIZED",
                "trusted reference authority root invalid",
            )
            info = root.stat()
            self.roots.append((copy.deepcopy(item), (info.st_dev, info.st_ino)))
        self.profiles = {}
        for ref in self.config["profiles"]:
            body = document(ref)
            require(
                body["id"] == ref["id"],
                "INVALID_REQUEST",
                "registered profile ID differs",
            )
            self.profiles[ref["id"]] = (copy.deepcopy(ref), body)
        require(
            self.roots and self.profiles,
            "UNAUTHORIZED",
            "trusted profile/reference authority missing",
        )

    def _registrations(self, kind):
        rows = []
        for authority, identity in self.roots:
            root = Path(authority["root"])
            current = root.stat()
            require(
                (current.st_dev, current.st_ino) == identity,
                "UNAUTHORIZED",
                "trusted authority root replaced",
            )
            if kind not in authority["allowed_kinds"]:
                continue
            for p in root.glob("*.json"):
                # Records are named by their exact complete original reference, never a latest pointer.
                from .ordinary_sources import json_value

                row = json_value(file_object(p, 2097152)[1])
                if type(row) is not dict or row.get("kind") != kind:
                    continue
                require(
                    p.name
                    == digest(canonical({"kind": kind, "ref": row["ref"]})) + ".json",
                    "UNAUTHORIZED",
                    "reference registration rebound",
                )
                require(
                    row["registered_scope"].get("namespace") == authority["namespace"],
                    "UNAUTHORIZED",
                    "reference namespace authority differs",
                )
                rows.append(row)
        return rows

    def _registered(self, kind, ref):
        matches = [row for row in self._registrations(kind) if row["ref"] == ref]
        require(
            len(matches) == 1,
            "UNAUTHORIZED",
            "complete original reference not registered",
        )
        return matches[0]

    @guarded
    def authorize(self, request, authority, operation):
        require(
            type(request) is dict
            and type(authority) is dict
            and operation in OPERATIONS,
            "UNAUTHORIZED",
            "original operation context absent",
        )
        require(
            not set(authority)
            & {
                "transport_principal",
                "trusted_config",
                "profile_registry",
                "slot_registry",
                "checker",
            },
            "INVALID_REQUEST",
            "peer cannot inject trusted configuration",
        )
        grant_ref = authority.get("grant_ref")
        self._registered("grant", grant_ref)
        grant = document(
            {"path": grant_ref["record_path"], "sha256": grant_ref["sha256"]}
        )
        require(
            self.principal in ("trusted-S", "trusted-tool")
            and grant["principal"] == self.principal
            and OPERATIONS[operation] in grant["operations"],
            "UNAUTHORIZED",
            "current principal lacks original grant",
        )
        require(
            grant["original_request"] == request
            and grant["request_digest"] == digest(canonical(request)),
            "UNAUTHORIZED",
            "complete original request differs from grant",
        )
        require(
            grant["slot_ref"] == authority.get("slot_ref"),
            "UNAUTHORIZED",
            "original slot grant differs",
        )
        if request.get("schema_version") == 2:
            require(
                grant["role"] == "session"
                and self.principal == "trusted-S"
                and grant["scope"] == request["session_binding"],
                "UNAUTHORIZED",
                "internal Session execution requires original trusted S scope",
            )
        else:
            require(
                grant["role"] == "tool", "UNAUTHORIZED", "legacy role is not a Session"
            )
        return copy.deepcopy(grant)

    @guarded
    def role_slot(self, request, authority):
        if request.get("schema_version") == 1 and "slot_ref" not in authority:
            return None
        grant = self.authorize(request, authority, "execute")
        ref = authority["slot_ref"]
        slots = [
            s
            for s in self.config["slots"]
            if s["slot_id"] == ref["slot_id"] and s["revision"] == ref["revision"]
        ]
        require(len(slots) == 1, "UNAUTHORIZED", "registered shared slot missing")
        slot = slots[0]
        require(
            ref.get("owner") == "trusted-X-configuration"
            and ref["role"] == grant["role"]
            and slot["namespace"] == grant["scope"]["namespace"]
            and self.principal in slot["allowed_principals"]
            and Path(slot["state_root"]).resolve() == self.state_root
            and slot["plan_sha256"]
            == ref["plan_sha256"]
            == digest(canonical(slot["plan"])),
            "UNAUTHORIZED",
            "complete original shared slot differs",
        )
        return {
            "slot_ref": copy.deepcopy(ref),
            "slot": copy.deepcopy(slot),
            "role": grant["role"],
            "grant": grant,
        }

    @guarded
    def runtime_input(self, request, authority):
        require(
            request.get("schema_version") == 1 and request.get("domain") == "runtime",
            "UNAUTHORIZED",
            "readonly tool input requires original runtime domain",
        )
        slot = self.role_slot(request, authority)
        require(
            slot is not None
            and slot["role"] == "tool"
            and slot["grant"]["scope"]["namespace"] == authority["namespace"],
            "UNAUTHORIZED",
            "readonly input original namespace/grant/slot differs",
        )
        return dict(
            slot,
            readonly_mounts=self._readonly_sources(
                request, None, roles={"input": "/input"}, namespace=authority["namespace"]
            ),
        )

    def _readonly_sources(self, request, profile, *, roles=None, namespace=None):
        mounts = request["readonly_mounts"]
        roles = roles or {
            "dependencies": "/opt",
            "harness": "/harness",
            "input": "/input",
            "workspace": "/workspace",
        }
        require(
            type(mounts) is list
            and len(mounts) == len(roles)
            and {m["role"] for m in mounts} == set(roles),
            "INVALID_REQUEST",
            "complete four readonly roles required",
        )
        if namespace is None:
            namespace = request["session_binding"]["namespace"]
        registrations = self._registrations("readonly-view")
        for mount in mounts:
            require(
                set(mount)
                == {
                    "role",
                    "source",
                    "target",
                    "read_only",
                    "manifest_ref",
                    "content_ref",
                }
                and mount["read_only"] is True
                and mount["target"] == roles[mount["role"]],
                "INVALID_REQUEST",
                "invalid readonly mount",
            )
            candidates = [
                r["ref"]
                for r in registrations
                if r["registered_scope"]
                == {
                    "namespace": namespace,
                    "role": mount["role"],
                }
                and r["ref"]["source"]["path"] == mount["source"]["path"]
            ]
            require(
                candidates,
                "UNAUTHORIZED",
                "readonly source outside trusted registered range",
            )
            require(
                mount in candidates,
                "INVALID_REQUEST",
                "readonly original reference changed",
            )
            require(
                not Path(mount["source"]["path"])
                .resolve()
                .is_relative_to(self.state_root)
                and not self.state_root.is_relative_to(
                    Path(mount["source"]["path"]).resolve()
                ),
                "UNAUTHORIZED",
                "readonly source overlaps control state",
            )
            source_path = Path(mount["source"]["path"]).resolve()
            require(
                not any(
                    source_path.is_relative_to(Path(a["root"]))
                    or Path(a["root"]).is_relative_to(source_path)
                    for a, _ in self.roots
                ),
                "UNAUTHORIZED",
                "readonly source overlaps reference control root",
            )
            manifest = readonly(mount)
            if mount["role"] == "dependencies":
                content = mount["content_ref"]
                upstream = content["upstream_manifest"]
                require(
                    content["owner"] == "trusted-X-configuration"
                    and content["kind"] == "profile-dependencies"
                    and upstream["sha256"] == profile["dependency_manifest"]["sha256"],
                    "INVALID_REQUEST",
                    "selected dependency profile differs",
                )
                source = document(upstream)
                files = {
                    str(Path(row["target"]).relative_to("/opt")): row
                    for row in source["files"]
                }
                for name, item in files.items():
                    actual = manifest["entries"].get(name, {})
                    require(
                        actual.get("kind") == "file"
                        and actual["sha256"] == item["sha256"]
                        and actual["byte_length"] == item["bytes"],
                        "INVALID_REQUEST",
                        "selected dependency actual bytes differ",
                    )
                links = {
                    str(Path(row["target"]).relative_to("/opt")): row["link"]
                    for row in source["links"]
                }
                require(
                    {
                        n: row["target"]
                        for n, row in manifest["entries"].items()
                        if row["kind"] == "symlink"
                    }
                    == links,
                    "INVALID_REQUEST",
                    "selected dependency links differ",
                )
                generated = content["generated_config"]
                expected = reference(generated["original"], 2097152)[1]
                require(
                    reference(generated, 2097152)[1] == expected
                    and generated["path"]
                    == str(Path(mount["source"]["path"]) / "lore/config/tsconfig.json"),
                    "INVALID_REQUEST",
                    "generated dependency configuration differs",
                )
                wanted = set(files) | {"lore/config/tsconfig.json"}
                require(
                    {
                        n
                        for n, row in manifest["entries"].items()
                        if row["kind"] == "file"
                    }
                    == wanted,
                    "INVALID_REQUEST",
                    "unexpected dependency files",
                )
            else:
                ref = mount["content_ref"]
                require(
                    ref["owner"] == "F" and ref["materialized_root"] == mount["source"],
                    "INVALID_REQUEST",
                    "ordinary F source association differs",
                )
                original = document(ref["original_manifest"])
                version = ref["version_ref"]
                require(
                    original.get("schema") == "lore-f-manifest/v1"
                    and ref["original_manifest"]["sha256"] == version["manifest_sha256"]
                    and all(
                        original[k] == version[k]
                        for k in ("domain", "profile", "resource_id")
                    ),
                    "INVALID_REQUEST",
                    "original F version differs",
                )
                saved, actual = original["tree"]["entries"], manifest["entries"]
                require(
                    set(saved) == set(actual),
                    "INVALID_REQUEST",
                    "F original complete member set differs",
                )
                for name, row in saved.items():
                    got = actual[name]
                    require(
                        all(
                            got[k] == row[k]
                            for k in ("kind", "mode", "uid", "gid", "mtime_ns")
                        )
                        and not row.get("xattrs"),
                        "INVALID_REQUEST",
                        "F original metadata differs",
                    )
                    if row["kind"] == "file":
                        require(
                            got["byte_length"] == row["size"]
                            and got["sha256"] == row["sha256"],
                            "INVALID_REQUEST",
                            "F original contents differ",
                        )
                    if row["kind"] == "symlink":
                        require(
                            base64.b64encode(os.fsencode(got["target"])).decode()
                            == row["target_b64"],
                            "INVALID_REQUEST",
                            "F original link differs",
                        )
                if mount["role"] == "harness":
                    require(
                        request["harness_version"] == ref["version_ref"],
                        "INVALID_REQUEST",
                        "Harness version differs",
                    )
        return copy.deepcopy(mounts)

    @guarded
    def prepare(self, request, authority):
        self.authorize(request, authority, "execute")
        require(
            set(request) == FIELDS
            and request["schema_version"] == 2
            and type(request["schema_version"]) is int,
            "INVALID_REQUEST",
            "unsupported Node request fields/schema",
        )
        require(
            request["environment"] in self.profiles
            and request["domain"] == "session",
            "INVALID_REQUEST",
            "internal Node profile/domain required",
        )
        entry, profile = self.profiles[request["environment"]]
        require(
            request["profile_sha256"] == entry["sha256"],
            "INVALID_REQUEST",
            "original Node profile changed",
        )
        require(
            type(request["object_generation"]) is int
            and request["object_generation"] > 0
            and type(request["session_binding"]["session_generation"]) is int
            and request["session_binding"]["session_generation"] > 0,
            "INVALID_REQUEST",
            "positive original generation required",
        )
        for key in ("execution_id", "caller", "invocation_id", "step_id"):
            require(
                type(request[key]) is str and 0 < len(request[key]) <= 256,
                "INVALID_REQUEST",
                "stable request identity required",
            )
        b = request["budgets"]
        # 2026-09-15 (amendment-linux-browser): per-profile budget maxima — the
        # profile document may raise ceilings for its environment via an optional
        # `budget_maxima` (same form as the X registry); absent means the base
        # LIMITS. The request still carries the full budget set every time.
        effective = {**LIMITS, **profile.get("budget_maxima", {})}
        require(
            set(b) == set(effective), "INVALID_REQUEST", "complete Node budget required"
        )
        for key, ceiling in effective.items():
            require(
                type(b[key]) in (int, float)
                and math.isfinite(b[key])
                and 0 < b[key] <= ceiling
                and (key in ("cpu", "deadline_seconds") or type(b[key]) is int),
                "INVALID_REQUEST",
                "Node profile budget exceeded",
            )
        require(
            request["environment_values"] == profile["environment"]
            and request["cwd"] == "/work"
            and request["io_mode"] == "duplex",
            "INVALID_REQUEST",
            "Node environment or working directory differs",
        )
        stdin = base64.b64decode(request["stdin_base64"], validate=True)
        require(
            len(stdin) <= b["stdin_write_bytes"],
            "INVALID_REQUEST",
            "Node initial input exceeds bound",
        )
        argv = request["command_argv"]
        require(
            type(argv) is list
            and 5 <= len(argv) <= 32
            and all(type(a) is str and len(a) <= 4096 and chr(0) not in a for a in argv)
            and argv[:3] == profile["argv_prefix"],
            "INVALID_REQUEST",
            "ordinary Node command prefix differs",
        )
        entries = [
            x
            for x in self.config["allowed_harness_entries"]
            if x["path"] == argv[3] and argv[4] in x["argv_modes"]
        ]
        require(
            len(entries) == 1,
            "UNAUTHORIZED",
            "ordinary Harness entry outside original grant",
        )
        mounts = self._readonly_sources(request, profile)
        harness = next(m for m in mounts if m["role"] == "harness")
        path = Path(harness["source"]["path"]) / Path(argv[3]).relative_to("/harness")
        require(
            file_object(path, 2097152, False)[0]["sha256"] == entries[0]["sha256"],
            "INVALID_REQUEST",
            "original Harness entry changed",
        )
        ref = request["snapshot_ref"]
        rows = [
            r
            for r in self._registrations("snapshot")
            if r["ref"].get("record_path") == ref.get("record_path")
        ]
        require(len(rows) == 1, "UNAUTHORIZED", "registered original S snapshot absent")
        registration = rows[0]
        scope = request["session_binding"]
        require(
            all(registration["registered_scope"][k] == scope[k] for k in SCOPE),
            "UNAUTHORIZED",
            "snapshot original scope differs",
        )
        require(
            registration["ref"] == ref
            and request["base_version"] == digest(canonical(ref)),
            "INVALID_REQUEST",
            "original snapshot reference differs",
        )
        original = snapshot(ref, registration["registered_scope"])
        limits = dict(b, volume_bytes=b["work_bytes"], inodes=b["work_inodes"])
        slot = self.role_slot(request, authority)
        extra = {
            **scope,
            "profile_sha256": request["profile_sha256"],
            "snapshot_sha256": ref["archive_sha256"],
            "readonly_mounts_sha256": digest(canonical(mounts)),
            "slot_id": slot["slot_ref"]["slot_id"],
            "slot_revision": slot["slot_ref"]["revision"],
        }
        return {
            "target_id": scope["session_id"],
            "domain": "session",
            "request_digest": digest(canonical(request)),
            "raw_archive": original["raw_archive"],
            "limits": limits,
            "binding_extra": extra,
            "readonly_mounts": mounts,
            "slot_ref": slot["slot_ref"],
            "slot": slot["slot"],
            "stdin": stdin,
            "argv": list(argv),
        }

    def _owned_original(self, ref, owner_ref, charge_ref, expected, fullref):
        owner = document(owner_ref)
        require(
            owner.get("schema") == "lore-s-original-snapshot-owner/v1"
            and owner["scope"] == {k: expected[k] for k in SCOPE},
            "UNAUTHORIZED",
            "actual owner Session scope differs",
        )
        require(
            owner["source"]
            == {"kind": "checkpoint", "original_checkpoint_full_ref": fullref}
            and owner["snapshot_ref"] == ref
            and owner["storage_charge_ref"] == charge_ref,
            "INVALID_REQUEST",
            "original ownership association differs",
        )
        registration = self._registered("snapshot", ref)
        require(
            registration["registered_scope"] == expected,
            "UNAUTHORIZED",
            "registered retained original scope differs",
        )
        observed = snapshot(ref, expected)
        fact = observed["archive_fact"]
        require(
            fact["sha256"] == fullref["sha256"]
            and fact["bytes"] == fullref["size"]
            and owner["actual_archive_object"] == fact["root"],
            "INVALID_REQUEST",
            "retained archive bytes/inode differ",
        )
        if Path(fullref["path"]).exists():
            old = reference(fullref)[0]
            require(
                old["root"] != fact["root"],
                "INVALID_REQUEST",
                "owner archive must be independent physical object",
            )
        self._registered("storage-charge", charge_ref)
        charge = document(charge_ref)
        require(
            charge["snapshot_ref"] == ref
            and charge["scope"] == owner["scope"]
            and charge["archive_fact"] == fact
            and type(charge["reserved_bytes"]) is int
            and fact["bytes"]
            <= charge["reserved_bytes"]
            <= charge["global_budget_bytes"],
            "INVALID_REQUEST",
            "owner original storage charge absent",
        )
        return owner

    @guarded
    def verify_owner_receipt(self, record, fullref, receipt):
        scope = record["request"]["session_binding"]
        binding = fullref["source_binding"]
        require(
            all(
                binding[k] == record["binding"][k]
                for k in EXEC
                if k != "freeze_generation"
            )
            and all(
                binding[k] == scope[k]
                for k in ("namespace", "session_id", "session_generation")
            ),
            "UNAUTHORIZED",
            "original checkpoint execution differs",
        )
        expected = {
            **scope,
            "original_execution": {
                **{k: binding[k] for k in EXEC},
                "state": fullref["state"],
            },
        }
        registration = self._registered("owner-receipt", receipt)
        require(
            registration["registered_scope"] == expected,
            "UNAUTHORIZED",
            "owner receipt registered scope differs",
        )
        body = document(receipt["actual_owner_receipt_path_sha_bytes"])
        require(
            body
            == {
                k: v
                for k, v in receipt.items()
                if k != "actual_owner_receipt_path_sha_bytes"
            }
            and body["owner"] == "S"
            and body["old_checkpoint_full_ref"] == fullref,
            "INVALID_REQUEST",
            "owner receipt original bytes/ref differ",
        )
        require(
            all(
                body[k] == scope[k]
                for k in ("namespace", "session_id", "session_generation")
            ),
            "UNAUTHORIZED",
            "owner receipt Session differs",
        )
        self._owned_original(
            body["retained_original_ref"],
            body["retained_owner_record_ref"],
            body["storage_charge_ref"],
            expected,
            fullref,
        )
        if body["handoff_kind"] == "sealed_ownership_transfer":
            require(
                body["confirmed_successor_full_ref"] is None
                and body["successor_owner_record_ref"] is None,
                "INVALID_REQUEST",
                "sealed transfer has invented successor",
            )
        else:
            require(
                body["handoff_kind"] == "successor_retained",
                "INVALID_REQUEST",
                "unknown original ownership transfer",
            )
            successor = body["confirmed_successor_full_ref"]
            newer = copy.deepcopy(expected)
            require(
                all(
                    successor["source_binding"][k] == binding[k]
                    for k in EXEC
                    if k != "freeze_generation"
                )
                and successor["freeze_generation"] > fullref["freeze_generation"],
                "UNAUTHORIZED",
                "successor original execution/generation differs",
            )
            newer["original_execution"].update(
                freeze_generation=successor["freeze_generation"],
                state=successor["state"],
            )
            owner = document(body["successor_owner_record_ref"])
            self._owned_original(
                owner["snapshot_ref"],
                body["successor_owner_record_ref"],
                owner["storage_charge_ref"],
                newer,
                successor,
            )
        return copy.deepcopy(receipt)
