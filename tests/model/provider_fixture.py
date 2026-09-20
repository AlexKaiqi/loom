"""Controlled HTTP/SSE peer. Never substitutes the actual Pi provider adapters."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time


class ProviderFixture(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, mode="rich"):
        super().__init__(("127.0.0.1", 0), Handler)
        self.mode = mode
        self.calls = []
        self.received = threading.Event()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server_port}/v1"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        # Deliberately do not retain authorization headers in any evidence.
        self.server.calls.append({"path": self.path, "body": body})
        self.server.received.set()
        mode = self.server.mode
        if mode in ("429", "500"):
            data = json.dumps({"error": {"message": "controlled failure"}}).encode()
            self.send_response(int(mode))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        if mode == "hang":
            time.sleep(3)
            self.close_connection = True
            return
        try:
            if mode == "anthropic":
                self.anthropic()
            else:
                self.openai(mode, len(self.server.calls))
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def event(self, data, kind=None):
        text = f"event: {kind}\n" if kind else ""
        text += "data: " + (data if isinstance(data, str) else json.dumps(data)) + "\n\n"
        self.wfile.write(text.encode())
        self.wfile.flush()

    def chunk(self, delta=None, finish=None, usage=None):
        value = {"id": "response-fixture", "object": "chat.completion.chunk", "created": 1,
                 "model": "fixture-model", "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}
        if usage:
            value["usage"] = usage
        self.event(value)

    def openai(self, mode, number):
        self.chunk({"role": "assistant", "reasoning_content": "considered"})
        self.chunk({"content": "hello"})
        if mode in ("rich", "loop", "invalid", "length") and (mode != "loop" or number == 1):
            argument = '{"command":' if mode != "invalid" else '{"command":'
            self.chunk({"tool_calls": [{"index": 0, "id": "call_fixture", "type": "function",
                        "function": {"name": "shell", "arguments": argument}}]})
            self.chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"echo ok"}' if mode != "invalid" else '{}}'}}]})
            finish = "length" if mode == "length" else "tool_calls"
        else:
            finish = "stop"
        if mode == "truncated":
            return
        self.chunk(finish=finish, usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10})
        self.event("[DONE]")

    def anthropic(self):
        self.event({"type": "message_start", "message": {"id": "msg_fixture", "type": "message", "role": "assistant",
                   "model": "fixture-model", "content": [], "stop_reason": None, "stop_sequence": None,
                   "usage": {"input_tokens": 7, "output_tokens": 0}}}, "message_start")
        self.event({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, "content_block_start")
        self.event({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "bonjour"}}, "content_block_delta")
        self.event({"type": "content_block_stop", "index": 0}, "content_block_stop")
        self.event({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 3}}, "message_delta")
        self.event({"type": "message_stop"}, "message_stop")


@contextmanager
def provider(mode="rich"):
    server = ProviderFixture(mode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def model(server, api="openai-completions"):
    return {"id": "fixture-model", "name": "Fixture", "provider": "fixture", "api": api,
            "baseUrl": server.base_url.removesuffix("/v1") if api == "anthropic-messages" else server.base_url, "reasoning": True, "input": ["text", "image"],
            "contextWindow": 4096, "maxTokens": 128,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}


TOOL = {"name": "shell", "description": "Run a command in an authorized remote environment",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}}
CONTEXT = {"systemPrompt": "Fixture system", "messages": [{"role": "user", "content": "test", "timestamp": 1}]}
