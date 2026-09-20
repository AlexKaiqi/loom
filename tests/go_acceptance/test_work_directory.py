"""Portable Work criteria from the original directory contract, independently observed."""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import threading
import tomllib

from support import CLIFixture, ROOT, provider, query, assert_no_secrets


class WorkDirectoryAcceptance(CLIFixture):
    def test_explicit_declaration_hidden_layout_and_immutable_binding(self):
        self.call("create", self.base / "undeclared", "--harness", self.policy("undeclared-policy"), ok=False)
        self.assertFalse((self.base / "undeclared").exists())
        work = self.create()
        self.assertEqual({p.name for p in work.iterdir()}, {"work.toml", "harness", "surface", ".loom"})
        self.assertTrue((work / ".loom/identity.json").is_file())
        self.assertTrue((work / ".loom/state.sqlite").is_file())
        self.assertTrue((work / ".loom/versions.git/objects").is_dir())
        definition = tomllib.loads((work / "work.toml").read_text())
        self.assertEqual(definition["model"]["service"], "model-main")
        self.assertEqual(definition["model"]["definition"]["id"], "fixture-model")
        self.assertNotIn("baseUrl", definition["model"]["definition"])
        self.assertNotIn("endpoint", definition["sandbox"])
        self.assertFalse((work / "surface/content").exists())
        (work / "work.toml").write_text((work / "work.toml").read_text().replace('fixture-model', 'changed-model'))
        self.call("status", work, ok=False)
        self.call("export", work, self.base / "mutated.tar.gz", ok=False)

    def test_model_definition_rejects_transport_credentials(self):
        for field, value in (("baseUrl", "https://example.invalid"), ("apiKey", "canary-forbidden-key"), ("headers", {"Authorization": "canary-forbidden-header"})):
            native = {"id": "fixture-model", "api": "openai-completions", "provider": "fixture", "name": "Fixture", field: value}
            definition = self.definition(native=native, name=field + ".toml")
            destination = self.base / ("invalid-" + field)
            self.call("create", destination, "--harness", self.policy("policy-" + field), "--definition", definition, ok=False)
            self.assertFalse(destination.exists(), "invalid declaration left a partially created Work")

    def test_stored_model_semantics_and_native_pause_move_without_old_host(self):
        work = self.create(continuation=True, max_turns=1, prepare_model=True)
        (work / "surface/notes.md").write_bytes(b"human ordinary content\r\n")
        self.admit(work)
        header_old = b"portable-old-host-header-canary"
        header_new = b"portable-new-host-header-canary"
        self.env["LOOM_TEST_HEADER_KEY"] = header_old.decode()
        with provider(work, "continue") as server:
            server.expected_header, server.header_matches = header_old.decode(), []
            self.configure(server, headers_env={"X-Acceptance-Token": "LOOM_TEST_HEADER_KEY"})
            self.config.write_text(self.config.read_text() + '\n[models.unused-default]\nendpoint="http://127.0.0.1:1"\napi_key_env="UNAVAILABLE_DEFAULT_KEY"\nworker=["missing-worker"]\n')
            self.call("run", work, ok=False)
            before = query(work, "SELECT * FROM rounds")[0]
            self.assertEqual(before["state"], "paused")
            self.assertIsNotNone(before["checkpoint"])
            old_effects = query(work, "SELECT * FROM effects ORDER BY rowid")
            self.assertEqual(len(server.calls), 1)
            self.assertEqual(server.header_matches, [True])
            assert_no_secrets(work, [header_old])
            self.assertEqual(server.calls[0]["body"]["model"], "fixture-model")
            archive = self.base / "paused.tar.gz"
            self.call("export", work, archive)
            imported, fresh_authority = self.base / "moved", self.base / "new-host-authority.sqlite"
            self.call("import", archive, imported, authority=fresh_authority)
            self.call("status", imported, authority=fresh_authority, ok=False)
            self.call("register", imported, authority=fresh_authority)
            self.assertEqual(query(imported, "SELECT * FROM effects ORDER BY rowid"), old_effects)
            self.assertEqual((imported / "surface/notes.md").read_bytes(), b"human ordinary content\r\n")
            shutil.rmtree(work)
            self.authority.unlink()
            self.config.unlink()
            server.work = imported
            with provider(imported, "text") as relocated:
                self.env["LOOM_TEST_HEADER_KEY"] = header_new.decode()
                relocated.expected_header, relocated.header_matches = header_new.decode(), []
                self.configure(relocated, headers_env={"X-Acceptance-Token": "LOOM_TEST_HEADER_KEY"})
                self.assertNotEqual(relocated.base_url, server.base_url)
                result = self.call("resume", imported, authority=fresh_authority)
                (self.base / "provider-relocation.json").write_text(json.dumps({"old_endpoint": server.base_url, "old_calls": server.calls, "new_endpoint": relocated.base_url, "new_calls": relocated.calls}, indent=2))
                self.assertEqual(result["state"], "completed")
                self.assertEqual(result["round_id"], before["id"])
                self.assertEqual(len(server.calls), 1, "resume used stale endpoint from native checkpoint")
                self.assertEqual(len(relocated.calls), 1)
                self.assertEqual(relocated.header_matches, [True])
                self.assertIn("first answer", json.dumps(relocated.calls[0]["body"]))
                self.assertEqual(relocated.calls[0]["body"]["model"], "fixture-model")
                self.assertEqual(server.errors, [])
                self.assertEqual(relocated.errors, [])
                self.assertEqual(query(imported, "SELECT * FROM pending"), [])
            for effect in old_effects:
                reference = json.loads(effect["result"])["artifact"]
                self.assertEqual(hashlib.sha256((imported / reference["path"]).read_bytes()).hexdigest(), reference["sha256"])
            assert_no_secrets(imported, [header_old, header_new, self.env["LOOM_TEST_MODEL_KEY"].encode()])

    def test_userspace_snapshot_restore_requires_new_grant_and_exact_bytes(self):
        work = self.create(userspace=True)
        userspace = self.base / "original-userspace"
        userspace.mkdir()
        (userspace / "numbers.txt").write_bytes(b"2\n3\n5\n")
        (userspace / "hidden.bin").write_bytes(bytes(range(256)))
        self.call("grant", work, userspace)
        self.assertTrue(any(p.is_file() for p in (work / ".loom/dependencies").rglob("*")))
        archive = self.base / "portable.tar.gz"
        self.call("export", work, archive)
        moved, fresh_authority = self.base / "moved", self.base / "new-host-authority.sqlite"
        self.call("import", archive, moved, authority=fresh_authority)
        self.call("register", moved, authority=fresh_authority)
        restored = self.base / "restored-userspace"
        self.call("restore-userspace", moved, restored, authority=fresh_authority)
        self.assertEqual((restored / "numbers.txt").read_bytes(), b"2\n3\n5\n")
        self.assertEqual((restored / "hidden.bin").read_bytes(), bytes(range(256)))
        with closing(sqlite3.connect(fresh_authority)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM grants").fetchone()[0], 0, "restore silently granted physical authority")
        self.call("restore-userspace", moved, restored, authority=fresh_authority, ok=False)
        changed = self.base / "different-bytes"
        shutil.copytree(restored, changed)
        (changed / "numbers.txt").write_bytes(b"999\n")
        self.call("grant", moved, changed, authority=fresh_authority, ok=False)
        self.call("grant", moved, restored, authority=fresh_authority)
        shutil.rmtree(work)
        shutil.rmtree(userspace)
        self.call("status", moved, authority=fresh_authority)
        dependency_files = [p for p in (moved / ".loom/dependencies").rglob("*") if p.is_file()]
        self.assertTrue(dependency_files)
        damaged = next((p for p in dependency_files if tarfile.is_tarfile(p)), dependency_files[0])
        damaged.write_bytes(b"independently corrupted dependency bytes")
        self.call("restore-userspace", moved, self.base / "bad-restore", authority=fresh_authority, ok=False)
        self.call("export", moved, self.base / "bad-export.tar.gz", authority=fresh_authority, ok=False)
        damaged.unlink()
        self.call("restore-userspace", moved, self.base / "missing-restore", authority=fresh_authority, ok=False)

    def test_resume_rejects_changed_granted_userspace_before_dispatch(self):
        work = self.create(userspace=True, continuation=True, max_turns=1)
        userspace = self.base / "userspace"
        userspace.mkdir()
        source = userspace / "numbers.txt"
        source.write_bytes(b"2\n3\n5\n")
        self.call("grant", work, userspace)
        self.admit(work)
        with provider(work, "continue") as server:
            self.configure(server)
            self.call("run", work, ok=False)
            before_round = query(work, "SELECT * FROM rounds")
            before_effects = query(work, "SELECT * FROM effects")
            self.assertEqual(before_round[0]["state"], "paused")
            self.assertIsNotNone(before_round[0]["checkpoint"])
            source.write_bytes(b"unapproved content drift\n")
            self.call("resume", work, ok=False)
            self.assertEqual(len(server.calls), 1, "resume dispatched a model against changed dependency bytes")
            self.assertEqual(query(work, "SELECT * FROM rounds"), before_round)
            self.assertEqual(query(work, "SELECT * FROM effects"), before_effects)
            source.write_bytes(b"2\n3\n5\n")
            result = self.call("resume", work)
            self.assertEqual(result["round_id"], before_round[0]["id"])
            self.assertEqual(result["state"], "completed")
            self.assertEqual(len(server.calls), 2)
            self.assertEqual(server.errors, [])
            self.save_provider(server)

    def test_remote_query_rejects_endpoint_drift_before_network(self):
        class Observer(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.server.requests.append(self.path)
                self.send_response(404)
                self.end_headers()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Observer)
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            work = self.create()
            self.admit(work)
            endpoint = "http://127.0.0.1:" + str(server.server_port)
            image = json.loads((ROOT / "deploy/opensandbox/versions.json").read_text())["code"]
            receipt = {"sandbox_id": "old-sandbox", "execution_id": "old-session/old-run", "binding": {"service_id": "sandbox-main", "endpoint": "http://127.0.0.1:1", "image": image, "profile": "code", "cpu": "1", "memory": "512Mi", "lease_seconds": 600, "request_timeout_seconds": 30}}
            with closing(sqlite3.connect(work / ".loom/state.sqlite")) as db, db:
                db.execute("INSERT INTO rounds(id,owner,input_seq,state) VALUES('old-round','old-owner',1,'paused')")
                db.execute("INSERT INTO effects(id,round_id,key,kind,request,digest,status,receipt) VALUES('old-effect','old-round','old-tool','sandbox.shell','{}','fixture','unknown',?)", (json.dumps(receipt),))
            self.config.write_text('[sandboxes.sandbox-main]\nendpoint=' + json.dumps(endpoint) + '\napi_key_env="LOOM_TEST_SANDBOX_KEY"\n')
            before = query(work, "SELECT * FROM effects")
            self.call("query-remote", work, "old-round", "old-effect", ok=False)
            self.assertEqual(server.requests, [], "old operation IDs were sent to a different service endpoint")
            self.assertEqual(query(work, "SELECT * FROM effects"), before)
            (self.base / "remote-negative-observation.json").write_text(json.dumps({"requests": server.requests, "receipt": receipt}, indent=2))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
