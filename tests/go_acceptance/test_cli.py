"""Go black-box acceptance; direct SQL, filesystem and provider-side observers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from support import CLIFixture, ROOT, provider, query


class GoAcceptance(CLIFixture):
    def test_rpc_timeout_interrupts_a_worker_that_never_reads_stdin(self):
        driver = self.driver()
        result = subprocess.run([driver, "rpc-stall", shutil.which("node")], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        observation = json.loads(result.stdout)
        (self.base / "blocked-write.json").write_text(json.dumps(observation, indent=2))
        self.assertTrue(observation["failed"])
        self.assertFalse(observation["watchdog"], "independent watchdog, not RPC deadline, released the blocked pipe")
        self.assertLess(observation["elapsed_ms"], 2000, "100 ms deadline did not bound a blocked local pipe write")

    def test_query_remote_requires_only_sandbox_config_and_is_read_only(self):
        class MissingRemote(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.server.requests.append({"method": "GET", "path": self.path})
                body = b'{"message":"independent remote no longer exists"}'
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        work = self.create()
        self.admit(work)
        server = ThreadingHTTPServer(("127.0.0.1", 0), MissingRemote)
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            image = json.loads((ROOT / "deploy/opensandbox/versions.json").read_text())["code"]
            endpoint = "http://127.0.0.1:" + str(server.server_port)
            self.config.write_text('[sandboxes.sandbox-main]\napi_key_env="LOOM_TEST_SANDBOX_KEY"\nendpoint=' + json.dumps(endpoint) + '\n')
            binding = {"service_id": "sandbox-main", "endpoint": endpoint, "image": image, "profile": "code", "cpu": "1", "memory": "512Mi", "lease_seconds": 600, "request_timeout_seconds": 30}
            with closing(sqlite3.connect(work / ".loom/state.sqlite")) as db, db:
                db.execute("INSERT INTO rounds(id,owner,input_seq,state) VALUES('query-round','old-owner',1,'paused')")
                db.execute("INSERT INTO effects(id,round_id,key,kind,request,digest,status,receipt) VALUES('query-effect','query-round','old','sandbox.shell','{}','fixture','unknown',?)", (json.dumps({"sandbox_id": "missing-sandbox", "execution_id": "missing-session/missing-run", "binding": binding}),))
            before = query(work, "SELECT * FROM effects")
            env = dict(self.env)
            env.pop("LOOM_TEST_MODEL_KEY", None)
            # The peer deliberately reports 404: a read-only failure is the
            # correct result; reaching it without model config is the property.
            self.call("query-remote", work, "query-round", "query-effect", env=env, ok=False)
            self.assertGreater(len(server.requests), 0, "query never reached the remote API")
            self.assertTrue(all(item["method"] == "GET" for item in server.requests))
            self.assertEqual(query(work, "SELECT * FROM effects"), before)
            (self.base / "remote-requests.json").write_text(json.dumps(server.requests, indent=2))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_policy_continuation_is_decided_once_per_native_turn(self):
        policy = self.policy(max_turns=3)
        worker = policy / "worker.mjs"
        worker.write_text(worker.read_text().replace('c.onRequest("policy.continue",p=>false && p.turn.context.messages.filter(m=>m.role==="assistant").length<2);', 'let decisions=0; c.onRequest("policy.continue",p=>++decisions>1);'))
        work = self.base / "work"
        self.call("create", work, "--harness", policy, "--definition", self.definition())
        self.admit(work)
        with provider(work) as server:
            self.configure(server)
            result = self.call("run", work)
            self.assertEqual(result["state"], "completed", "Runtime must honor the single policy stop decision")
            self.assertEqual(len(server.calls), 1)
            self.assertEqual(server.errors, [])
            self.save_provider(server)

    def test_external_python_kernel_uses_same_go_controller(self):
        work = self.base / "work"
        self.call("create", work, "--harness", ROOT / "harnesses/kernel", "--definition", self.definition(userspace=True))
        userspace = self.base / "userspace"
        userspace.mkdir()
        self.call("grant", work, userspace)
        self.admit(work)
        with provider(work) as server:
            self.configure(server)
            result = self.call("run", work)
            self.assertEqual(result["state"], "completed")
            self.assertEqual(len(server.calls), 1)
            self.assertEqual(server.errors, [])
            self.assertIn("report.md", server.calls[0]["body"]["messages"][0]["content"])
            self.save_provider(server)

    def driver(self):
        path = self.base / "storage-cutpoint"
        subprocess.run(["go", "build", "-o", path, str(ROOT / "tests/go_acceptance/driver/main.go")], cwd=ROOT / "runtime", check=True, capture_output=True)
        return path

    def test_after_event_insert_sigkill_has_no_partial_admission(self):
        work = self.create()
        database = work / ".loom/state.sqlite"
        driver = self.driver()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TRIGGER acceptance_kill AFTER INSERT ON events BEGIN SELECT acceptance_kill_writer(); END")
        result = subprocess.run([driver, "kill", database], text=True, capture_output=True)
        (self.base / "cutpoint.json").write_text(json.dumps({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, indent=2))
        self.assertEqual(result.returncode, -signal.SIGKILL)
        self.assertIn("AFTER EVENT INSERT", result.stdout)
        for table in ("events", "admissions", "pending"):
            self.assertEqual(query(work, "SELECT COUNT(*) AS n FROM " + table), [{"n": 0}])
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DROP TRIGGER acceptance_kill")
        result = subprocess.run([driver, "admit", database], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for table in ("events", "admissions", "pending"):
            self.assertEqual(query(work, "SELECT COUNT(*) AS n FROM " + table), [{"n": 1}])

    def test_separate_go_processes_have_one_round_and_resume_owner(self):
        work = self.create()
        self.admit(work)
        driver = self.driver()
        database = work / ".loom/state.sqlite"
        observations = []
        for mode in ("begin", "resume"):
            if mode == "resume":
                with closing(sqlite3.connect(database)) as db, db:
                    # Component fixture only: known no-effect checkpoint, not an
                    # end-to-end claim that external execution was recovered.
                    db.execute("UPDATE rounds SET state='paused',checkpoint=?", (json.dumps({"context": {"messages": []}, "plan": {"max_turns": 1}}),))
            children = [subprocess.Popen([driver, mode, database], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
            outcomes = []
            for child in children:
                out, err = child.communicate(timeout=20)
                outcomes.append({"returncode": child.returncode, "stdout": out, "stderr": err})
            self.assertEqual(sum(r["returncode"] == 0 for r in outcomes), 1)
            self.assertEqual(len(query(work, "SELECT * FROM rounds")), 1)
            observations.append({"mode": mode, "processes": outcomes})
        (self.base / "owners.json").write_text(json.dumps(observations, indent=2))

    def test_native_binary_and_node_policy_without_python(self):
        identity = subprocess.check_output(["go", "version", "-m", self.binary], text=True)
        self.assertIn("loom/runtime", identity)
        (self.base / "binary-build-info.txt").write_text(identity)
        safe_bin = self.base / "bin"
        safe_bin.mkdir()
        for tool in ("node", "git"):
            (safe_bin / tool).symlink_to(shutil.which(tool))
        env = dict(self.env, PATH=str(safe_bin))
        self.assertIsNone(shutil.which("python", path=env["PATH"]))
        self.assertIsNone(shutil.which("python3", path=env["PATH"]))
        work = self.base / "work"
        self.call("create", work, "--harness", self.policy(), "--definition", self.definition(), env=env)
        payload = self.base / "payload.json"
        payload.write_text('{"text":"Go with only Node and Git"}')
        self.call("admit", work, "work.objective.set", "--payload", payload, "--request-id", "one", env=env)
        with provider(work) as server:
            self.configure(server)
            result = self.call("run", work, env=env)
            self.assertEqual(result["state"], "completed")
            self.assertEqual(len(server.calls), 1)
            self.assertEqual(server.errors, [])
            self.assertIn("INDEPENDENT NODE POLICY", json.dumps(server.calls))
            self.save_provider(server)
        self.assertEqual(query(work, "SELECT * FROM pending"), [])
        effects = query(work, "SELECT * FROM effects")
        self.assertEqual([(e["kind"], e["status"]) for e in effects], [("model", "completed")])
        result = json.loads(effects[0]["result"])
        reference = result["artifact"]
        raw = (work / reference["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), reference["sha256"])
        message = json.loads(raw)["message"]
        self.assertEqual(message["stopReason"], "stop")
        self.assertEqual(message["usage"]["totalTokens"], 10)
        self.assertIn("thinking", [part["type"] for part in message["content"]])
        for path in work.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"go-acceptance-synthetic-key", path.read_bytes())

    def test_atomic_concurrent_admission_conflict_and_restart(self):
        work = self.create()
        payload = self.base / "input.json"
        payload.write_text('{"text":"one durable fact"}')
        command = self.command("admit", work, "work.objective.set", "--payload", payload, "--request-id", "same")
        children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env) for _ in range(6)]
        outcomes = []
        for child in children:
            out, err = child.communicate(timeout=30)
            self.assertEqual(child.returncode, 0, err)
            outcomes.append(json.loads(out))
        (self.base / "concurrent.json").write_text(json.dumps(outcomes, indent=2))
        self.assertEqual(len({item["seq"] for item in outcomes}), 1)
        for table in ("events", "admissions", "pending"):
            self.assertEqual(query(work, "SELECT COUNT(*) AS n FROM " + table), [{"n": 1}])
        self.admit(work, "same", {"text": "different"}, ok=False)
        self.assertEqual(query(work, "SELECT payload FROM events"), [{"payload": '{"text":"one durable fact"}'}])
        self.assertEqual(query(work, "PRAGMA integrity_check"), [{"integrity_check": "ok"}])
        self.call("status", work)
        self.assertEqual(len(query(work, "SELECT * FROM pending")), 1)

    def test_unknown_model_and_process_death_never_redispatch(self):
        work = self.create(timeout=0.2)
        self.admit(work)
        with provider(work, "hang") as server:
            self.configure(server)
            self.call("run", work, ok=False)
            self.assertEqual(len(server.calls), 1)
            self.assertEqual(query(work, "SELECT state FROM rounds"), [{"state": "paused"}])
            effects = query(work, "SELECT status,result FROM effects")
            self.assertEqual(len(effects), 1)
            if effects[0]["status"] == "completed":
                self.assertIn(json.loads(effects[0]["result"])["stopReason"], ["aborted", "error"])
            else:
                self.assertEqual(effects[0]["status"], "unknown")
            self.call("run", work, ok=False)
            self.call("resume", work, ok=False)
            self.assertEqual(len(server.calls), 1)
            self.save_provider(server)
        self.assertEqual(len(query(work, "SELECT * FROM pending")), 1)
        self.call("export", work, self.base / "unsafe.tar.gz", ok=False)

    def test_killed_go_owner_is_not_taken_over_or_redispatched(self):
        work = self.create(timeout=20)
        self.admit(work)
        with provider(work, "hang") as server:
            self.configure(server)
            child = subprocess.Popen(self.command("run", work), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
            workers = []
            try:
                self.assertTrue(server.received.wait(10), "real Pi provider request never arrived")
                workers = [int(pid) for pid in subprocess.check_output(["pgrep", "-P", str(child.pid)], text=True).split()]
                child.kill()
                out, err = child.communicate(timeout=10)
                self.assertEqual(child.returncode, -signal.SIGKILL)
                (self.base / "controller-kill.json").write_text(json.dumps({"returncode": child.returncode, "stdout": out, "stderr": err, "owned_worker_pids": workers}, indent=2))
                self.assertEqual(query(work, "SELECT state FROM rounds"), [{"state": "running"}])
                self.assertEqual(query(work, "SELECT status FROM effects"), [{"status": "intent"}])
                self.call("run", work, ok=False)
                self.call("resume", work, ok=False)
                self.assertEqual(len(server.calls), 1)
                self.save_provider(server)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
                for pid in workers:
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_explicit_resume_preserves_native_context_and_local_failure(self):
        work = self.create(continuation=True, max_turns=1)
        self.admit(work)
        with provider(work, "continue") as server:
            self.configure(server)
            self.call("run", work, ok=False)
            before = query(work, "SELECT state,checkpoint FROM rounds")[0]
            self.assertEqual(before["state"], "paused")
            self.assertIsNotNone(before["checkpoint"])
            self.assertEqual(len(server.calls), 1)
            self.configure(server, worker=[str(self.base / "nonexistent-worker")])
            self.call("resume", work, ok=False)
            after = query(work, "SELECT state,checkpoint FROM rounds")[0]
            self.assertEqual(after, before)
            self.assertEqual(len(server.calls), 1)
            self.configure(server)
            resumed = self.call("resume", work)
            self.assertEqual(resumed["state"], "completed")
            self.assertEqual(len(server.calls), 2)
            self.assertIn("first answer", json.dumps(server.calls[1]["body"]))
            self.assertEqual(server.errors, [])
            self.save_provider(server)
        self.assertEqual(len(query(work, "SELECT * FROM rounds")), 1)
        effects = query(work, "SELECT id,status FROM effects")
        self.assertEqual(len({e["id"] for e in effects}), 2)
        self.assertEqual({e["status"] for e in effects}, {"completed"})
        self.assertEqual(query(work, "SELECT * FROM pending"), [])

    def test_authority_copy_overlap_schema_relay(self):
        sender = self.create("sender", userspace=True)
        receiver = self.create("receiver", userspace=True)
        copied = self.base / "copied"
        shutil.copytree(sender, copied)
        self.call("status", copied, ok=False)
        self.call("grant", sender, sender / "surface", ok=False)
        userspace = self.base / "userspace"
        userspace.mkdir()
        nested = userspace / "nested"
        nested.mkdir()
        self.call("grant", sender, userspace)
        self.call("grant", receiver, nested, ok=False)
        self.admit(sender, payload={"text": "ok", "source": "system"}, ok=False)
        self.assertEqual(query(sender, "SELECT * FROM events"), [])
        payload = self.base / "relay.json"
        payload.write_text('{"text":"relay input"}')
        relay = ("relay", sender, receiver, "work.objective.set", "--payload", payload, "--request-id", "relay-one")
        self.call(*relay, ok=False)
        self.call("allow-relay", sender, receiver)
        result = self.call(*relay)
        self.assertEqual(self.call(*relay), result)
        events = query(receiver, "SELECT * FROM events")
        self.assertEqual(len(events), 1)
        self.assertNotEqual(events[0]["source"], "system")
        payload.write_text('{"text":42}')
        self.call("relay", sender, receiver, "work.objective.set", "--payload", payload, "--request-id", "bad-schema", ok=False)
        self.assertEqual(len(query(receiver, "SELECT * FROM events")), 1)

    def test_export_committed_wal_pending_no_authority_and_tamper_rejected(self):
        work = self.create()
        db = sqlite3.connect(work / ".loom/state.sqlite")
        self.addCleanup(db.close)
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("BEGIN")
        db.execute("SELECT COUNT(*) FROM events").fetchone()
        self.admit(work, "before-export")
        self.assertTrue(Path(str(work / ".loom/state.sqlite") + "-wal").stat().st_size > 0)
        archive = self.base / "work.tar.gz"
        self.call("export", work, archive)
        unpacked = self.base / "unpacked"
        unpacked.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(unpacked, filter="data")
        exported = unpacked / "work"
        self.assertEqual(query(exported, "SELECT source,request_id,kind,payload FROM events"), query(work, "SELECT source,request_id,kind,payload FROM events"))
        self.assertEqual(query(exported, "SELECT * FROM pending"), query(work, "SELECT * FROM pending"))
        self.assertFalse((exported / "authority.sqlite").exists())
        imported = self.base / "imported"
        fresh_authority = self.base / "fresh-authority.sqlite"
        result = self.call("import", archive, imported, authority=fresh_authority)
        self.assertFalse(result["authorized"])
        self.call("status", imported, authority=fresh_authority, ok=False)
        self.call("register", imported, authority=fresh_authority)
        self.call("status", imported, authority=fresh_authority)
        self.assertEqual(query(imported, "SELECT * FROM pending"), query(work, "SELECT * FROM pending"))
        (exported / ".loom/identity.json").write_text('{}')
        broken = self.base / "bad.tar.gz"
        with tarfile.open(broken, "w:gz") as target:
            target.add(exported, arcname="work")
        self.call("import", broken, self.base / "bad-import", authority=fresh_authority, ok=False)
        self.assertFalse((self.base / "bad-import").exists())


if __name__ == "__main__":
    unittest.main()
