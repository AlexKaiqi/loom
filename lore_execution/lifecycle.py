"""Freeze/export precedes actual stop; restoration never dispatches a command."""

from pathlib import Path
import copy, time
from .archives import export_volume, inspect
from .errors import ExecutionError, require
from .journal import canonical, digest
from .requests import validate


class Lifecycle:
    def _live(self, id, authority, operation="query"):
        record = self._load(id, authority, operation)
        return self.channels[id].record if id in self.channels else record

    def request_stop(self, id, authority, stop_id):
        record = self._live(id, authority, "stop")
        require(
            record["request"]["schema_version"] == 2
            or "stop" in authority.get("grants", []),
            "UNAUTHORIZED",
            "stop permission absent",
        )
        prior = record.get("stop_id")
        require(
            prior is None or prior == stop_id, "ID_CONFLICT", "stop identity changed"
        )
        record["stop_id"] = stop_id
        record["result"]["stop_requested"] = True
        self.journal.put(record)
        return self._response(record)

    def checkpoint(self, id, authority, checkpoint_id, purpose):
        # One original X owner serializes capacity admission with the real export.
        with self.journal.lock:
            return self._checkpoint_locked(id, authority, checkpoint_id, purpose)

    def _checkpoint_locked(self, id, authority, checkpoint_id, purpose):
        record = self._live(id, authority, "checkpoint")
        require(
            record["request"]["schema_version"] == 2
            or "checkpoint" in authority.get("grants", []),
            "UNAUTHORIZED",
            "checkpoint permission absent",
        )
        if checkpoint_id in record["checkpoints"]:
            saved = record["checkpoints"][checkpoint_id]
            require(
                saved["purpose"] == purpose, "ID_CONFLICT", "checkpoint purpose differs"
            )
            if saved.get("artifact") is not None:
                self.journal.read(
                    saved["artifact"],
                    record.get("limits", record["request"]["budgets"])["archive_bytes"],
                )
                return self._response(record) | {
                    "artifacts": {
                        **copy.deepcopy(record["artifacts"]),
                        "checkpoint": copy.deepcopy(saved["artifact"]),
                    }
                }
        cid = record["binding"]["container_id"]
        actual = self.engine.inspect(cid)
        require(
            actual is not None and actual["State"]["Running"],
            "STOPPED",
            "original environment not available for a new checkpoint",
        )
        if record["request"]["schema_version"] == 2:
            if checkpoint_id not in record["checkpoints"]:
                require(
                    sum(
                        c.get("retention", {}).get("state") != "RELEASED"
                        for c in record["checkpoints"].values()
                    )
                    < 2,
                    "SLOT_EXHAUSTED",
                    "two original checkpoints still retained",
                )
                record["checkpoints"][checkpoint_id] = {
                    "purpose": purpose,
                    "artifact": None,
                    "state": "PREPARING",
                    "archive_name": "checkpoint-" + digest(checkpoint_id.encode()),
                }
                self.journal.put(record)
        if not actual["State"]["Paused"]:
            self.engine.call("POST", "/containers/" + cid + "/pause")
            record["binding"]["freeze_generation"] += 1
        actual = self.engine.inspect(cid)
        require(
            actual["State"]["Paused"],
            "UNKNOWN",
            "Engine did not establish original freeze",
        )
        record["result"]["execution_state"] = "FROZEN"
        self.journal.put(record)
        raw, members = export_volume(self.engine, record)
        name = (
            "checkpoint-" + digest(checkpoint_id.encode())
            if record["request"]["schema_version"] == 2
            else "checkpoint"
        )
        ref = self.journal.blob(id, name, raw)
        ref.update(
            state="PREPARED",
            owner="X",
            execution_id=id,
            object_generation=record["binding"]["object_generation"],
            freeze_generation=record["binding"]["freeze_generation"],
            source_binding=copy.deepcopy(record["binding"]),
            members=members,
        )
        record["artifacts"]["checkpoint"] = ref
        record["checkpoints"].setdefault(checkpoint_id, {"purpose": purpose}).update(
            artifact=copy.deepcopy(ref), state="PREPARED"
        )
        self.journal.put(record)
        return self._response(record)

    def _receipt(self, record, receipt):
        require(
            type(receipt) is dict and receipt == record["artifacts"].get("checkpoint"),
            "STALE_CHECKPOINT",
            "original prepared receipt differs",
        )
        b = record["binding"]
        require(
            receipt["execution_id"] == b["execution_id"]
            and receipt["object_generation"] == b["object_generation"]
            and receipt["freeze_generation"] == b["freeze_generation"],
            "STALE_CHECKPOINT",
            "receipt belongs to another object/freeze",
        )
        self.journal.read(
            receipt, record.get("limits", record["request"]["budgets"])["archive_bytes"]
        )

    def resume(self, id, authority, receipt):
        record = self._live(id, authority, "execute")
        require(
            record["request"]["schema_version"] == 2
            or "execute" in authority.get("grants", []),
            "UNAUTHORIZED",
            "resume permission absent",
        )
        self._receipt(record, receipt)
        cid = record["binding"]["container_id"]
        actual = self.engine.inspect(cid)
        require(
            actual is not None
            and actual["State"]["Running"]
            and actual["State"]["Paused"],
            "STALE_CHECKPOINT",
            "same original object is not frozen",
        )
        self.engine.call("POST", "/containers/" + cid + "/unpause")
        record["result"]["execution_state"] = (
            "RUNNING" if record["issued"] else "CREATED"
        )
        self.journal.put(record)
        return self._response(record)

    def stop_physical(self, record, reason):
        cid = record["binding"].get("container_id")
        actual = self.engine.inspect(cid) if cid else None
        if actual and actual["State"]["Running"]:
            self.engine.call("POST", "/containers/" + cid + "/kill?signal=SIGKILL")
        actual = self.engine.inspect(cid) if cid else None
        require(
            actual is None or not actual["State"]["Running"],
            "UNKNOWN",
            "original container has not actually stopped",
        )
        record["result"].update(execution_state="STOPPED", reason=reason)
        self.journal.put(record)
        return actual

    def seal(self, id, authority, receipt):
        record = self._live(id, authority, "stop")
        self._receipt(record, receipt)
        require(
            record["request"]["schema_version"] == 2
            or "stop" in authority.get("grants", []),
            "UNAUTHORIZED",
            "seal permission absent",
        )
        if "stopped" in record["artifacts"]:
            self.journal.read(
                record["artifacts"]["stopped"],
                record.get("limits", record["request"]["budgets"])["archive_bytes"],
            )
            return self._response(record)
        current = self.engine.inspect(record["binding"]["container_id"])
        require(
            record["result"]["execution_state"] == "FROZEN"
            and current is not None
            and current["State"]["Running"]
            and current["State"]["Paused"],
            "STALE_CHECKPOINT",
            "sealed source must remain in its original frozen generation",
        )
        state = self.stop_physical(record, "SEALED")
        channel = self.channels.get(id)
        if channel:
            channel.done.wait(2)
        elif record["request"]["schema_version"] == 2:
            if record["result"]["output_state"] == "PENDING":
                record["result"]["output_state"] = "INCOMPLETE_OBSERVATION"
            for stream in ("stdout", "stderr"):
                path = self._stream_path(record, stream)
                data = path.read_bytes() if path.exists() else b""
                record["artifacts"][stream] = self._output_ref(record, stream, data)
        proof = {
            "owner": "X",
            "kind": "stopped",
            "execution_id": id,
            "object_generation": record["binding"]["object_generation"],
            "target_id": record["binding"]["target_id"],
            "domain": record["binding"]["domain"],
            "binding_generation": record["request"].get(
                "binding_generation",
                record["request"].get("session_binding", {}).get("session_generation"),
            ),
            "base_version": record["request"]["base_version"],
            "container_id": record["binding"]["container_id"],
            "exec_id": record["binding"]["exec_id"],
            "prepared_ref": copy.deepcopy(receipt),
            "engine_state": state["State"] if state else None,
        }
        record["artifacts"]["stopped"] = self.journal.blob(
            id, "stopped-proof", canonical(proof)
        )
        self.journal.put(record)
        return self._response(record)

    def release(self, id, authority):
        record = self._live(id, authority, "stop")
        require(
            record["request"]["schema_version"] == 2
            or "stop" in authority.get("grants", []),
            "UNAUTHORIZED",
            "release permission absent",
        )
        cid = record["binding"].get("container_id")
        actual = self.engine.inspect(cid) if cid else None
        require(
            actual is None or not actual["State"]["Running"],
            "BUSY",
            "actual original environment remains live",
        )
        if record.get("released"):
            volume = record["binding"].get("volume_id")
            remaining = (
                self.engine.call("GET", "/volumes/" + volume, missing=True)
                if volume
                else None
            )
            require(
                actual is None and remaining is None,
                "INCOMPLETE_OBSERVATION",
                "original released objects reappeared",
            )
            if self.slots and record.get("slot_ref"):
                self.slots.release(record)
            return self._response(record)
        require(
            record["result"]["output_state"] != "PENDING",
            "INCOMPLETE_OBSERVATION",
            "result has not reached a durable observation boundary",
        )
        if cid:
            self.engine.call(
                "DELETE", "/containers/" + cid + "?force=true", missing=True
            )
        if record["binding"].get("volume_id"):
            self.engine.call(
                "DELETE", "/volumes/" + record["binding"]["volume_id"], missing=True
            )
        record["result"]["execution_state"] = "STOPPED"
        record["released"] = True
        self.journal.put(record)
        self.channels.pop(id, None)
        if self.slots and record.get("slot_ref"):
            self.slots.release(record)
        return self._response(record)

    def restore(self, request, authority, source_ref, object_generation):
        request, authority, source_ref = (
            copy.deepcopy(request),
            copy.deepcopy(authority),
            copy.deepcopy(source_ref),
        )
        prior = self.journal.get(request["execution_id"])
        if prior:
            self._authorized(prior, authority)
            require(
                prior["binding"]["request_digest"] == digest(canonical(request)),
                "ID_CONFLICT",
                "restore identity differs",
            )
            return self.query(request["execution_id"], authority)
        checked = validate(request, authority, self.journal.root, restore=True)
        require(
            source_ref
            == authority.get("restore_source")
            == request.get("restore_source"),
            "UNAUTHORIZED",
            "explicit selected source differs",
        )
        require(
            source_ref.get("owner") == "X"
            and source_ref.get("metadata_profile") == authority.get("metadata_profile"),
            "INPUT_VERSION_UNAVAILABLE",
            "unsupported original restore source",
        )
        original = self._load(source_ref["source_execution_id"], authority)
        require(
            source_ref["source_object_generation"]
            == original["binding"]["object_generation"]
            and source_ref["input_manifest"] == original["request"]["input_manifest"],
            "INPUT_VERSION_UNAVAILABLE",
            "original source execution/version differs",
        )
        known = [
            x["artifact"]
            for x in original["checkpoints"].values()
            if x["artifact"]["freeze_generation"] == source_ref["freeze_generation"]
            and x["artifact"]["sha256"] == source_ref["archive_ref"]["sha256"]
        ]
        require(
            len(known) == 1
            and known[0]["source_binding"] == source_ref["source_binding"],
            "INPUT_VERSION_UNAVAILABLE",
            "selected original checkpoint association absent",
        )
        require(
            type(object_generation) is int
            and object_generation > source_ref["source_object_generation"]
            and object_generation
            == request["object_generation"]
            == authority.get("object_generation"),
            "STALE_BINDING",
            "restore requires a new original object generation",
        )
        ref = source_ref["archive_ref"]
        path = Path(ref["path"])
        try:
            require(
                path.is_absolute() and not path.is_symlink(),
                "INPUT_VERSION_UNAVAILABLE",
                "source path alias",
            )
            with path.open("rb") as stream:
                raw = stream.read(request["budgets"]["archive_bytes"] + 1)
            require(
                len(raw) == ref["size"] and digest(raw) == ref["sha256"],
                "INPUT_VERSION_UNAVAILABLE",
                "selected source bytes differ",
            )
            inspect(raw, request["budgets"])
        except (OSError, ExecutionError) as exc:
            raise ExecutionError(
                "INPUT_VERSION_UNAVAILABLE",
                "selected original source unavailable: " + str(exc),
            ) from exc
        record, _ = self._create(request, authority, checked, raw, object_generation)
        return self._response(record)
