"""Original X channel calls: durable issue identity, explicit ranges, no replay."""

import base64, copy, os, time, threading
from .errors import ExecutionError, require
from .journal import canonical, digest


def serialized(method):
    def invoke(self, id, *args, **kwargs):
        with self.journal.lock:
            if not hasattr(self, "_channel_call_locks"):
                self._channel_call_locks = {}
            lock = self._channel_call_locks.setdefault(id, threading.RLock())
        with lock:
            return method(self, id, *args, **kwargs)

    return invoke


class CallOperations:
    def _call_binding(self, record, method, fields):
        require(
            type(fields) is dict, "INVALID_REQUEST", "complete original call required"
        )
        b = record["binding"]
        for key in (
            "execution_id",
            "object_generation",
            "channel_id",
            "request_digest",
        ):
            require(
                fields.get(key) == b[key],
                "UNAUTHORIZED",
                "original channel differs: " + key,
            )
        require(
            fields.get("method") == method, "INVALID_REQUEST", "call method differs"
        )
        require(
            type(fields.get("call_id")) is str and 0 < len(fields["call_id"]) <= 256,
            "INVALID_REQUEST",
            "bounded call identity required",
        )
        offset = fields.get("byte_offset", 0)
        require(
            type(offset) is int and offset >= 0,
            "INVALID_REQUEST",
            "explicit byte offset required",
        )
        return {
            key: fields[key]
            for key in (
                "call_id",
                "method",
                "execution_id",
                "object_generation",
                "channel_id",
                "request_digest",
            )
        } | {"byte_offset": offset}

    def _save_call(self, record, request, body):
        with self.journal.lock:
            ref = self.journal.blob(
                record["request"]["execution_id"],
                "call-" + digest(body["call_id"].encode()),
                canonical(body),
            )
            record.setdefault("calls", {})[body["call_id"]] = {
                "request": copy.deepcopy(request),
                "ref": ref,
                "body": copy.deepcopy(body),
            }
            self.journal.put(record)
        return ref

    def _call_response(self, record, saved):
        require(
            self.journal.read(saved["ref"], 2097152) == canonical(saved["body"]),
            "RESULT_UNAVAILABLE",
            "original call receipt bytes differ",
        )
        result = self._response(record) | {"call_ref": copy.deepcopy(saved["ref"])}
        body = saved["body"]
        if body["method"] == "channel_read":
            data = self._read_stream(
                record,
                saved["request"]["stream"],
                body["byte_offset"],
                body["data_bytes"],
            )
            require(
                len(data) == body["data_bytes"] and digest(data) == body["data_sha256"],
                "RESULT_UNAVAILABLE",
                "original read range is unavailable",
            )
            result.update(
                data_base64=base64.b64encode(data).decode(),
                stream=saved["request"]["stream"],
                byte_offset=body["byte_offset"],
                next_byte_offset=body["byte_offset"] + len(data),
            )
        elif body["state"] != "CONFIRMED":
            result["error"] = {
                "code": "INCOMPLETE_OBSERVATION",
                "message": "original issued call is not replayable",
            }
        return result

    def _stream_path(self, record, stream):
        return self.journal.directory(record["request"]["execution_id"]) / (
            stream + ".stream"
        )

    def _read_stream(self, record, stream, offset, size):
        path = self._stream_path(record, stream)
        if not path.exists():
            require(size == 0, "RESULT_UNAVAILABLE", "original stream missing")
            return b""
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            return os.pread(fd, size, offset)
        finally:
            os.close(fd)

    def query_call(self, id, authority, fields):
        record = self._live(id, authority)
        method = fields.get("method")
        key = self._call_binding(record, method, fields)
        saved = record.get("calls", {}).get(key["call_id"])
        require(saved is not None, "NOT_FOUND", "original call was not issued")
        require(
            all(saved["body"][k] == v for k, v in key.items()),
            "ID_CONFLICT",
            "original call binding differs",
        )
        return self._call_response(record, saved)

    @serialized
    def channel_read(self, id, authority, stream, maximum, fields=None):
        record = self._live(id, authority)
        if record["request"]["schema_version"] == 1:
            channel = self._channel(id, authority)
            return self._response(channel.record) | {
                "channel": channel.read(stream, maximum)
            }
        body = self._call_binding(record, "channel_read", fields)
        require(
            stream in ("stdout", "stderr")
            and type(maximum) is int
            and 0 < maximum <= 1048576,
            "INVALID_REQUEST",
            "bounded explicit stream range required",
        )
        signature = body | {"stream": stream, "maximum": maximum}
        saved = record.get("calls", {}).get(body["call_id"])
        if saved:
            require(
                saved["request"] == signature, "ID_CONFLICT", "original read changed"
            )
            return self._call_response(record, saved)
        channel = self.channels.get(id)
        end = time.monotonic() + 2
        path = self._stream_path(record, stream)
        while channel and not channel.done.is_set() and time.monotonic() < end:
            if path.exists() and path.stat().st_size > body["byte_offset"]:
                break
            time.sleep(0.005)
        data = (
            self._read_stream(record, stream, body["byte_offset"], maximum)
            if path.exists()
            else b""
        )
        body.update(
            data_sha256=digest(data),
            data_bytes=len(data),
            state="CONFIRMED",
            written_bytes=0,
        )
        self._save_call(record, signature, body)
        return self._call_response(record, record["calls"][body["call_id"]])

    @serialized
    def channel_write(self, id, authority, data, fields=None):
        record = self._live(id, authority, "execute")
        if record["request"]["schema_version"] == 1:
            channel = self._channel(id, authority)
            require(
                "execute" in authority.get("grants", []),
                "UNAUTHORIZED",
                "stdin grant absent",
            )
            channel.write(data)
            return self._response(record)
        body = self._call_binding(record, "channel_write", fields)
        require(
            isinstance(data, bytes)
            and len(data) <= record["limits"]["stdin_write_bytes"],
            "INVALID_REQUEST",
            "bounded stdin bytes required",
        )
        signature = body | {"data_sha256": digest(data), "data_bytes": len(data)}
        saved = record.get("calls", {}).get(body["call_id"])
        if saved:
            require(
                saved["request"] == signature, "ID_CONFLICT", "original write changed"
            )
            return self._call_response(record, saved)
        require(
            body["byte_offset"] == record.get("stdin_offset", 0),
            "INVALID_REQUEST",
            "stdin offset is not current original boundary",
        )
        require(
            not any(
                v["body"]["method"] == "channel_write"
                and v["body"]["state"] != "CONFIRMED"
                for v in record.get("calls", {}).values()
            ),
            "INCOMPLETE_OBSERVATION",
            "prior original write unresolved",
        )
        channel = self._channel(id, authority)
        require(
            not channel.input_closed
            and not channel.eof
            and record["result"]["execution_state"] != "FROZEN",
            "INCOMPLETE_OBSERVATION",
            "original stdin unavailable",
        )
        body = signature | {"state": "ISSUED", "written_bytes": 0}
        self._save_call(record, signature, body)

        def progress(written):
            body.update(
                written_bytes=written,
                state="CONFIRMED" if written == len(data) else "UNKNOWN",
            )
            if written == len(data):
                record["stdin_offset"] = body["byte_offset"] + written
            self._save_call(record, signature, body)
            if written < len(data):
                self._barrier("channel_prefix_written_before_ack", record)

        try:
            channel.write(
                data, maximum=record["limits"]["stdin_write_bytes"], progress=progress
            )
            if not data:
                progress(0)
        except (ExecutionError, OSError):
            body["state"] = "UNKNOWN"
            self._save_call(record, signature, body)
            return self._call_response(record, record["calls"][body["call_id"]])
        self._barrier("channel_written_before_ack", record)
        return self._call_response(record, record["calls"][body["call_id"]])

    @serialized
    def close_stdin(self, id, authority, fields=None):
        record = self._live(id, authority, "execute")
        if record["request"]["schema_version"] == 1:
            require(
                "execute" in authority.get("grants", []),
                "UNAUTHORIZED",
                "stdin EOF grant absent",
            )
            self._channel(id, authority).close_input()
            return self._response(record)
        body = self._call_binding(record, "close_stdin", fields)
        signature = copy.deepcopy(body)
        saved = record.get("calls", {}).get(body["call_id"])
        if saved:
            require(
                saved["request"] == signature, "ID_CONFLICT", "original EOF changed"
            )
            return self._call_response(record, saved)
        channel = self._channel(id, authority)
        body.update(
            data_sha256=digest(b""), data_bytes=0, state="ISSUED", written_bytes=0
        )
        self._save_call(record, signature, body)
        channel.close_input()
        body["state"] = "CONFIRMED"
        self._save_call(record, signature, body)
        return self._call_response(record, record["calls"][body["call_id"]])
