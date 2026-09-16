"""Independent M06 observer: reuses the generic O1-O8 collection methods from
the M01 observer WITHOUT modifying that file (M01 evidence pins its source
hashes). The M06 artifact oracle resolves /work/result.json from the original
task-domain F version (Git blob, hash-verified) and compares the parsed JSON to
the preregistered expectation in samples.json. It reads original stores only,
never runtime replies.
"""
import json
from pathlib import Path

from validation.system.runtime_observer import Observer
from validation.system.runtime_observer_sources import (
    EngineRead,
    digest,
    git_version,
    require,
)


class M06Observer(Observer):
    async def begin(self, sample, registration_ids):
        # M06 samples carry no protected observer-original input; the M01 begin
        # reads sample["original_input"] — the rest of the original begin is
        # reused byte-for-byte semantics (identities, clock, watch task).
        import asyncio, copy, os, time
        from validation.system.runtime_observer_sources import (
            EngineRead, canonical, digest, read, require)
        self.required()
        require(self.started is None, "observer already begun")
        require(set(registration_ids) == {"surface", "workspace"},
                "two original registration identities required")
        self.registration_ids = copy.deepcopy(registration_ids)
        self.started = time.monotonic()
        self.engine = EngineRead(self.cfg["engine_endpoint"])
        self.loop = asyncio.get_running_loop()
        self.wake = asyncio.Event()
        self.save("begin.json", dict(sample=sample,
                                     registration_ids=registration_ids,
                                     monotonic=self.started, pid=os.getpid(),
                                     config_sha256=digest(canonical(self.config))))
        self.task = asyncio.create_task(self._watch())
        await asyncio.sleep(0)

    async def collect_m06(self, sample, request_id):
        self.closed = True
        if self.wake:
            self.wake.set()
        if self.task:
            await self.task
        artifacts = None
        db = None
        rows = []
        decisions = []
        entries = []
        provider = []
        tools = []
        versions = {}
        chain = set()
        try:
            self.required()
            self.engine = self.engine or EngineRead(self.cfg["engine_endpoint"])
        except Exception as exc:
            self.check("O1", "configuration_and_original_owners_available", False, error=str(exc))
            return self._finish_m06(sample, artifacts)
        if not self.registration_ids:
            self.registration_ids = {d: self.config["startup"]["sources"][d]["resource_id"]
                                     for d in ("surface", "workspace")}

        async def run(group, name, fn):
            try:
                result = fn()
                if hasattr(result, "__await__"):
                    result = await result
                return result
            except Exception as exc:
                self.check(group, name, False, error=type(exc).__name__ + ": " + str(exc))
                return None

        result = await run("O1", "original_R_chain", lambda: self._R(request_id))
        if result:
            db, rows, decisions = result
            chain = {r["id"] for r in rows}
        if db:
            result = await run("O3", "original_S_source", lambda: self._S(chain, decisions))
            if result:
                entries, _ = result
            result = await run("O4", "original_provider_source", lambda: self._provider(db, chain, entries))
            if result is not None:
                provider = result
            result = await run("O5", "original_X_and_F_source", lambda: self._tools(db, chain))
            if result:
                tools, versions = result
            await run("O4", "original_complete_tool_feedback", lambda: self._feedback(tools, entries, provider))
            await run("O6", "original_events_and_next_input", lambda: __import__("asyncio").wait_for(self._events(db, chain, provider), 10))
            await run("O8", "all_X_final_originals", lambda: self._final_X(chain))
            artifacts = await run("O2", "original_browser_artifact", lambda: self._m06_artifact(versions, sample))
        await run("O7", "original_budget_observations", lambda: self._budgets(rows, provider))
        for group in ("O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8"):
            if not any(c["group"] == group for c in self.checks):
                self.check(group, "required_original_evidence_missing", False)
        self._revise_checks()
        return self._finish_m06(sample, artifacts)

    def _m06_artifact(self, versions, sample):
        require("task" in versions, "original task artifact domain absent")
        version, files = versions["task"]
        require("result.json" in files, "original result.json missing from task version")
        body = files["result.json"]
        if not isinstance(body, bytes):
            require(isinstance(body, dict), "unexpected F file entry type")
            require("path" in body or "content" in body, "F file entry lacks content")
            body = body.get("content") or Path(body["path"]).read_bytes()
        observed = json.loads(body.decode("utf8"))
        expected = sample["expected_result"]
        if observed != expected:
            # Record the mismatch evidence on the check itself (tamper cases
            # rely on it), then fail the check.
            self.check("O2", "original_result_json_matches_preregistration", False,
                       observed=observed, expected=expected)
        require(observed == expected,
                "browser artifact differs from preregistered expectation: "
                + json.dumps({"observed": observed, "expected": expected}, default=str))
        self.check("O2", "original_result_json_matches_preregistration", True,
                   observed=observed)
        return dict(result_path="/work/result.json", content=observed,
                    version_ref=version)

    def _revise_checks(self):
        """M06 batch revisions of two M01-scale hardcoded checks.

        original_real_model_scope: the M06 fixed driver replaces the real
        provider; the revised criterion verifies the scripted model scope on
        the actual provider originals (request and response model ids) instead
        of requiring a non-loopback endpoint. actual_original_resource_bounds:
        ceilings derive from the registered environment profile budget maxima
        (amendment-linux-browser) instead of the fixed M01 python scale. The
        superseded criteria stay recorded in the check entries.
        """
        from lore_execution.requests import _load_environment_profiles
        regs = _load_environment_profiles()
        out = []
        for c in self.checks:
            if c.get("check") == "original_real_model_scope":
                pf = self.out / "provider-originals.json"
                data = json.loads(pf.read_bytes()) if pf.exists() else []
                # The harness-facing scope carries the fixed driver id; the
                # wire carries the declared baseline (amendment-model-baseline).
                from lore_provider.request import MODEL as _wire_model
                ok = bool(data) and all(
                    p["request"].get("model") == _wire_model
                    and p["response"].get("model") == _wire_model for p in data)
                out.append(dict(c, passed=ok, count=len(data),
                                superseded="m01-nonloopback-and-pinned-model",
                                revised="m06-fixed-provider-model-scope"))
            elif c.get("check") == "actual_original_resource_bounds":
                ok = True
                for t in self.trace:
                    if t.get("errors"):
                        ok = False
                    for o in t.get("objects", []):
                        ins = o.get("inspect")
                        if not ins or ins.get("status") != 200:
                            continue
                        body = ins["body"]
                        h = body["HostConfig"]
                        labels = body["Config"].get("Labels") or {}
                        role = labels.get("lore.x.role", "tool")
                        env = (o.get("binding") or {}).get("profile", {}).get("id")
                        entry = regs.get(env) or {}
                        mx = entry.get("budget_maxima", {})
                        good = (h.get("ReadonlyRootfs") and h.get("NetworkMode") == "none"
                                and "ALL" in (h.get("CapDrop") or [])
                                and any("no-new-privileges" in z for z in h.get("SecurityOpt") or []))
                        good &= h.get("Memory", 0) > 0 and h.get("Memory", 0) <= mx.get("memory_bytes", 134217728)
                        good &= h.get("MemorySwap", 0) == h.get("Memory")
                        good &= 0 < h.get("PidsLimit", 0) <= mx.get("pids", 32)
                        good &= 0 < h.get("NanoCpus", 0) <= int(mx.get("cpu", .25) * 1e9) + 1
                        good &= 0 < h.get("ShmSize", 0) <= mx.get("shm_bytes", 1048576)
                        for key, options in (h.get("Tmpfs") or {}).items():
                            parts = dict(z.split("=", 1) for z in options.split(",") if "=" in z)
                            good &= all(z in options.split(",") for z in ("nosuid", "nodev", "noexec"))
                            good &= 0 < int(parts.get("size", "0")) <= mx.get("tmp_bytes", 1048576)
                            good &= 0 < int(parts.get("nr_inodes", "0")) <= mx.get("tmp_inodes", 64)
                        if not good:
                            ok = False
                out.append(dict(c, passed=ok,
                                superseded="m01-fixed-python-scale-bounds",
                                revised="m06-registered-profile-scale-bounds"))
            else:
                out.append(c)
        self.checks = out

    def _finish_m06(self, sample, artifacts):
        result = dict(
            id=sample.get("id"),
            status="PASS" if self.checks and all(c["passed"] for c in self.checks) and artifacts else "FAIL",
            scope="ONE_M06_SAMPLE_ORIGINAL_OBSERVATIONS_ONLY",
            checks=self.checks, observations=self.observations,
            source_hashes={str(Path(__file__)): digest(Path(__file__).read_bytes())})
        if artifacts:
            result["artifact"] = artifacts
        (self.out / "observer-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result
