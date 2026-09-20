"""Black-box source installer observations; no writes to the operator's home."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get("LOOM_INSTALL_TEST_OUTPUT") or tempfile.mkdtemp(prefix="loom-install-validation-"))
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.prefix = cls.output / "install with spaces"
        cls.home = cls.output / "synthetic home"
        cls.home.mkdir()
        cls.outside = cls.output / "outside checkout"
        cls.outside.mkdir()
        cls.env = os.environ.copy()
        # Share ordinary dependency caches, not user configuration or credentials.
        for key in ("GOCACHE", "GOMODCACHE", "GOPATH"):
            cls.env[key] = subprocess.check_output(["go", "env", key], text=True).strip()
        cls.env["npm_config_cache"] = subprocess.check_output(["npm", "config", "get", "cache"], text=True).strip()
        cls.env["HOME"] = str(cls.home)
        cls.env.pop("LOOM_INSTALL_ROOT", None)
        cls.config = cls.home / ".config/loom/config.toml"
        cls.config.parent.mkdir(parents=True)
        cls.config.write_text('# user-owned sentinel\n[models.user]\nendpoint="https://example.invalid"\n')
        cls.config_bytes = cls.config.read_bytes()
        cls.observations = {}
        print(f"Installer observations: {cls.output}", file=sys.stderr)
        result = cls.invoke("initial-install", [ROOT / "install.sh", "--prefix", cls.prefix])
        if result.returncode:
            raise AssertionError(f"initial install failed; read {cls.output / 'initial-install.log'}")
        cls.launcher = cls.prefix / "bin/loom"

    @classmethod
    def invoke(cls, name, command, **kwargs):
        result = subprocess.run([str(part) for part in command], cwd=cls.outside, env=kwargs.pop("env", cls.env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
        (cls.output / (name + ".log")).write_bytes(result.stdout)
        return result

    @classmethod
    def tearDownClass(cls):
        (cls.output / "observations.json").write_text(json.dumps(cls.observations, indent=2) + "\n")

    def test_01_real_install_outside_source(self):
        current = (self.prefix / "current").resolve()
        self.assertTrue(self.launcher.is_symlink())
        self.assertEqual(self.invoke("installed-help", [self.launcher, "--help"]).returncode, 0)
        self.assertTrue((current / "services/model/node_modules/@earendil-works/pi-ai/package.json").is_file())
        work = self.output / "portable work"
        authority = self.output / "authority.sqlite"
        create = self.invoke("installed-create", [self.launcher, "--authority", authority, "create", work,
                             "--harness", current / "harnesses/kernel", "--definition", current / "deploy/work.example.toml"])
        self.assertEqual(create.returncode, 0, create.stdout.decode())
        payload = self.output / "objective.json"
        payload.write_text('{"text":"Inspect installer dependency isolation"}')
        admit = self.invoke("installed-harness-admit", [self.launcher, "--authority", authority, "admit", work,
                            "work.objective.set", "--payload", payload, "--request-id", "installer-check"])
        self.assertEqual(admit.returncode, 0, admit.stdout.decode())
        events = self.invoke("installed-events", [self.launcher, "--authority", authority, "events", work])
        self.assertEqual(events.returncode, 0, events.stdout.decode())
        records = json.loads(events.stdout)
        self.assertTrue(any(event["kind"] == "work.objective.set" and event["payload"]["text"] == "Inspect installer dependency isolation" for event in records))
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.observations["outside-source"] = {"active_release": str(current), "runtime_sha256": sha(current / "bin/loom-runtime"), "admitted_event": records}

    def test_02_reinstall_retains_previous_and_configuration(self):
        previous = (self.prefix / "current").resolve()
        digest = sha(previous / "bin/loom-runtime")
        model = self.output / "native-model.json"
        model.write_text(json.dumps({"id": "install-test", "api": "openai-completions", "provider": "custom"}))
        setup_config = self.output / "setup config/config.toml"
        setup = self.invoke("setup-before-upgrade", [self.launcher, "--config", setup_config, "setup", "--model-file", model,
                            "--model-endpoint", "http://127.0.0.1:1/v1", "--sandbox-endpoint", "http://127.0.0.1:2",
                            "--model-key-env", "INSTALL_MODEL_KEY", "--sandbox-key-env", "INSTALL_SANDBOX_KEY"])
        self.assertEqual(setup.returncode, 0, setup.stdout.decode())
        setup_bytes = setup_config.read_bytes()
        self.assertIn(b"worker = ['loom-model']", setup_bytes)
        self.assertNotIn(str(previous).encode(), setup_bytes)

        # Observe the real launcher's environment and the actual exec'ed Node
        # argv. A temporary Runtime probe delays worker startup across activation;
        # it changes no launcher/model bytes and is restored before other checks.
        probe = ('#!' + sys.executable + '\nimport json, os, shutil, sys\n'
                 'print(json.dumps({"root": os.environ["LOOM_INSTALL_ROOT"], "worker": shutil.which("loom-model")}), flush=True)\n'
                 'sys.stdin.readline()\nos.execvp("loom-model", ["loom-model"])\n')
        processes, replaced = [], []

        def delayed_launcher(release):
            binary = release / "bin/loom-runtime"
            saved = release / "bin/loom-runtime.saved"
            binary.rename(saved)
            replaced.append((binary, saved))
            binary.write_text(probe)
            binary.chmod(0o755)
            process = subprocess.Popen([str(self.launcher)], cwd=self.outside, env=self.env,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append(process)
            observed = json.loads(process.stdout.readline())
            self.assertEqual(Path(observed["root"]), release)
            self.assertEqual(Path(observed["worker"]), release / "bin/loom-model")
            return process, observed

        try:
            old_process, old_binding = delayed_launcher(previous)
            result = self.invoke("reinstall", [ROOT / "install.sh", "--prefix", self.prefix])
            self.assertEqual(result.returncode, 0, result.stdout.decode())
            current = (self.prefix / "current").resolve()
            self.assertNotEqual(previous, current)
            new_process, new_binding = delayed_launcher(current)
            for process, release, binding in ((old_process, previous, old_binding), (new_process, current, new_binding)):
                process.stdin.write(b"start\n")
                process.stdin.flush()
                expected_worker = str(release / "services/model/worker.mjs")
                for _ in range(100):
                    argv = subprocess.check_output(["ps", "-p", str(process.pid), "-o", "command="], text=True).strip()
                    if expected_worker in argv:
                        break
                    time.sleep(0.02)
                self.assertIn(expected_worker, argv)
                binding["executed_argv"] = argv
                process.stdin.close()
                process.wait(timeout=10)
                self.assertEqual(process.returncode, 0)
            self.assertEqual(setup_config.read_bytes(), setup_bytes)
            self.observations["upgrade-worker-binding"] = {"old_started_process": old_binding, "new_process": new_binding, "configuration_sha256": sha(setup_config)}
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    pipe.close()
            for binary, saved in replaced:
                binary.unlink()
                saved.rename(binary)
        self.assertTrue(previous.is_dir())
        self.assertEqual(sha(previous / "bin/loom-runtime"), digest)
        self.assertEqual(self.invoke("reinstalled-help", [self.launcher, "--help"]).returncode, 0)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.observations["repeat-install"] = {"old_release": str(previous), "new_release": str(current), "config_sha256": sha(self.config)}

    def test_03_failed_build_preserves_active_release(self):
        previous = os.readlink(self.prefix / "current")
        contents = sorted(path.name for path in (self.prefix / "releases").iterdir())
        digest = sha((self.prefix / "current/bin/loom-runtime").resolve())
        shims = self.output / "failed build tools"
        shims.mkdir()
        go = shims / "go"
        go.write_text('#!/bin/sh\nif [ "$1" = version ]; then printf "go version go1.24.2 test/test\\n"; exit 0; fi\nprintf "deliberate compiler failure\\n" >&2\nexit 23\n')
        go.chmod(0o755)
        environment = self.env.copy()
        environment["PATH"] = str(shims) + os.pathsep + self.env["PATH"]
        result = self.invoke("failed-build", [ROOT / "install.sh", "--prefix", self.prefix], env=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"deliberate compiler failure", result.stdout)
        self.assertEqual(os.readlink(self.prefix / "current"), previous)
        self.assertEqual(sorted(path.name for path in (self.prefix / "releases").iterdir()), contents)
        self.assertEqual(sha((self.prefix / "current/bin/loom-runtime").resolve()), digest)
        self.assertEqual(self.invoke("after-failure-help", [self.launcher, "--help"]).returncode, 0)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.observations["failed-build"] = {"active_link": previous, "runtime_sha256": digest, "releases_unchanged": contents}

    def test_04_unrelated_launcher_is_not_overwritten(self):
        bindir = self.output / "unrelated bin"
        bindir.mkdir()
        unrelated = bindir / "loom"
        sentinel = b"user executable must survive\n"
        unrelated.write_bytes(sentinel)
        result = self.invoke("unrelated-launcher", [ROOT / "install.sh", "--prefix", self.output / "unrelated prefix", "--bin-dir", bindir])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Refusing to replace", result.stdout)
        self.assertEqual(unrelated.read_bytes(), sentinel)
        self.observations["unrelated-launcher"] = {"sha256": sha(unrelated), "preserved": True}

    def test_05_wrong_node_never_activates(self):
        shims = self.output / "wrong node tools"
        shims.mkdir()
        node = shims / "node"
        node.write_text('#!/bin/sh\nprintf "v23.0.0\\n"\n')
        node.chmod(0o755)
        environment = self.env.copy()
        environment["PATH"] = str(shims) + os.pathsep + self.env["PATH"]
        prefix = self.output / "wrong node install"
        result = self.invoke("wrong-node", [ROOT / "install.sh", "--prefix", prefix], env=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"requires Node 24", result.stdout)
        self.assertFalse((prefix / "current").exists())
        self.observations["wrong-node"] = {"activated": False}


if __name__ == "__main__":
    unittest.main()
