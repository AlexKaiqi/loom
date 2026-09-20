"""Independent installed-user acceptance, with real Pi and real OpenSandbox.

Run only against an operator-provided service. Outputs never include credentials,
private host TOML or authority databases; those remain under --private-dir.
"""
import argparse
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import hashlib
import json
import os
import pty
import select
import time
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/go_acceptance"))
from support import Handler, ProviderFixture, query, assert_no_secrets
from remote import APIObserver, serving

ARCHIVE_CANARY = "OLD_ARCHIVE_BODY_MUST_NOT_BE_PROJECTED_34c270f"
PLAN_CANARY = "CURRENT_PLAN_VISIBLE_69b1b07"
MODEL_KEY = "onboarding-model-secret-361562b94"
TASK = "读取 Userspace 的 numbers.txt，计算总和；更新 Surface 的计划、报告并归档过程。"


class UserProvider(Handler):
    def openai(self, mode, number):
        effects = query(self.server.work, "SELECT * FROM effects ORDER BY rowid")
        active = [e for e in effects if e["kind"] == "model" and e["status"] == "intent"]
        if len(active) != 1:
            self.server.errors.append("provider request without exactly one saved model intent")
        else:
            ref = json.loads(active[0]["request"])["request"]
            raw = (self.server.work / ref["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                self.server.errors.append("provider request artifact digest differs")
        if self.server.mode == "truncated":
            self.chunk({"role": "assistant", "content": "unconfirmed"})
            return
        self.chunk({"role": "assistant"})
        if self.server.mode == "tools" and number <= 4:
            self.chunk({"content": "NATIVE_ORIGINAL_TURN_" + str(number) + "_" + "e" * 12000})
        if self.server.mode == "tools" and number == 1:
            scripts = {
                "userspace": """python - <<'PY'
import os,pathlib
assert os.getuid()==65534
assert 'LOOM_TEST_MODEL_KEY' not in os.environ
assert 'LOOM_TEST_SANDBOX_KEY' not in os.environ
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not pathlib.Path('/workspace/surface').exists()
assert not pathlib.Path('/workspace/.loom').exists()
values=[int(v) for v in pathlib.Path('numbers.txt').read_text().split()]
assert values==[17,23]
pathlib.Path('sum.txt').write_text(str(sum(values))+'\\n')
print(sum(values))
PY""",
                "surface": """python - <<'PY'
import os,pathlib
assert os.getuid()==65534
assert not pathlib.Path('/workspace/userspace').exists()
assert not pathlib.Path('/workspace/.loom').exists()
assert not pathlib.Path('../harness').exists()
for p in ('/workspace/work.toml','/workspace/.loom/identity.json'):
    assert not pathlib.Path(p).exists()
assert pathlib.Path('archive/old.md').read_text()=='OLD_ARCHIVE_BODY_MUST_NOT_BE_PROJECTED_34c270f\\n'
pathlib.Path('report.md').write_text('# Result\\n17 + 23 = 40\\n')
pathlib.Path('plan.md').write_text('# Plan\\n- [x] Compute 17 + 23\\n- [x] Preserve archived evidence\\n')
pathlib.Path('notes.md').write_text('Source: archive/new.md\\n')
pathlib.Path('archive/new.md').write_text('ARCHIVED_REMOTE_DETAIL_NOT_AUTO_PROJECTED_7926\\n')
print('surface files preserved and updated')
PY""",
            }
            for index, (domain, script) in enumerate(scripts.items()):
                self.chunk({"tool_calls": [{"index": index, "id": "onboarding_" + domain,
                    "type": "function", "function": {"name": "shell", "arguments": json.dumps({"target": domain, "script": script, "timeout": 30})}}]})
            self.chunk(finish="tool_calls", usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30})
        elif self.server.mode == "tools" and 2 <= number <= 4:
            self.chunk({"tool_calls": [{"index": 0, "id": "archive_turn_" + str(number), "type": "function",
                "function": {"name": "shell", "arguments": json.dumps({"target": "surface", "script": "printf 'verified archive working turn\\n'", "timeout": 30})}}]})
            self.chunk(finish="tool_calls", usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30})
        else:
            self.chunk({"content": "已完成：17 + 23 = 40。计划与归档已保存。"})
            self.chunk(finish="stop", usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30})
        self.event("[DONE]")


class InstalledUser:
    def __init__(self, args):
        self.output = Path(args.output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.private = Path(args.private_dir).resolve()
        self.private.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.home = self.private / "home"
        self.home.mkdir()
        self.prefix = self.private / "installed prefix"
        self.cwd = self.private / "unrelated cwd"
        self.cwd.mkdir()
        self.binary = self.prefix / "bin/loom"
        self.commands = []
        self.checks = []
        self.env = dict(os.environ)
        self.env["HOME"] = str(self.home)
        self.env["PATH"] = os.pathsep.join(p for p in self.env["PATH"].split(os.pathsep) if str(ROOT) not in p and "loom-onboarding-private" not in p)
        self.env.pop("PYTHONPATH", None)
        self.env.pop("LOOM_INSTALL_ROOT", None)
        self.env["LOOM_TEST_MODEL_KEY"] = MODEL_KEY
        self.env["LOOM_TEST_SANDBOX_KEY"] = Path(args.sandbox_key_file).read_text().strip()
        self.config = self.home / ".config/loom/config.toml"
        self.authority = self.home / ".local/state/loom/authority.sqlite"
        self.work = self.output / "work"
        self.userspace = self.private / "task files"
        self.userspace.mkdir()
        (self.userspace / "numbers.txt").write_text("17\n23\n")
        self.args = args

    def command(self, *args, ok=True, env=None, cwd=None, timeout=180):
        cmd = [str(self.binary), *map(str, args)]
        result = subprocess.run(cmd, cwd=cwd or self.cwd, env=env or self.env, text=True, capture_output=True, timeout=timeout)
        self.commands.append({"argv": cmd, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        (self.output / "commands.json").write_text(json.dumps(self.commands, ensure_ascii=False, indent=2))
        assert (result.returncode == 0) == ok, result.stderr + result.stdout
        return result

    def install(self):
        before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for base in ("runtime", "services/model", "harnesses", "deploy", "scripts", "docs/contracts", "tests/onboarding", "tests/model", "tests/go_acceptance", "tests/harness", "tests/install")
                  for p in (ROOT / base).rglob("*") if p.is_file() and not any(part in {"node_modules", "bin", "__pycache__"} for part in p.parts)}
        for name in ("SPEC.md", "AGENTS.md", "install.sh"):
            before[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        (self.output / "source-hashes.json").write_text(json.dumps(before, sort_keys=True, indent=2))
        result = subprocess.run([str(ROOT / "install.sh"), "--prefix", str(self.prefix)], cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=300)
        (self.output / "install.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
        self.command("--help")
        self.checks.append("fresh installation in prefix with spaces from unrelated cwd; no manual Python env or worker path")

    def setup(self, provider, api, *, ok=True):
        return self.command("setup", "--provider", "groq", "--model", "llama-3.1-8b-instant",
                            "--model-endpoint", provider.base_url, "--sandbox-endpoint", f"http://127.0.0.1:{api.server_port}",
                            "--model-key-env", "LOOM_TEST_MODEL_KEY", "--sandbox-key-env", "LOOM_TEST_SANDBOX_KEY", ok=ok)

    def interactive_setup(self, provider, api):
        target = self.private / "interactive/config.toml"
        master, slave = pty.openpty()
        process = subprocess.Popen([str(self.binary), "--config", str(target), "setup", "--model-endpoint", provider.base_url],
                                   stdin=slave, stdout=slave, stderr=slave, cwd=self.cwd, env=self.env, close_fds=True)
        os.close(slave)
        transcript = bytearray()
        def until(marker):
            deadline = time.monotonic() + 30
            while marker not in transcript:
                assert time.monotonic() < deadline, "interactive setup prompt timeout"
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        raw = os.read(master, 65536)
                    except OSError:
                        raw = b""
                    assert raw, "interactive setup exited before prompt"
                    transcript.extend(raw)
        try:
            for prompt, answer in (
                (b"Provider (--provider): ", "groq"),
                (b"Model (--model): ", "llama-3.1-8b-instant"),
                (b"OpenSandbox endpoint (--sandbox-endpoint): ", f"http://127.0.0.1:{api.server_port}"),
                (b"model API key (hidden): ", MODEL_KEY),
                (b"sandbox API key (hidden): ", self.env["LOOM_TEST_SANDBOX_KEY"]),
            ):
                until(prompt)
                time.sleep(0.05)
                os.write(master, answer.encode() + b"\n")
            while process.poll() is None:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        transcript.extend(os.read(master, 65536))
                    except OSError:
                        break
            assert process.wait(timeout=30) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            assert MODEL_KEY.encode() not in transcript and self.env["LOOM_TEST_SANDBOX_KEY"].encode() not in transcript
            (self.output / "interactive-setup.txt").write_bytes(transcript)
        config = tomllib.loads(target.read_text())
        for name, key in (("model", MODEL_KEY), ("sandbox", self.env["LOOM_TEST_SANDBOX_KEY"])):
            secret = target.parent / "secrets" / (name + ".key")
            assert secret.read_text() == key and secret.stat().st_mode & 0o777 == 0o600
        assert "api_key_file" in config["models"]["primary"]
        self.checks.append("real terminal setup offers Pi catalog, hides key input and persists only private 0600 credential files")

    def run(self):
        self.install()
        provider = ProviderFixture("tools")
        provider.RequestHandlerClass = UserProvider
        provider.work, provider.errors = self.work, []
        api = ThreadingHTTPServer(("127.0.0.1", 0), APIObserver)
        api.upstream, api.work, api.errors, api.creates, api.requests = self.args.sandbox_endpoint.rstrip("/"), self.work, [], 0, []
        try:
            with serving(provider), serving(api):
                self.interactive_setup(provider, api)
                self.setup(provider, api)
                config_before = self.config.read_bytes()
                config = tomllib.loads(config_before.decode())
                worker = config["models"]["primary"].get("worker", [])
                if worker:
                    assert worker == ["loom-model"] or (str(self.prefix) in json.dumps(worker) and str(ROOT) not in json.dumps(worker)), "setup must resolve installed worker without user-written checkout paths"
                assert not any(s in config_before for s in (MODEL_KEY.encode(), self.env["LOOM_TEST_SANDBOX_KEY"].encode()))
                self.setup(provider, api, ok=False)
                assert self.config.read_bytes() == config_before
                self.checks.append("setup creates host-only routing plus default declaration without secrets; rerun preserves existing config")
                self.command("new", self.work, "--userspace", self.userspace)
                for file in ("plan.md", "report.md", "notes.md"):
                    assert (self.work / "surface" / file).is_file(), file
                (self.work / "surface/archive").mkdir(exist_ok=True)
                (self.work / "surface/archive/old.md").write_text(ARCHIVE_CANARY + "\n")
                (self.work / "surface/plan.md").write_text("# Plan\n" + PLAN_CANARY + "\n")
                self.command("status", cwd=self.work)
                denied_env = dict(self.env)
                denied_env.pop("LOOM_TEST_MODEL_KEY")
                self.command("ask", self.work, TASK, "--request-id", "natural-1", ok=False, env=denied_env)
                assert len(query(self.work, "SELECT * FROM events")) == 1
                assert len(query(self.work, "SELECT * FROM pending")) == 1
                assert not query(self.work, "SELECT * FROM effects")
                assert not provider.calls and not api.requests
                self.checks.append("missing model key preserves natural-language admission/pending, creates no remote effect")
                result = self.command("ask", self.work, TASK, "--request-id", "natural-1")
                assert "40" in result.stdout
                assert len(provider.calls) == 5 and api.creates == 5
                assert provider.calls[0]["body"]["max_completion_tokens"] == 4096
                first_prompt = json.dumps(provider.calls[0]["body"]["messages"], ensure_ascii=False)
                assert PLAN_CANARY in first_prompt
                assert ARCHIVE_CANARY not in first_prompt
                assert "archive/index.jsonl" in first_prompt
                assert (self.userspace / "sum.txt").read_text() == "40\n"
                assert (self.work / "surface/report.md").read_text() == "# Result\n17 + 23 = 40\n"
                assert (self.work / "surface/archive/old.md").read_text() == ARCHIVE_CANARY + "\n"
                assert (self.work / "surface/archive/new.md").read_text() == "ARCHIVED_REMOTE_DETAIL_NOT_AUTO_PROJECTED_7926\n"
                assert not provider.errors and not api.errors, (provider.errors, api.errors)
                effects = query(self.work, "SELECT * FROM effects ORDER BY rowid")
                assert sum(e["kind"] == "model" for e in effects) == 5
                assert sum(e["kind"] == "sandbox.shell" for e in effects) == 5
                assert all(e["status"] == "completed" for e in effects)
                assert not query(self.work, "SELECT * FROM pending")
                for effect in effects:
                    if effect["kind"] == "sandbox.shell":
                        receipt = json.loads(effect["result"])["receipt"]
                        assert receipt["exit_code"] == 0 and receipt["released"]
                        assert not subprocess.check_output(["docker", "ps", "-aq", "--filter", "label=loom.operation=" + effect["id"]], text=True).strip()
                contexts = [json.loads(p.read_text()) for p in (self.work / "surface/archive").glob("*.json")]
                native_archives = [c for c in contexts if c.get("kind") == "native-context"]
                assert native_archives and any("NATIVE_ORIGINAL_TURN_1_" in json.dumps(c["original"]) for c in native_archives)
                assert any("LOOM_KERNEL_ARCHIVE" in json.dumps(c["body"]["messages"]) for c in provider.calls[1:])
                self.checks.append("native prepare hook archived full long Pi context before smaller provider projection; original first turn directly recovered")
                self.checks.append("real Pi and two real isolated Sandbox domains; direct data=40, plan/report/archive bytes, durable custody and remote release")
                self.command("ask", self.work, TASK, "--request-id", "natural-1")
                assert len(provider.calls) == 5 and len(query(self.work, "SELECT * FROM events")) == 1
                self.command("ask", self.work, "changed content", "--request-id", "natural-1", ok=False)
                assert len(provider.calls) == 5 and len(query(self.work, "SELECT * FROM events")) == 1
                self.checks.append("same request retries are idempotent and conflicting text rejects without new provider calls")
                provider.mode = "text"
                self.command("ask", "检查已保存的计划", "--request-id", "natural-2", cwd=self.work)
                latest_prompt = json.dumps(provider.calls[-1]["body"]["messages"], ensure_ascii=False)
                assert "Compute 17 + 23" in latest_prompt
                assert "archive/index.jsonl" in latest_prompt
                assert "ARCHIVED_REMOTE_DETAIL_NOT_AUTO_PROJECTED_7926" not in latest_prompt
                self.checks.append("cwd shorthand works; later Round sees current plan and discoverable archived refs without archive bodies")
                local_work = self.output / "local-rejection-work"
                local_tasks = self.private / "local-rejection-task-files"
                local_tasks.mkdir()
                self.command("new", local_work, "--userspace", local_tasks)
                before_http = (len(provider.calls), len(api.requests))
                rejected = self.command("ask", local_work, "Explicit user input too large: " + "z" * 50000, "--request-id", "local-reject-1", ok=False)
                assert "before model/tool dispatch" in rejected.stderr and "unknown" not in rejected.stderr
                assert not query(local_work, "SELECT * FROM effects")
                assert query(local_work, "SELECT state FROM rounds") == [{"state": "rejected"}]
                assert len(query(local_work, "SELECT * FROM pending")) == 1
                assert (len(provider.calls), len(api.requests)) == before_http
                self.checks.append("oversized policy input fails locally with accurate pre-dispatch guidance, pending intact and zero HTTP/effects")
                unknown_work = self.output / "unknown-work"
                unknown_tasks = self.private / "unknown-task-files"
                unknown_tasks.mkdir()
                self.command("new", unknown_work, "--userspace", unknown_tasks)
                provider.work = unknown_work
                provider.mode = "truncated"
                self.command("ask", unknown_work, "retain unknown responsibility", "--request-id", "unknown-1", ok=False)
                count = len(provider.calls)
                unknown_effects = query(unknown_work, "SELECT * FROM effects")
                assert len(unknown_effects) == 1
                interrupted_round = query(unknown_work, "SELECT * FROM rounds")[0]
                assert interrupted_round["state"] == "paused" and interrupted_round["checkpoint"] is None
                native_error = json.loads(unknown_effects[0]["result"])
                assert native_error["stopReason"] == "error"
                native_bytes = (unknown_work / native_error["artifact"]["path"]).read_bytes()
                assert hashlib.sha256(native_bytes).hexdigest() == native_error["artifact"]["sha256"]
                assert json.loads(native_bytes)["message"]["stopReason"] == "error"
                queued = self.command("ask", unknown_work, "retain unknown responsibility", "--request-id", "unknown-1")
                assert "queued" in queued.stdout.lower()
                for operation in (("run", unknown_work), ("resume", unknown_work)):
                    self.command(*operation, ok=False)
                assert len(provider.calls) == count
                assert query(unknown_work, "SELECT * FROM pending")
                self.checks.append("truncated provider result is preserved as native error custody; paused Round without checkpoint never automatically redispatches")
                report_version = subprocess.check_output(["git", "--git-dir", str(self.work / ".loom/versions.git"), "show", "HEAD:report.md"])
                assert report_version == (self.work / "surface/report.md").read_bytes()
                self.command("export", self.work, self.output / "work.tar.gz")
                copied = self.output / "copied-work"
                shutil.copytree(self.work, copied)
                self.command("status", copied, ok=False)
                self.checks.append("copied Work carries no host authority")
        finally:
            observations = {"checks": self.checks, "provider_calls": provider.calls, "provider_errors": provider.errors,
                "api_requests": api.requests, "api_errors": api.errors, "sandbox_creates": api.creates,
                "rounds": query(self.work, "SELECT * FROM rounds") if self.work.exists() else [],
                "effects": query(self.work, "SELECT * FROM effects ORDER BY rowid") if self.work.exists() else []}
            (self.output / "observations.json").write_text(json.dumps(observations, ensure_ascii=False, indent=2))
            scanned = assert_no_secrets(self.output, [MODEL_KEY.encode(), self.env["LOOM_TEST_SANDBOX_KEY"].encode()])
            (self.output / "secret-scan.json").write_text(json.dumps({"objects": scanned, "matches": 0}))
        frozen = json.loads((self.output / "source-hashes.json").read_text())
        changed = [name for name, digest in frozen.items() if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
        (self.output / "source-closure.json").write_text(json.dumps({"files": len(frozen), "changed_during_run": changed}, indent=2))
        assert not changed, "source changed during acceptance: " + repr(changed)
        (self.output / "PASS").write_text("\n".join(self.checks) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--private-dir", required=True)
    parser.add_argument("--sandbox-endpoint", required=True)
    parser.add_argument("--sandbox-key-file", required=True)
    args = parser.parse_args()
    InstalledUser(args).run()


if __name__ == "__main__":
    main()
