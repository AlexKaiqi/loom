"""Test-only JSON-RPC peer for the independently deployed Pi worker.

This is an external protocol verifier, not a Runtime implementation. Production
control is in Go. It uses python-lsp-jsonrpc framing/dispatch, sends native Pi
payloads, and deliberately exercises worker fault/cancellation boundaries.
"""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError
import logging
import math
import os
import socket
import json
from pathlib import Path
import subprocess
import threading
from typing import Callable
from uuid import uuid4

from pylsp_jsonrpc.endpoint import Endpoint
class JsonRpcStreamReader:
    def __init__(self, stream): self.stream = stream
    def listen(self, consumer):
        while True:
            line = self.stream.readline(4 * 1024 * 1024 + 2)
            if not line: return
            if len(line) > 4 * 1024 * 1024 + 1 or not line.endswith(b'\n'): raise ValueError('frame limit')
            consumer(json.loads(line))
    def close(self): self.stream.close()

class JsonRpcStreamWriter:
    def __init__(self, stream): self.stream = stream; self.lock = threading.Lock()
    def write(self, value):
        with self.lock:
            self.stream.write(json.dumps(value, separators=(',', ':')).encode() + b'\n')
            self.stream.flush()
    def close(self): self.stream.close()

# The upstream transport's debug and error logs include whole request bodies.
# Model credentials/prompts must never reach an application's configured logger.
_rpc_logger = logging.getLogger("pylsp_jsonrpc")
_rpc_logger.addHandler(logging.NullHandler())
_rpc_logger.propagate = False
_rpc_logger.setLevel(logging.CRITICAL + 1)


class WorkerTransportError(RuntimeError):
    """The worker disappeared or did not settle; never automatically replay."""


class WorkerClient:
    """One disposable Node worker, one request at a time; callbacks may use remote tools."""

    def __init__(self, command: list[str] | None = None):
        if command is None:
            worker = Path(__file__).resolve().parents[2] / "services" / "model" / "worker.mjs"
            if not worker.is_file():
                raise FileNotFoundError(f"Independent worker fixture is missing: {worker}")
            command = ["node", str(worker.resolve())]
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}}
        parent, child = socket.socketpair()
        # The test peer passes one explicit inherited endpoint as FD 3.
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, env=env, pass_fds=(child.fileno(), 3),
                                        preexec_fn=lambda: os.dup2(child.fileno(), 3))
        child.close()
        self._channel = parent
        self._reader = JsonRpcStreamReader(parent.makefile('rb'))
        self._writer = JsonRpcStreamWriter(parent.makefile('wb'))
        self._handlers: dict[str, Callable] = {}
        self._active_id: str | None = None
        self._pending: Future | None = None
        self._lock = threading.RLock()
        self._endpoint = Endpoint(self._handlers, self._writer.write, id_generator=self._request_id)
        self._thread = threading.Thread(target=self._listen, name="worker-test-rpc", daemon=True)
        self._thread.start()
        hello = self._request('session.hello', {'protocol_version': 'loom/1', 'schema_version': 1,
            'role': 'runtime', 'peer_role': 'model', 'max_frame_bytes': 4 * 1024 * 1024,
            'required_capabilities': ['model/1']}, 5)
        if hello.get('protocol_version') != 'loom/1' or hello.get('role') != 'model':
            self.close()
            raise WorkerTransportError('invalid handshake')

    def _request_id(self):
        self._active_id = str(uuid4())
        return self._active_id

    def _listen(self):
        try:
            self._reader.listen(self._endpoint.consume)
        finally:
            pending = self._pending
            if pending is not None and not pending.done():
                pending.set_exception(WorkerTransportError("Model worker closed; outcome may be unknown"))

    def _request(self, method: str, params: dict, timeout: float):
        with self._lock:
            if self.process.poll() is not None:
                raise WorkerTransportError("Model worker is closed")
            future = self._endpoint.request(method, params)
            self._pending = future
            try:
                # Worker enforces actual deadline; this allowance only drains abort/results.
                return future.result(timeout=timeout + 1)
            except TimeoutError as error:
                self.cancel()
                self.close()
                raise WorkerTransportError("Model deadline exceeded; outcome may be unknown") from error
            finally:
                self._pending = None
                self._active_id = None

    @staticmethod
    def _params(context, model, api_key, timeout, options):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        return {"protocol_version": "loom/1", "schema_version": 1, "context": context, "model": model, "apiKey": api_key,
                "timeoutMs": max(1, int(timeout * 1000)), "options": options or {}}

    def complete(self, context: dict, *, model: dict, api_key: str, timeout: float,
                 options: dict | None = None) -> dict:
        return self._request("model.complete", self._params(context, model, api_key, timeout, options), timeout)

    def run(self, context: dict, *, model: dict, api_key: str, tools: list[dict],
            handle_tool: Callable[[str, dict, str], dict], max_turns: int, timeout: float,
            on_event: Callable[[dict], None] | None = None,
            should_continue: Callable[[dict], bool] | None = None,
            prepare_turn: Callable[[dict], dict | None] | None = None,
            options: dict | None = None) -> list[dict]:
        """Run Pi's bounded native loop; acknowledge custody before subsequent effects.

        `on_event` must persist required native messages before returning. Callback
        exceptions stop continuation; the Runtime owns reconciling uncertain effects.
        A prepare_turn context uses the original authorized executable tools.
        """
        with self._lock:
            self._handlers.update({
                "tool.execute": lambda p: {"result": handle_tool(p["name"], p["arguments"], p["toolCallId"])},
                "agent.event": lambda event: {"result": on_event(event) if on_event else None},
                "agent.shouldStop": lambda turn: {"result": not should_continue(turn)},
                "agent.prepareTurn": lambda turn: {"result": prepare_turn(turn)},
            })
            params = self._params({**context, "tools": tools}, model, api_key, timeout, options)
            params.update(maxTurns=max_turns, hooks=(["shouldStop"] if should_continue else []) + (["prepareTurn"] if prepare_turn else []))
            try:
                return self._request("agent.run", params, timeout)
            finally:
                self._handlers.clear()

    def cancel(self):
        """Request cancellation without claiming the provider rolled back its effect."""
        if self._active_id is not None:
            self._endpoint.notify("$/cancelRequest", {"id": self._active_id})

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=0.5)
        self._reader.close()
        self._writer.close()
        self._channel.close()
        self._endpoint.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
