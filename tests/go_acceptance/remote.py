"""Controlled native Pi + Go + real OpenSandbox, with independent API observer."""
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.error
import urllib.request

from support import CLIFixture, ROOT, Handler, ProviderFixture, query, assert_no_secrets


class APIObserver(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def do_DELETE(self):
        self.forward()

    def do_PUT(self):
        self.forward()

    def do_PATCH(self):
        self.forward()

    def forward(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        self.server.requests.append({"method": self.command, "path": self.path})
        if self.command == "POST" and self.path.split("?")[0].rstrip("/").endswith("/sandboxes"):
            effects = query(self.server.work, "SELECT * FROM effects ORDER BY rowid")
            models = [e for e in effects if e["kind"] == "model"]
            if not models or any(e["status"] != "completed" for e in models):
                self.server.errors.append("sandbox create before model custody")
            active = [e for e in effects if e["kind"] == "sandbox.shell" and e["status"] == "intent"]
            if len(active) != 1:
                self.server.errors.append("sandbox create without exactly one durable shell intent")
            for model in models:
                try:
                    ref = json.loads(model["result"])["artifact"]
                    raw = (self.server.work / ref["path"]).read_bytes()
                    assert hashlib.sha256(raw).hexdigest() == ref["sha256"]
                    assert any(p["type"] == "toolCall" for p in json.loads(raw)["message"]["content"])
                except Exception as error:
                    self.server.errors.append("model tool call custody missing: " + str(error))
            self.server.creates += 1
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "connection", "content-length"}}
        request = urllib.request.Request(self.server.upstream + self.path, data=body, headers=headers, method=self.command)
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        data = response.read()
        self.send_response(response.status)
        for name, value in response.headers.items():
            if name.lower() not in {"transfer-encoding", "connection", "content-length", "server", "date"}:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ToolProvider(Handler):
    def openai(self, mode, number):
        effects = query(self.server.work, "SELECT * FROM effects ORDER BY rowid")
        if len([e for e in effects if e["kind"] == "model" and e["status"] == "intent"]) != 1:
            self.server.errors.append("provider dispatch lacks one durable model intent")
        if number == 1:
            self.chunk({"role": "assistant", "reasoning_content": "two independent domains"})
            for index, domain in enumerate(self.server.domains):
                script = """python - <<'PY'
import os,pathlib
assert os.getuid()==65534
assert 'LOOM_TEST_MODEL_KEY' not in os.environ
assert 'LOOM_TEST_SANDBOX_KEY' not in os.environ
assert not pathlib.Path('/var/run/docker.sock').exists()
other='userspace' if pathlib.Path.cwd().name=='surface' else 'surface'
assert not pathlib.Path('/workspace',other).exists()
for hidden in ('/workspace/.loom', '/workspace/work.toml', '/workspace/harness'):
    assert not pathlib.Path(hidden).exists()
try:
    pathlib.Path('../.loom/identity.json').write_text('corrupt')
except (PermissionError, FileNotFoundError):
    pass
else:
    raise AssertionError('remote command changed a control directory')
with pathlib.Path('executions.txt').open('a') as f: f.write('once\\n')
print('independently observed domain')
PY"""
                if domain == "surface":
                    script += "\nprintf 'verified remote report\\n' > report.md\nprintf 'verified remote notes\\n' > notes.md\n"
                self.chunk({"tool_calls": [{"index": index, "id": "call_" + domain, "type": "function", "function": {"name": "shell", "arguments": json.dumps({"target": domain, "script": script, "timeout": 30})}}]})
            self.chunk(finish="tool_calls", usage={"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14})
        else:
            if len([e for e in effects if e["kind"] == "sandbox.shell" and e["status"] == "completed"]) != len(self.server.domains):
                self.server.errors.append("next model dispatch before two durable tool results")
            self.chunk({"role": "assistant", "content": "Both remote domains complete."})
            self.chunk(finish="stop", usage={"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14})
        self.event("[DONE]")


@contextmanager
def serving(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main(args):
    os.environ["LOOM_GO_BINARY"] = str(Path(args.binary).resolve())
    os.environ.pop("LOOM_GO_EVIDENCE", None)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = CLIFixture()
    fixture.setUp()
    fixture.base, fixture.authority, fixture.config = output, output / "authority.sqlite", output / "config.toml"
    fixture.env["LOOM_TEST_SANDBOX_KEY"] = Path(args.sandbox_key_file).read_text().strip()
    domains = ["surface"] if args.surface_only else ["surface", "userspace"]
    policy = fixture.policy(max_turns=1, timeout=120)
    worker = policy / "worker.mjs"
    worker.write_text(worker.read_text().replace('p=>false && p.turn.context.messages.filter(m=>m.role==="assistant").length<2', 'p=>p.turn.message.stopReason === "toolUse"'))
    manifest_file = policy / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["tools"] = [{"name": "shell", "capability": "sandbox.shell", "description": "remote shell", "parameters": {"type": "object", "properties": {"target": {"type": "string", "enum": domains}, "script": {"type": "string"}, "timeout": {"type": "number"}}, "required": ["target", "script"], "additionalProperties": False}}]
    manifest_file.write_text(json.dumps(manifest))
    work, userspace = output / "work", output / "userspace"
    fixture.call("create", work, "--harness", policy, "--definition", fixture.definition(userspace=not args.surface_only))
    userspace.mkdir()
    if not args.surface_only:
        fixture.call("grant", work, userspace)
    fixture.admit(work)
    immutable = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [work / "work.toml", *[p for p in (work / "harness").rglob("*") if p.is_file()]]}
    identity_before = json.loads((work / ".loom/identity.json").read_text())
    api = ThreadingHTTPServer(("127.0.0.1", 0), APIObserver)
    api.upstream, api.work, api.errors, api.creates, api.requests = args.sandbox_endpoint.rstrip("/"), work, [], 0, []
    provider = ProviderFixture()
    provider.RequestHandlerClass = ToolProvider
    provider.work, provider.errors, provider.domains = work, [], domains
    observations = {}
    try:
        with serving(api), serving(provider):
            fixture.configure(provider, sandbox_endpoint=f"http://127.0.0.1:{api.server_port}")
            image = json.loads((ROOT / "deploy/opensandbox/versions.json").read_text())["code"]
            fixture.config.write_text(fixture.config.read_text().replace('image = "fixture-unused"', 'image = ' + json.dumps(image)))
            fixture.call("run", work, ok=False, timeout=180)
            rounds = query(work, "SELECT * FROM rounds")
            assert rounds[0]["state"] == "paused" and rounds[0]["checkpoint"]
            checkpoint = json.loads(rounds[0]["checkpoint"])
            assert sum(m["role"] == "toolResult" for m in checkpoint["plan"]["context"]["messages"]) == len(domains)
            if not args.surface_only:
                assert (userspace / "executions.txt").read_text() == "once\n"
            else:
                assert not (userspace / "executions.txt").exists()
            assert (work / "surface/executions.txt").read_text() == "once\n"
            assert len(provider.calls) == 1 and api.creates == len(domains)
            if args.portable:
                original_round = rounds[0]["id"]
                original_effects = query(work, "SELECT * FROM effects ORDER BY rowid")
                archive = output / "paused-work.tar.gz"
                fixture.call("export", work, archive)
                imported = output / "imported-work"
                fresh_authority = output / "new-host-authority.sqlite"
                fixture.call("import", archive, imported, authority=fresh_authority)
                fixture.call("status", imported, authority=fresh_authority, ok=False)
                fixture.call("register", imported, authority=fresh_authority)
                if not args.surface_only:
                    restored = output / "restored-userspace"
                    fixture.call("restore-userspace", imported, restored, authority=fresh_authority)
                    assert (restored / "executions.txt").read_text() == "once\n"
                    (restored / "executions.txt").write_text("unapproved drift\n")
                    fixture.call("grant", imported, restored, authority=fresh_authority, ok=False)
                    (restored / "executions.txt").write_text("once\n")
                    fixture.call("grant", imported, restored, authority=fresh_authority)
                    shutil.rmtree(userspace)
                    userspace = restored
                shutil.rmtree(work)
                fixture.authority.unlink()
                fixture.config.unlink()
                fixture.authority = fresh_authority
                work = imported
                provider.work = api.work = work
                fixture.configure(provider, sandbox_endpoint=f"http://127.0.0.1:{api.server_port}")
                assert query(work, "SELECT * FROM effects ORDER BY rowid") == original_effects
                observations["migration"] = {"original_round": original_round, "archive": str(archive), "new_work": str(work), "new_authority": str(fresh_authority), "old_work_removed": True, "old_userspace_removed": not args.surface_only}
            result = fixture.call("resume", work, timeout=180)
            assert result["state"] == "completed"
            assert result["round_id"] == rounds[0]["id"]
            assert all(hashlib.sha256((work / path).read_bytes()).hexdigest() == digest for path, digest in immutable.items())
            identity_after = json.loads((work / ".loom/identity.json").read_text())
            assert {k:v for k,v in identity_before.items() if k != "userspace_snapshot_digest"} == {k:v for k,v in identity_after.items() if k != "userspace_snapshot_digest"}
            assert len(provider.calls) == 2 and api.creates == len(domains)
            assert not provider.errors and not api.errors, (provider.errors, api.errors)
            if not args.surface_only:
                assert (userspace / "executions.txt").read_text() == "once\n"
            assert (work / "surface/executions.txt").read_text() == "once\n"
            assert sum(message["role"] == "tool" for message in provider.calls[1]["body"]["messages"]) == len(domains)
            effects = query(work, "SELECT * FROM effects ORDER BY rowid")
            assert [e["kind"] for e in effects] == ["model"] + ["sandbox.shell"] * len(domains) + ["model"]
            for effect in effects:
                assert effect["status"] == "completed"
                if effect["kind"] == "sandbox.shell":
                    receipt = json.loads(effect["result"])["receipt"]
                    assert receipt["exit_code"] == 0 and receipt["released"]
                    assert not subprocess.check_output(["docker", "ps", "-aq", "--filter", "label=loom.operation=" + effect["id"]], text=True).strip()
            assert query(work, "SELECT * FROM pending") == []
            observations.update(result=result, domains=domains, creates=api.creates, provider_calls=provider.calls, effects=effects, checks=["Go and native Pi", "authorized remote domains only", "independent API checks model ACK/tool intent order", "known checkpoint contains toolResults", "explicit resume has zero repeated tool executions", "service operation containers absent"])
            (output / "PASS").write_text("Controlled provider / real Pi / Go / real OpenSandbox confirmed resume passed: " + ",".join(domains) + "\n")
    finally:
        observations.update(provider_errors=provider.errors, api_errors=api.errors, api_requests=api.requests, creates=api.creates, provider_calls=provider.calls, rounds=query(work, "SELECT * FROM rounds"), effects=query(work, "SELECT * FROM effects ORDER BY rowid"))
        (output / "observations.json").write_text(json.dumps(observations, indent=2))
        key = fixture.env["LOOM_TEST_SANDBOX_KEY"].encode()
        observations["secret_scan_objects"] = assert_no_secrets(output, [key, fixture.env["LOOM_TEST_MODEL_KEY"].encode()])
        (output / "observations.json").write_text(json.dumps(observations, indent=2))
        fixture.doCleanups()
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--sandbox-key-file", required=True)
    parser.add_argument("--sandbox-endpoint", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--surface-only", action="store_true")
    parser.add_argument("--portable", action="store_true")
    main(parser.parse_args())
