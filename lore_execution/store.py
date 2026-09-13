"""Own only execution associations and original output, never task strategy/history."""

import base64, copy, os, threading, time, uuid
from pathlib import Path
from .archives import initial, import_volume, inspect
from .channel import Channel
from .engine import Engine, PROFILE, command
from .errors import ExecutionError, require
from .journal import Journal, canonical, digest
from .requests import validate
from .lifecycle import Lifecycle
from .calls import CallOperations
from .retention import Retention
from .node_profile import NodeProfile
from .slots import SlotLedger


class ExecutionStore(CallOperations, Retention, Lifecycle):
    def __init__(
        self,
        state_dir,
        engine_endpoint=None,
        checkpoint=None,
        trusted_config=None,
        trusted_config_sha256=None,
    ):
        self.journal = Journal(state_dir)
        self.node_profile = (
            NodeProfile(trusted_config, trusted_config_sha256, self.journal.root)
            if trusted_config
            else None
        )
        self.slots = (
            SlotLedger(self.journal, self.node_profile.config)
            if self.node_profile
            else None
        )
        self.engine = Engine(engine_endpoint)
        self.engine.slots = self.slots
        if self.slots:
            self.journal.write_guard = self.slots.guard_write
        self.channels = {}
        self.checkpoint_hook = checkpoint or (lambda label, record: None)

    def _barrier(self, label, record):
        self.checkpoint_hook(label, copy.deepcopy(record["binding"]))

    def _response(self, record):
        with self.journal.lock:
            value = copy.deepcopy(
                {key: record[key] for key in ("binding", "result", "artifacts")}
            )
            if self.slots and record.get("slot_ref"):
                value["artifacts"]["slot"] = self.slots.snapshot(record)
            return value

    def _authorized(self, record, authority, operation="query"):
        request = record["request"]
        if self.node_profile:
            self.node_profile.authorize(request, authority, operation)
            if request["schema_version"] == 2:
                return
        require(
            authority.get("caller") == request["caller"]
            and authority.get("domain") == request["domain"]
            and authority.get("target_id") == record["binding"]["target_id"]
            and authority.get("binding_generation") == request["binding_generation"],
            "UNAUTHORIZED",
            "original execution scope differs",
        )
        require(
            authority.get("namespace") == record["authority"]["namespace"]
            and "query" in authority.get("grants", [])
            and Path(authority["state_dir"]).resolve() == self.journal.root,
            "UNAUTHORIZED",
            "original query scope absent",
        )

    def _load(self, id, authority, operation="query"):
        record = self.journal.get(id)
        require(record is not None, "NOT_FOUND", "execution was not accepted")
        self._authorized(record, authority, operation)
        return record

    def _create(self, request, authority, checked, raw, generation):
        id = request["execution_id"]
        with self.journal.lock:
            old = self.journal.get(id)
            if old is not None:
                require(
                    old["binding"]["request_digest"] == checked["request_digest"],
                    "ID_CONFLICT",
                    "immutable execution identity differs",
                )
                return old, False
            record = {
                "request": copy.deepcopy(request),
                "authority": copy.deepcopy(authority),
                "binding": {
                    key: checked[key]
                    for key in ("target_id", "domain", "request_digest")
                },
                "result": {
                    "execution_state": "NOT_STARTED",
                    "output_state": "PENDING",
                    "stop_requested": False,
                },
                "artifacts": {},
                "issued": False,
                "checkpoints": {},
            }
            record["binding"].update(
                execution_id=id,
                object_generation=generation,
                freeze_generation=0,
                exec_id_present=False,
            )
            record["limits"] = copy.deepcopy(checked.get("limits", request["budgets"]))
            record["binding"].update(copy.deepcopy(checked.get("binding_extra", {})))
            if request["schema_version"] == 2:
                record["binding"]["channel_id"] = "channel-" + uuid.uuid4().hex
                record["result"]["execution_state"] = "PREPARING"
                record["calls"] = {}
                record["stdin_offset"] = 0
            if checked.get("slot_ref"):
                record["slot_ref"] = copy.deepcopy(checked["slot_ref"])
                record["role"] = checked["role"]
                self.slots.reserve(record, record["slot_ref"], record["role"])
            self.journal.put(record)
        if record.get("slot_ref"):
            self._barrier("slot_reserved_before_engine_create", record)
        volume = "lore-" + uuid.uuid4().hex
        record["binding"]["volume_id"] = volume
        self.journal.put(record)
        b = record["limits"]
        self.engine.call(
            "POST",
            "/volumes/create",
            {
                "Name": volume,
                "Driver": "local",
                "Labels": {"lore.x.execution_id": id},
                "DriverOpts": {
                    "type": "tmpfs",
                    "device": "tmpfs",
                    "o": "size="
                    + str(b["volume_bytes"])
                    + ",nr_inodes="
                    + str(b["inodes"])
                    + ",uid=1000,gid=1000,mode=0700",
                },
            },
        )
        keeper = "import signal\nwhile True:signal.pause()"
        cid = (
            command(
                [
                    "/usr/bin/docker",
                    "create",
                    *self.engine.options(b),
                    *self.engine.slot_labels(record),
                    *[
                        arg
                        for mount in checked.get("readonly_mounts", [])
                        for arg in (
                            "--mount",
                            "type=bind,src="
                            + mount["source"]["path"]
                            + ",dst="
                            + mount["target"]
                            + ",readonly",
                        )
                    ],
                    "--user",
                    "0:0",
                    "--label",
                    "lore.x.execution_id=" + id,
                    "--mount",
                    "type=volume,src=" + volume + ",dst=/work,volume-nocopy",
                    PROFILE["image"],
                    "python",
                    "-c",
                    keeper,
                ]
            )
            .decode()
            .strip()
        )
        record["binding"]["container_id"] = cid
        self.journal.put(record)
        self.engine.call("POST", "/containers/" + cid + "/start")
        import_volume(self.engine, record, raw)
        node = request["schema_version"] == 2
        argv = (
            request["command_argv"]
            if node
            else [*request["interpreter_argv"], checked["script"].decode("utf-8")]
        )
        created = self.engine.call(
            "POST",
            "/containers/" + cid + "/exec",
            {
                "AttachStdin": True,
                "AttachStdout": True,
                "AttachStderr": True,
                "Tty": False,
                "User": "1000:1000",
                "Privileged": False,
                "WorkingDir": (
                    request["cwd"]
                    if node
                    else "/work"
                    + ("" if request["cwd"] == "." else "/" + request["cwd"])
                ),
                "Env": (
                    [k + "=" + v for k, v in request["environment_values"].items()]
                    if node
                    else ["HOME=/work", "LANG=C.UTF-8", "PYTHONDONTWRITEBYTECODE=1"]
                ),
                "Cmd": argv,
            },
        )
        record["binding"].update(exec_id=created["Id"], exec_id_present=True)
        record["result"]["execution_state"] = "CREATED"
        self.journal.put(record)
        return record, True

    def execute(self, request, authority):
        request, authority = copy.deepcopy(request), copy.deepcopy(authority)
        if "readonly_mounts" in request and request.get("schema_version") == 1:
            require(
                self.node_profile is not None,
                "UNAUTHORIZED",
                "readonly input requires trusted NodeProfile configuration",
            )
        if self.node_profile:
            self.node_profile.authorize(request, authority, "execute")
        prior = self.journal.get(request["execution_id"])
        if prior is not None:
            if not self.node_profile:
                self._authorized(prior, authority)
            require(
                prior["binding"]["request_digest"] == digest(canonical(request)),
                "ID_CONFLICT",
                "same execution ID differs",
            )
            return self.query(request["execution_id"], authority)
        if request.get("schema_version") == 2:
            require(
                self.node_profile is not None,
                "INVALID_REQUEST",
                "Node profile is not enabled",
            )
            checked = self.node_profile.prepare(request, authority)
            checked["role"] = "session"
            raw = checked["raw_archive"]
            generation = request["object_generation"]
        else:
            checked = validate(request, authority, self.journal.root)
            if self.node_profile:
                checked.update(
                    self.node_profile.runtime_input(request, authority)
                    if "readonly_mounts" in request
                    else self.node_profile.role_slot(request, authority) or {}
                )
            raw = initial(request)
            members = inspect(raw, request["budgets"])
            for item in request["input_manifest"]["files"]:
                actual = members.get(item["path"], {})
                require(
                    actual.get("sha256") == item["sha256"]
                    and actual.get("size") == item["size"],
                    "INPUT_VERSION_UNAVAILABLE",
                    "copied archive differs from immutable input",
                )
            generation = time.monotonic_ns() // 1000
        record, new = self._create(request, authority, checked, raw, generation)
        if new:
            self._barrier("after_exec_created_before_start", record)
            self._dispatch(record)
        return self._response(record)

    def _dispatch(self, record):
        with self.journal.lock:
            current = self.journal.get(record["request"]["execution_id"])
            require(
                current["result"]["execution_state"] == "CREATED"
                and not current["issued"],
                "UNCERTAIN_EXECUTION",
                "only positively never-started exec may dispatch",
            )
            require(
                not current["result"]["stop_requested"],
                "STOP_REQUESTED",
                "original stop request already accepted",
            )
            record["issued"] = True
            record["result"]["execution_state"] = "RUNNING"
            self.journal.put(record)
            channel = Channel(self, record)
            self.channels[record["request"]["execution_id"]] = channel
        channel.start()
        stdin = base64.b64decode(record["request"]["stdin_base64"])
        if stdin:
            channel.write(
                stdin, maximum=record["limits"].get("stdin_write_bytes", 65536)
            )
            record["stdin_offset"] = len(stdin)
            self.journal.put(record)
        if record["request"]["io_mode"] == "finite":
            channel.close_input()
        self._barrier("after_start_before_receipt", record)

    def dispatch_created(self, id, authority):
        record = self._load(id, authority, "execute")
        require(
            record["request"]["schema_version"] == 2
            or "execute" in authority.get("grants", []),
            "UNAUTHORIZED",
            "dispatch permission absent",
        )
        self._dispatch(record)
        return self._response(record)

    def query(self, id, authority):
        record = self._load(id, authority)
        channel = self.channels.get(id)
        if channel is not None:
            return self._response(channel.record)
        if record["issued"] and record["result"]["output_state"] == "PENDING":
            actual = self.engine.inspect_exec(record["binding"]["exec_id"])
            environment = self.engine.inspect(record["binding"]["container_id"])
            state = "UNKNOWN"
            if environment is not None:
                state = (
                    "STOPPED"
                    if not environment["State"]["Running"]
                    else "FROZEN" if environment["State"]["Paused"] else "RUNNING"
                )
            record["result"].update(
                output_state="INCOMPLETE_OBSERVATION",
                execution_state=state,
            )
            if actual and not actual["Running"]:
                record["result"]["exit_code"] = actual["ExitCode"]
            self.journal.put(record)
        for name in ("stdout", "stderr"):
            if name in record["artifacts"]:
                self.journal.read(
                    record["artifacts"][name],
                    record.get("limits", record["request"]["budgets"])[name + "_bytes"],
                )
        return self._response(record)

    def complete_observation(self, channel, resource_reason):
        record = channel.record
        self._barrier("after_effect_before_output_barrier", record)
        with self.journal.lock:
            for name, data in channel.parts.items():
                record["artifacts"][name] = self._output_ref(record, name, bytes(data))
            actual = self.engine.inspect_exec(record["binding"]["exec_id"])
            if actual and not actual["Running"]:
                record["result"]["exit_code"] = actual["ExitCode"]
            if record["result"]["output_state"] != "INCOMPLETE_LIMIT":
                record["result"]["output_state"] = (
                    "COMPLETE"
                    if channel.eof and actual is not None and not actual["Running"]
                    else "INCOMPLETE_OBSERVATION"
                )
            if (
                resource_reason
                and record["result"]["output_state"] != "INCOMPLETE_LIMIT"
            ):
                record["result"]["reason"] = resource_reason
            self.journal.put(record)

    def observation_failed(self, channel, reason):
        record = channel.record
        with self.journal.lock:
            for name, data in channel.parts.items():
                record["artifacts"][name] = self._output_ref(record, name, bytes(data))
            if record["result"]["output_state"] != "INCOMPLETE_LIMIT":
                record["result"]["output_state"] = "INCOMPLETE_OBSERVATION"
            record["result"]["observation_error"] = reason
            self.journal.put(record)

    def await_exit(self, id, authority, timeout=9):
        record = self._load(id, authority)
        channel = self.channels.get(id)
        if channel is not None:
            require(
                channel.done.wait(timeout),
                "EXECUTION_PENDING",
                "original execution remains active",
            )
            record = channel.record
        return self._response(record)

    def _channel(self, id, authority):
        self._load(id, authority)
        require(
            id in self.channels,
            "INCOMPLETE_OBSERVATION",
            "original live stream unavailable after observer restart",
        )
        return self.channels[id]

    def _output_ref(self, record, name, data):
        if record["request"]["schema_version"] == 1:
            return self.journal.blob(record["request"]["execution_id"], name, data)
        path = self._stream_path(record, name)
        if not path.exists():
            from .journal import atomic

            atomic(path, b"")
        require(
            path.read_bytes() == data,
            "RESULT_UNAVAILABLE",
            "durable original stream differs",
        )
        return {"path": str(path), "sha256": digest(data), "size": len(data)}
