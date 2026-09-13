"""One real Engine exec stream; bounded observation never starts a replacement."""

import base64, json, select, socket, struct, threading, time
from .errors import ExecutionError, require
from .journal import canonical, digest


class Channel:
    def __init__(self, store, record):
        self.store, self.record = store, record
        self.sock = None
        self.thread = None
        self.parts = {"stdout": bytearray(), "stderr": bytearray()}
        self.offsets = {"stdout": 0, "stderr": 0}
        self.ready = threading.Event()
        self.done = threading.Event()
        self.eof = False
        self.input_closed = False
        self.error = None
        self.stop_thread = None
        self.stop_reason = None
        self.stop_error = None

    def start(self):
        eid = self.record["binding"]["exec_id"]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(self.store.engine.path)
        body = b'{"Detach":false,"Tty":false}'
        header = (
            "POST /v1.48/exec/"
            + eid
            + "/start HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: tcp\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(body))
            + "\r\n\r\n"
        ).encode()
        s.sendall(header + body)
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = s.recv(4096)
            require(chunk, "ENGINE_ERROR", "exec start headers interrupted")
            raw += chunk
            require(len(raw) <= 1048576, "ENGINE_ERROR", "exec headers cap")
        head, raw = raw.split(b"\r\n\r\n", 1)
        status = int(head.split(b" ", 2)[1])
        require(
            status in (101, 200), "ENGINE_ERROR", "exec start status " + str(status)
        )
        s.setblocking(False)
        self.sock = s
        self.thread = threading.Thread(target=self._observe, args=(raw,), daemon=True)
        self.thread.start()

    def _request_stop(self, reason):
        if self.stop_thread is not None:
            return
        self.stop_reason = reason

        def stop():
            try:
                self.store.stop_physical(self.record, reason)
            except Exception as exc:
                self.stop_error = str(exc)

        # Engine kill can wait for the original attached stream to drain.
        # Keep the reader running while this bounded control call completes.
        self.stop_thread = threading.Thread(target=stop, daemon=True)
        self.stop_thread.start()

    def _append(self, stream, data):
        if self.record["result"]["output_state"] == "INCOMPLETE_LIMIT":
            return False
        b = self.record["request"]["budgets"]
        remaining = min(
            b[stream + "_bytes"] - len(self.parts[stream]),
            b["combined_output_bytes"] - sum(map(len, self.parts.values())),
        )
        accepted = data[: max(remaining, 0)]
        if accepted and self.record["request"]["schema_version"] == 2:
            path = self.store._stream_path(self.record, stream)
            if self.store.slots:
                self.store.slots.guard_write(self.record, path, len(accepted))
            with path.open("ab") as output:
                output.write(accepted)
                output.flush()
                __import__("os").fsync(output.fileno())
        self.parts[stream].extend(accepted)
        if len(data) > remaining:
            with self.store.journal.lock:
                self.record["result"].update(
                    output_state="INCOMPLETE_LIMIT", reason="OUTPUT_LIMIT"
                )
                self.store.journal.put(self.record)
            self._request_stop("OUTPUT_LIMIT")
            return False
        return True

    def _frames(self, raw):
        while len(raw) >= 8:
            stream = raw[0]
            require(
                stream in (1, 2) and raw[1:4] == b"\0\0\0",
                "ENGINE_ERROR",
                "invalid Engine stream header",
            )
            n = struct.unpack(">I", raw[4:8])[0]
            require(n <= 1048576, "ENGINE_ERROR", "Engine stream frame cap")
            if len(raw) < n + 8:
                break
            self._append("stdout" if stream == 1 else "stderr", raw[8 : 8 + n])
            raw = raw[8 + n :]
        return raw

    def _memory_limited(self):
        original = self.store.engine.inspect(self.record["binding"]["container_id"])
        require(
            original is not None
            and original["Id"] == self.record["binding"]["container_id"],
            "UNKNOWN",
            "original resource environment unavailable",
        )
        limited = original["State"].get("OOMKilled") is True
        if limited and "memory_witness" not in self.record["artifacts"]:
            witness = {
                "execution_id": self.record["binding"]["execution_id"],
                "object_generation": self.record["binding"]["object_generation"],
                "engine_container": original,
            }
            with self.store.journal.lock:
                self.record["artifacts"]["memory_witness"] = self.store.journal.blob(
                    self.record["binding"]["execution_id"],
                    "memory-witness",
                    canonical(witness),
                )
                self.store.journal.put(self.record)
        return limited

    def _observe(self, raw):
        last = time.monotonic()
        elapsed = 0
        last_stats = 0
        resource_reason = None
        try:
            while True:
                now = time.monotonic()
                state = self.record["result"]["execution_state"]
                elapsed += now - last if state != "FROZEN" else 0
                last = now
                if state != "FROZEN" and now - last_stats > 0.2:
                    stats = self.store.engine.call(
                        "GET",
                        "/containers/"
                        + self.record["binding"]["container_id"]
                        + "/stats?stream=false&one-shot=true",
                        missing=True,
                    )
                    last_stats = now
                    if stats:
                        if self._memory_limited():
                            resource_reason = "MEMORY_LIMIT"
                        elif stats.get("memory_stats", {}).get("failcnt", 0) > 0:
                            resource_reason = "MEMORY_LIMIT"
                        if (
                            stats.get("pids_stats", {}).get("current", 0)
                            >= self.record["request"]["budgets"]["pids"]
                        ):
                            resource_reason = "PIDS_LIMIT"
                if (
                    state != "FROZEN"
                    and elapsed >= self.record["request"]["budgets"]["deadline_seconds"]
                ):
                    self._request_stop(resource_reason or "DEADLINE")
                if raw:
                    raw = self._frames(raw)
                self.ready.set()
                if self.eof:
                    # EOF may arrive before the next periodic resource sample.
                    # The terminal original-object fact must still be checked.
                    if self._memory_limited():
                        resource_reason = "MEMORY_LIMIT"
                    if self.stop_thread is not None and self.stop_thread.is_alive():
                        time.sleep(0.02)
                        continue
                    if self.stop_error:
                        raise ExecutionError("ENGINE_UNAVAILABLE", self.stop_error)
                    if (
                        not resource_reason
                        or not self.store.engine.inspect(
                            self.record["binding"]["container_id"]
                        )["State"]["Running"]
                    ):
                        break
                    time.sleep(0.02)
                    continue
                readable, _, _ = select.select([self.sock], [], [], 0.02)
                if readable:
                    chunk = self.sock.recv(65536)
                    if not chunk:
                        self.eof = True
                    else:
                        raw += chunk
                if self.eof and raw:
                    raise ExecutionError(
                        "ENGINE_ERROR", "exec stream interrupted mid-frame"
                    )
            self.store.complete_observation(self, resource_reason)
        except Exception as exc:
            self.error = str(exc)
            self.store.observation_failed(self, str(exc))
        finally:
            self.ready.set()
            self.done.set()
            if self.sock:
                self.sock.close()

    def write(self, data, maximum=65536, progress=None):
        require(
            self.sock is not None and not self.input_closed and not self.eof,
            "CHANNEL_CLOSED",
            "original stdin unavailable",
        )
        require(
            self.record["result"]["execution_state"] != "FROZEN",
            "FROZEN",
            "input cannot be delivered while frozen",
        )
        require(len(data) <= maximum, "INVALID_REQUEST", "bounded stdin chunk")
        end = time.monotonic() + 2
        view = memoryview(data)
        while view:
            require(
                time.monotonic() < end,
                "CHANNEL_BLOCKED",
                "bounded stdin delivery deadline",
            )
            _, ready, _ = select.select([], [self.sock], [], 0.02)
            if ready:
                try:
                    n = self.sock.send(view[:65536])
                except (BrokenPipeError, ConnectionError, OSError) as exc:
                    raise ExecutionError(
                        "INCOMPLETE_OBSERVATION", "original stdin write interrupted"
                    ) from exc
                require(
                    n > 0, "INCOMPLETE_OBSERVATION", "original stdin made no progress"
                )
                view = view[n:]
                if progress:
                    progress(len(data) - len(view))

    def close_input(self):
        if not self.input_closed and self.sock and not self.eof:
            self.sock.shutdown(socket.SHUT_WR)
            self.input_closed = True

    def read(self, stream, maximum):
        require(
            stream in self.parts and type(maximum) is int and 0 < maximum <= 65536,
            "INVALID_REQUEST",
            "bounded stream selection",
        )
        end = time.monotonic() + 2
        while (
            len(self.parts[stream]) == self.offsets[stream]
            and not self.done.is_set()
            and time.monotonic() < end
        ):
            time.sleep(0.005)
        start = self.offsets[stream]
        data = bytes(self.parts[stream][start : start + maximum])
        self.offsets[stream] += len(data)
        return {
            "data_base64": base64.b64encode(data).decode(),
            "eof": self.eof and self.offsets[stream] == len(self.parts[stream]),
        }
