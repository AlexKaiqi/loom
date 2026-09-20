"""Independent black-box CLI driver: never import production Loom Python code."""
from contextlib import closing, contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tarfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/model"))
from provider_fixture import Handler, ProviderFixture, model


def query(work, statement, parameters=()):
    with closing(sqlite3.connect(Path(work) / ".loom/state.sqlite")) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(statement, parameters)]


def assert_no_secrets(root, secrets):
    """Inspect plaintext and nested tar/gzip members without extracting them."""
    examined = 0
    def inspect(raw, label, depth=0):
        nonlocal examined
        examined += 1
        assert all(secret not in raw for secret in secrets if secret), "credential found: " + label
        if depth >= 6:
            return
        try:
            archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:*")
        except (tarfile.TarError, EOFError, OSError):
            return
        with archive:
            for member in archive:
                if member.isfile():
                    with archive.extractfile(member) as stream:
                        inspect(stream.read(), label + "!" + member.name, depth + 1)
    for path in Path(root).rglob("*"):
        if path.is_file():
            inspect(path.read_bytes(), str(path))
    return examined


class ObservedHandler(Handler):
    def openai(self, mode, number):
        if hasattr(self.server, "expected_header"):
            self.server.header_matches.append(self.headers.get("X-Acceptance-Token") == self.server.expected_header)
        if self.server.work:
            effects = query(self.server.work, "SELECT * FROM effects ORDER BY rowid")
            active = [e for e in effects if e["kind"] == "model" and e["status"] == "intent"]
            if len(active) != 1:
                self.server.errors.append("HTTP request without exactly one durable model intent")
            else:
                try:
                    reference = json.loads(active[0]["request"])["request"]
                    raw = (self.server.work / reference["path"]).read_bytes()
                    assert hashlib.sha256(raw).hexdigest() == reference["sha256"]
                    saved = json.loads(raw)
                    assert saved["type"] == "model_request"
                    assert saved["model"]["id"] == self.server.calls[-1]["body"]["model"]
                    assert b"go-acceptance-synthetic-key" not in raw
                except Exception as error:
                    self.server.errors.append("Model request custody failure: " + str(error))
        if mode == "continue" and number == 1:
            self.chunk({"role": "assistant", "reasoning_content": "first native thought", "content": "first answer"})
        else:
            self.chunk({"role": "assistant", "reasoning_content": "native thought", "content": "verified answer"})
        self.chunk(finish="stop", usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10})
        self.event("[DONE]")


@contextmanager
def provider(work=None, mode="text"):
    server = ProviderFixture(mode)
    if mode != "hang":
        server.RequestHandlerClass = ObservedHandler
    server.work = work
    server.errors = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class CLIFixture(unittest.TestCase):
    def setUp(self):
        binary = os.environ.get("LOOM_GO_BINARY")
        if not binary:
            raise RuntimeError("LOOM_GO_BINARY is required: build the Go Runtime before acceptance")
        self.binary = Path(binary).resolve(strict=True)
        evidence = os.environ.get("LOOM_GO_EVIDENCE")
        if evidence:
            self.base = Path(evidence).resolve() / self.id().split(".")[-1]
            self.base.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(prefix="loom-go-acceptance-")
            self.addCleanup(temporary.cleanup)
            self.base = Path(temporary.name)
        self.authority = self.base / "authority.sqlite"
        self.config = self.base / "config.toml"
        self.records = []
        self.env = dict(os.environ)
        self.env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + self.env.get("PATH", "")
        self.env["LOOM_TEST_MODEL_KEY"] = "go-acceptance-synthetic-key"
        self.env["LOOM_TEST_SANDBOX_KEY"] = "go-acceptance-sandbox-key"
        self.env.pop("PYTHONPATH", None)

    def command(self, *args, authority=None):
        return [str(self.binary), "--authority", str(authority or self.authority), "--config", str(self.config), *map(str, args)]

    def call(self, *args, ok=True, authority=None, env=None, timeout=30):
        command = self.command(*args, authority=authority)
        result = subprocess.run(command, capture_output=True, text=True, env=env or self.env, timeout=timeout)
        self.records.append({"argv": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        (self.base / "commands.json").write_text(json.dumps(self.records, indent=2))
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, "invalid operation was accepted: " + result.stdout)
        return result

    def policy(self, name="policy", *, continuation=False, max_turns=2, timeout=4, reject=False, prepare_model=False):
        destination = self.base / name
        destination.mkdir()
        shutil.copyfile(ROOT / "tests/go_acceptance/peer.mjs", destination / "peer.mjs")
        rpc = "./peer.mjs"
        preparation = ('p=>({context:{...p.turn.context,messages:[...p.turn.context.messages,{role:"user",content:"Continue the same objective.",timestamp:1}]}})' if continuation else 'p=>({context:p.turn.context})')
        if prepare_model:
            selected = {"id": "fixture-model", "name": "Fixture", "provider": "fixture", "api": "openai-completions", "reasoning": True,
                "input": ["text", "image"], "contextWindow": 4096, "maxTokens": 128,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}
            preparation = preparation.replace('p=>({context:', 'p=>({model:' + json.dumps(selected) + ',context:')
        source = f'''import {{createWorkerConnection}} from {json.dumps(rpc)};
import {{readFileSync}} from 'node:fs';
import {{execFileSync}} from 'node:child_process';
const c=createWorkerConnection("harness");
const inputs=p=>JSON.parse(execFileSync('sqlite3',['-readonly','-json',p.facts_database,'SELECT fact_id,record_path FROM facts ORDER BY ordinal'],{{encoding:'utf8'}})).filter(f=>p.required_fact_ids.includes(f.fact_id)).map(f=>JSON.parse(readFileSync(f.record_path,'utf8')));
c.onRequest("policy.admit",p=>{str(not reject).lower()});
c.onRequest("policy.start",p=>c.publish(p,{{context:{{systemPrompt:"INDEPENDENT NODE POLICY",messages:[{{role:"user",content:JSON.stringify(inputs(p)),timestamp:p.timestamp}}]}},max_turns:{max_turns},timeout:{timeout}}}));
c.onRequest("policy.continue",p=>{str(continuation).lower()} && p.turn.context.messages.filter(m=>m.role==="assistant").length<2);
c.onRequest("policy.prepare",p=>c.publish(p,({preparation})(p)));
c.listen();
'''
        (destination / "worker.mjs").write_text(source)
        (destination / "manifest.json").write_text(json.dumps({"protocol": 1,
            "events": {"work.objective.set": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}}, "tools": []}))
        return destination

    def create(self, name="work", *, userspace=False, **policy_options):
        policy = self.policy(name + "-policy", **policy_options)
        work = self.base / name
        self.call("create", work, "--harness", policy, "--definition", self.definition(userspace=userspace))
        return work

    def admit(self, work, identity="objective", payload=None, *, ok=True):
        source = self.base / ("payload-" + str(len(self.records)) + ".json")
        source.write_text(json.dumps(payload if payload is not None else {"text": "independent input"}))
        return self.call("admit", work, "work.objective.set", "--payload", source, "--request-id", identity, ok=ok)

    def definition(self, *, userspace=False, native=None, sandbox=True, name="definition.toml", harness_argv=None):
        native = native or {"id": "fixture-model", "name": "Fixture", "provider": "fixture", "api": "openai-completions",
            "reasoning": True, "input": ["text", "image"], "contextWindow": 4096, "maxTokens": 128,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}
        lines = ['schema_version=2','[harness]', 'path="harness"', 'argv='+json.dumps(harness_argv or ['node','{harness}/worker.mjs']), '[surface]', 'path="surface"', '[model]', 'service="model-main"', '[model.parameters]']
        lines.extend(key + "=" + json.dumps(value) for key, value in native.items() if not isinstance(value, dict))
        for key, value in native.items():
            if isinstance(value, dict):
                lines.append('[model.parameters.' + key + ']')
                lines.extend(k + '=' + json.dumps(v) for k, v in value.items())
        if userspace:
            lines.extend(['[userspaces.app]', 'resource="task-files"', 'access="write"', 'delivery="per-tool"'])
        if sandbox:
            lines.extend(['[targets.default]', 'profile="code"', 'userspaces='+json.dumps(['app'] if userspace else [])])
        path = self.base / name
        path.write_text("\n".join(lines) + "\n")
        return path

    def configure(self, server=None, *, worker=None, sandbox_endpoint="http://127.0.0.1:1", model_endpoint=None, headers_env=None):
        worker = worker or [shutil.which("node"), str(ROOT / "services/model/worker.mjs")]
        endpoint = model_endpoint or server.base_url
        lines = ['[models.model-main]', 'api_key_env="LOOM_TEST_MODEL_KEY"', 'worker=' + json.dumps(worker),
            'endpoint=' + json.dumps(endpoint), '[sandboxes.sandbox-main]',
            'api_key_env="LOOM_TEST_SANDBOX_KEY"', 'endpoint=' + json.dumps(sandbox_endpoint)]
        if headers_env:
            lines.append("[models.model-main.headers_env]")
            lines.extend(json.dumps(name) + "=" + json.dumps(env) for name, env in headers_env.items())
        image = json.loads((ROOT / "deploy/opensandbox/versions.json").read_text())["code"]
        lines.extend(['[profiles.code]', 'service="sandbox-main"', 'image='+json.dumps(image), 'profile="code"', 'cpu="1"', 'memory="512Mi"', 'lease_seconds=600', 'request_timeout_seconds=30'])
        facility = os.environ.get("LOOM_TEST_CGROUP_ROOT")
        if not facility:
            raise RuntimeError("execution acceptance requires a real shared Linux Work facility")
        launcher = Path("/usr/local/bin/nsjail")
        state = Path("/tmp/loom-acceptance-execution")
        lines.extend(['[execution]', 'launcher=' + json.dumps(str(launcher)),
                      'launcher_sha256=' + json.dumps(hashlib.sha256(launcher.read_bytes()).hexdigest()),
                      'state_directory=' + json.dumps(str(state)), 'cgroup_root=' + json.dumps(facility),
                      'uid_base=100000', 'uid_count=100000', 'memory_bytes=536870912', 'processes=64', 'cpu_milliseconds=1000'])
        self.config.write_text("\n".join(lines) + "\n")

    def save_provider(self, server):
        (self.base / "provider.json").write_text(json.dumps({"calls": server.calls, "errors": server.errors}, indent=2))
