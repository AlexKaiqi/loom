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
            active = [e for e in effects if e["kind"] == "tool.exec" and e["status"] == "intent"]
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


BASH_TOOL = {"name": "bash", "capability": "tool.exec", "description": "Run ordinary Bash in Work or a remote Sandbox Target. Work starts at /work; task files start at /workspace/task/app.", "parameters": {"type": "object", "properties": {"environment": {"type": "string", "enum": ["work", "sandbox"]}, "target": {"type": "string"}, "script": {"type": "string"}, "timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": 30}}, "required": ["environment", "script"], "additionalProperties": False}}


class ToolProvider(Handler):
    def openai(self, mode, number):
        effects = query(self.server.work, "SELECT * FROM effects ORDER BY rowid")
        if len([e for e in effects if e["kind"] == "model" and e["status"] == "intent"]) != 1:
            self.server.errors.append("provider dispatch lacks one durable model intent")
        if number == 1:
            self.chunk({"role": "assistant", "reasoning_content": "two independent environments"})
            for index, domain in enumerate(self.server.domains):
                script = """python3 - <<'SCRIPT'
import os,pathlib
assert 'LOOM_TEST_MODEL_KEY' not in os.environ
assert 'LOOM_TEST_SANDBOX_KEY' not in os.environ
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not pathlib.Path('/work/.loom').exists()
"""
                if domain == "work":
                    script += """assert os.getuid() >= 100000
assert pathlib.Path.cwd() == pathlib.Path('/work')
assert pathlib.Path('/work/work.toml').is_file()
assert pathlib.Path('/harness/manifest.json').is_file()
assert not pathlib.Path('/workspace/task').exists()
p = pathlib.Path('surface/executions.txt')
pathlib.Path('surface/report.md').write_text('verified Work report\\n')
pathlib.Path('surface/notes.md').write_text('verified Work notes\\n')
"""
                else:
                    script += """assert os.getuid() == 65534
assert pathlib.Path.cwd() == pathlib.Path('/workspace/task')
assert not pathlib.Path('/work').exists()
assert not pathlib.Path('/harness').exists()
p = pathlib.Path('app/executions.txt')
"""
                script += "with p.open('a') as f: f.write('once\\n')\nprint('independently observed environment')\nSCRIPT"
                arguments = {"environment": domain, "script": script, "timeout": 30}
                if domain == "sandbox":
                    arguments["target"] = "default"
                self.chunk({"tool_calls": [{"index": index, "id": "call_" + domain, "type": "function", "function": {"name": "bash", "arguments": json.dumps(arguments)}}]})
            self.chunk(finish="tool_calls", usage={"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14})
        else:
            if len([e for e in effects if e["kind"] == "tool.exec" and e["status"] == "completed"]) != len(self.server.domains):
                self.server.errors.append("next model dispatch before durable tool results")
            self.chunk({"role": "assistant", "content": "Both environments complete."})
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
    domains = ["work"] if args.work_only else ["work", "sandbox"]
    policy = fixture.policy(max_turns=1, timeout=120)
    worker = policy / "worker.mjs"
    worker.write_text(worker.read_text().replace('p=>false && p.turn.context.messages.filter(m=>m.role==="assistant").length<2', 'p=>p.turn.message.stopReason === "toolUse"'))
    manifest_file = policy / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["tools"] = [BASH_TOOL]
    manifest_file.write_text(json.dumps(manifest))
    work, userspace = output / "work", output / "userspace"
    definition = fixture.definition(userspace=not args.work_only)
    definition.write_text(definition.read_text().replace("contextWindow=4096", "contextWindow=32768"))
    fixture.call("create", work, "--harness", policy, "--definition", definition)
    userspace.mkdir()
    if not args.work_only:
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
            assert rounds[0]["state"] == "ready" and rounds[0]["checkpoint"]
            checkpoint = json.loads(rounds[0]["checkpoint"])
            assert sum(m["role"] == "toolResult" for m in checkpoint["plan"]["context"]["messages"]) == len(domains)
            if not args.work_only:
                assert not (userspace / "executions.txt").exists()
                saved = output / "before-resume-copy"
                fixture.call("restore-resource", work, "app", saved, "--target", "default")
                assert (saved / "executions.txt").read_text() == "once\n"
            else:
                assert not (userspace / "executions.txt").exists()
            assert (work / "surface/executions.txt").read_text() == "once\n"
            assert len(provider.calls) == 1 and api.creates == (0 if args.work_only else 1)
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
                if not args.work_only:
                    restored = output / "restored-userspace"
                    fixture.call("restore-resource", imported, "app", restored, "--target", "default", authority=fresh_authority)
                    assert (restored / "executions.txt").read_text() == "once\n"
                    fixture.call("grant", imported, imported / "surface", authority=fresh_authority, ok=False)
                    (restored / "executions.txt").write_text("new host shared project\n")
                    fixture.call("grant", imported, restored, authority=fresh_authority)
                    exact = output / "imported-independent-copy"
                    fixture.call("restore-resource", imported, "app", exact, "--target", "default", authority=fresh_authority)
                    assert (exact / "executions.txt").read_text() == "once\n"
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
                observations["migration"] = {"original_round": original_round, "archive": str(archive), "new_work": str(work), "new_authority": str(fresh_authority), "old_work_removed": True, "old_userspace_removed": not args.work_only}
            result = fixture.call("resume", work, timeout=180)
            assert result["state"] == "handed_off"
            assert result["round_id"] == rounds[0]["id"]
            assert all(hashlib.sha256((work / path).read_bytes()).hexdigest() == digest for path, digest in immutable.items())
            identity_after = json.loads((work / ".loom/identity.json").read_text())
            assert identity_before == identity_after
            assert len(provider.calls) == 2 and api.creates == (0 if args.work_only else 1)
            assert not provider.errors and not api.errors, (provider.errors, api.errors)
            if not args.work_only:
                saved = output / "after-resume-copy"
                fixture.call("restore-resource", work, "app", saved, "--target", "default")
                assert (saved / "executions.txt").read_text() == "once\n"
                if args.portable:
                    assert (userspace / "executions.txt").read_text() == "new host shared project\n"
                else:
                    assert not (userspace / "executions.txt").exists()
            assert (work / "surface/executions.txt").read_text() == "once\n"
            assert sum(message["role"] == "tool" for message in provider.calls[1]["body"]["messages"]) == len(domains)
            effects = query(work, "SELECT * FROM effects ORDER BY rowid")
            assert [e["kind"] for e in effects] == ["model"] + ["tool.exec"] * len(domains) + ["model"]
            for effect in effects:
                assert effect["status"] == "completed"
                if effect["kind"] == "tool.exec" and json.loads(effect["request"])["environment"] == "sandbox":
                    receipt = json.loads(effect["result"])["receipt"]
                    assert receipt["exit_code"] == 0 and receipt["released"]
                    assert not subprocess.check_output(["docker", "ps", "-aq", "--filter", "label=loom.operation=" + effect["id"]], text=True).strip()
            assert query(work, "SELECT * FROM pending") == []
            observations.update(result=result, domains=domains, creates=api.creates, provider_calls=provider.calls, effects=effects, checks=["Go and native Pi", "distinct Work and remote Sandbox identities", "independent API checks model ACK/tool intent order", "known checkpoint contains toolResults", "explicit resume has zero repeated tool executions", "service operation containers absent"])
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
    parser.add_argument("--work-only", action="store_true")
    parser.add_argument("--portable", action="store_true")
    main(parser.parse_args())
