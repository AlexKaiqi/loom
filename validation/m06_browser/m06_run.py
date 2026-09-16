"""M06 batch-A driver (protocol m06-batch-a-001): fixed HTTP model responses
(M02 shape) drive the real Runtime (R/E/F/X/S + Docker + NATS) through the
linux-browser-v1 session profile. The scripted response calls the ordinary
shell tool once to run the preregistered task.py; the independent M06Observer
(O1-O8 + result.json preregistration check) collects original evidence.

Failure at any stage records FAIL with the actual error; nothing is retried,
patched, or inferred (P7). The batch passes only 9/9.
"""
import argparse
import asyncio
import copy
import hashlib
import http.server
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BROWSER_PROFILE = ROOT / "design/g3/x-node-profile/node-profile-linux-browser-v1.json"
BROWSER_TEMPLATE = ROOT / "design/g3/x-node-profile/node-request-template-linux-browser-v1.json"
ORIGINAL_HOST = (ROOT / "validation/session-plan-evidence/"
                 "context-independent-001/workspace/original-host")
MODEL_ID = "fixed-m06-driver"
ARCHIVE = dict(context_tokens=49152, reserve_tokens=40960,
               tail_reserve_tokens=4096, soft_tokens=8192)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fact(path):
    path = Path(path).absolute()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def configuration(sample, url, endpoint):
    """Browser-session bootstrap profile (mirrors the tested M01 assembly)."""
    from lore_runtime.startup_assets import CODE_FILES
    out = Path(sample["surface"]).parent
    host = out / "host"
    principal, namespace = "operator", sample["id"]
    authority = {principal: dict(namespaces=[namespace], roles=["admin", "runtime", "submit"])}
    deps = ORIGINAL_HOST / "dependencies-manifest.json"
    dm = json.loads(deps.read_text())
    model = dict(id=MODEL_ID, name=MODEL_ID, api="lore-stdio",
                 provider="lore-provider", reasoning=False, input=["text"],
                 cost=dict(input=0, output=0, cacheRead=0, cacheWrite=0),
                 contextWindow=ARCHIVE["context_tokens"], maxTokens=16384)
    startup = dict(principal=principal, namespace=namespace,
        sources={d: dict(path=sample[d], resource_id=sample["id"] + "-" + d)
                 for d in ("surface", "workspace")},
        code_sources={name: fact(ROOT / name) for name in CODE_FILES},
        profile_ref=fact(BROWSER_PROFILE),
        request_template_ref=fact(BROWSER_TEMPLATE),
        deps_mount=dict(role="dependencies", source=dm["root"], target="/opt",
                        read_only=True, manifest_ref=fact(deps), content_ref=dm["source_ref"]),
        model=model, capability_limits=dict(max_steps=24, archive=ARCHIVE))
    events = dict(schema_version=1, namespaces=[namespace], stream_max_bytes=8388608,
        message_limit_bytes=65536, page_size=16, authority=authority,
        runtime_principal=principal, input_root=str(host / "E-inputs"),
        stream_prefix="LORE_", subject_prefix="lore", storage="file", discard="new",
        max_age=0, replicas=1)
    runtime = dict(control_db=str(out / "R.sqlite"), files_dir=str(out / "F"),
        execution_dir=str(host / "X-state"), session_dir=str(out / "S"), nats_url=url,
        engine_endpoint="unix:///var/run/docker.sock", authority=authority,
        worker_id=sample["id"] + "-worker", event_profile=events)
    initial = dict(owner="S", namespace=namespace, surface_id=sample["id"] + "-surface",
        session_id=sample["id"] + "-session", session_generation=1,
        confirmation_request_id=None)
    budget = dict(max_requests=24, max_input_tokens=393216,
        max_output_tokens_per_request=16384, max_request_body_bytes=65536, max_seconds=1800,
        reasoning_effort="medium")
    return dict(runtime=runtime, startup_root=str(host), startup=startup,
        provider=dict(root=str(out / "provider"), endpoint=endpoint, principal=principal,
                      timeout=300, budget=budget),
        initial_session_ref=initial)


TASK_SCRIPT = "python3 /work/task.py\n"
EMIT_SCRIPT = 'python3 /input/surface/emit.py browser-task-done \'{"task":"browser","done":true}\'\n'


class FixedResponseServer:
    """Scripted openai-compatible chat completions: one shell tool call running
    the preregistered task.py, then a stop. Binds localhost only; no secrets."""

    def __init__(self):
        self.requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.requests.append(body)
                model = body.get("model", MODEL_ID)
                step = len(self.server.requests)
                if step == 1:
                    # Preregistered script: the browser task on the workspace
                    # target, then the surface emit on the runtime target, then
                    # the final stop - the M01 real-chain shape.
                    message = {"role": "assistant", "content": None, "tool_calls": [
                        {"id": "call-1", "type": "function", "function": {
                            "name": "shell",
                            "arguments": json.dumps({"target": "workspace",
                                                     "script": TASK_SCRIPT})}}]}
                    finish = "tool_calls"
                elif step == 2:
                    message = {"role": "assistant", "content": None, "tool_calls": [
                        {"id": "call-2", "type": "function", "function": {
                            "name": "shell",
                            "arguments": json.dumps({"target": "runtime",
                                                     "script": EMIT_SCRIPT})}}]}
                    finish = "tool_calls"
                else:
                    message = {"role": "assistant", "content": "browser task issued"}
                    finish = "stop"
                payload = json.dumps({"id": "fixed-" + str(step), "object": "chat.completion",
                    "created": int(time.time()), "model": model,
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10,
                              "total_tokens": 20}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        # BaseHTTPRequestHandler instances reach the wrapping server only via
        # self.server (the HTTPServer); expose the request journal on it.
        self.server.requests = self.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.port = self.server.server_address[1]

    @property
    def endpoint(self):
        # ProviderBridge requires the structured endpoint dict, not a URL string.
        return dict(scheme="http", host="127.0.0.1", port=self.port,
                    path_prefix="/v1")

    def start(self):
        self.thread.start()

    def close(self):
        # shutdown() deadlocks if serve_forever never started (early failure).
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()


async def execute_m06(rt, sample, config, initial_refs, observer):
    """Register both domains, start, drive; the observer collects originals."""
    from lore_runtime.bootstrap import assemble  # noqa: F401  (parity with M01)
    for obj, names in [(rt, ("open", "register", "start", "drive_until", "query", "close")),
                       (observer, ("begin", "collect_m06", "mark_accepting", "mark_finished"))]:
        if obj is None or any(not callable(getattr(obj, name, None)) for name in names):
            raise RuntimeError("MISSING: real Runtime or independent observer entry")
    cfg, refs = copy.deepcopy(config), copy.deepcopy(initial_refs)
    for key in ("harness_ref", "session_ref", "source_result_ref", "capability_ref",
                "surface_ref", "previous_session_ref", "execution_targets"):
        if key not in refs:
            raise ValueError("initial original reference missing: " + key)
    sid = sample["id"] + "-surface"
    wid = sample["id"] + "-workspace"
    request_id = sample["id"] + "-invocation"
    await observer.begin(sample, {"surface": sid, "workspace": wid})
    replies = {}
    opened = False
    failure = None
    accepting = False
    try:
        await rt.open()
        opened = True
        for domain, resource_id in (("surface", sid), ("workspace", wid)):
            replies[domain] = rt.register(
                cfg["registration_principal"],
                request_id=sample["id"] + "-register-" + domain,
                resource_id=resource_id, namespace=cfg["namespace"], kind=domain,
                path=sample[domain], harness_ref=refs["harness_ref"],
                grants=cfg["grants"])
        selector = {
            "namespace": cfg["namespace"], "source": cfg["principal"],
            "start_sequence": cfg["start_sequence"], "filters": cfg["filters"],
            "page_size": cfg["page_size"], "surface_ref": refs["surface_ref"],
            "previous_session_ref": refs["previous_session_ref"],
            "execution_targets": refs["execution_targets"],
        }
        request = {
            "id": request_id, "namespace": cfg["namespace"], "kind": "invocation",
            "payload": {
                "resource_id": sid, "resource_revision": replies["surface"]["revision"],
                "harness_ref": refs["harness_ref"], "input_ref": None,
                "input_binding": selector,
                **{key: refs[key] for key in
                   ("session_ref", "source_result_ref", "capability_ref")},
            },
        }
        deadline = time.monotonic() + 900
        observer.mark_accepting()
        accepting = True
        replies["accepted"] = rt.start(cfg["principal"], request)
        replies["drive"] = await asyncio.wait_for(
            rt.drive_until(cfg["principal"], request_id,
                           deadline_monotonic=deadline),
            timeout=deadline - time.monotonic())
        observer.mark_finished()
        accepting = False
        replies["query"] = rt.query(cfg["principal"], request_id)
    except Exception as error:
        failure = error
    finally:
        if accepting:
            observer.mark_finished()
        if opened:
            try:
                await rt.close()
            except Exception as error:
                if failure is None:
                    failure = error
    try:
        observations = await observer.collect_m06(sample, request_id)
    except Exception as error:
        observations = {"status": "FAIL",
                        "error": {"type": type(error).__name__, "message": str(error)}}
        if failure is None:
            failure = error
    if failure is not None:
        return {"id": sample["id"], "status": "FAIL",
                "error": {"type": type(failure).__name__, "message": str(failure)},
                "runtime_replies": replies, "observations": observations}
    return {"id": sample["id"], "status": observations.get("status", "FAIL"),
            "runtime_replies": replies, "observations": observations,
            "artifact": observations.get("artifact")}


async def one(sample, rows):
    from lore_runtime.bootstrap import assemble
    from validation.components.e.support import Server
    from validation.m06_browser.m06_observer import M06Observer
    out = Path(sample["surface"]).parent
    server, fixed, runtime = None, None, None
    result = dict(id=sample["id"], status="FAIL")
    started = time.monotonic()
    save(out / "start.json", dict(id=sample["id"], monotonic=started,
        wall_time=time.time(), pid=os.getpid(), fixed_responses=True))
    try:
        server = Server(out / "nats")
        fixed = FixedResponseServer()
        whole = configuration(sample, server.url, fixed.endpoint)
        save(out / "config.json", whole)
        observer = M06Observer(config={**whole, "observation": dict(
            expected_model=MODEL_ID, expected_model_alias=MODEL_ID)},
            output_dir=out / "observer")
        await server.start()
        fixed.start()
        runtime = assemble(whole, credential_provider=lambda: "public-owner-fixture",
                           checkpoint=observer.notify)
        call_config = dict(principal="operator", registration_principal="operator",
            namespace=sample["id"], grants={"operator": ["read", "write"]},
            page_size=16, start_sequence=1, filters={})
        save(out / "call-config.json", dict(config=call_config,
                                            initial_refs=runtime.initial_refs))
        result = await execute_m06(runtime, sample, call_config,
                                   runtime.initial_refs, observer)
        result["fixed_response_requests"] = len(fixed.requests)
    except Exception as error:
        result.update(status="FAIL",
                      error=dict(type=type(error).__name__, message=str(error)))
    finally:
        if runtime is not None and not runtime.closed:
            try:
                await runtime.close()
            except Exception as error:
                result.update(status="FAIL",
                              runtime_close_error=dict(type=type(error).__name__,
                                                       message=str(error)))
        for closer in (server,):
            if closer is not None:
                try:
                    closer.close()
                    if getattr(closer, "proc", None) is not None:
                        result["nats"] = dict(reaped=closer.proc.poll() is not None)
                        if not result["nats"]["reaped"]:
                            result["status"] = "FAIL"
                except Exception as error:
                    result.update(status="FAIL",
                                  close_error=dict(type=type(error).__name__,
                                                   message=str(error)))
        if fixed is not None:
            fixed.close()
        result["total_seconds"] = time.monotonic() - started
        save(out / "result.json", result)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--case")
    args = ap.parse_args()
    if not args.batch.replace("-", "").isalnum():
        ap.error("fresh batch id")
    # The sample/host trees must live on a Linux filesystem that preserves the
    # full F metadata contract (chown/utime/xattrs); virtiofs bind mounts of the
    # repo do not. LORE_M06_OUT points into the state volume (M01 pattern); the
    # runner copies the finished tree back into the repo afterwards.
    out = Path(os.environ.get("LORE_M06_OUT",
              str(ROOT / "validation/m06_browser/evidence"))) / args.batch
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / "validation/m06_browser"))
    from m06 import prepare_samples
    samples = prepare_samples(out)
    if args.case:
        samples = [s for s in samples if s["class"] == args.case]
        if not samples:
            ap.error("no samples for class " + args.case)
    rows = []

    async def run_all():
        for sample in samples:
            rows.append(await one(sample, rows))
            print(json.dumps({"id": rows[-1]["id"], "status": rows[-1]["status"]},
                             ensure_ascii=False), flush=True)

    asyncio.run(run_all())
    passed = sum(1 for r in rows if r["status"] == "PASS")
    summary = dict(status="PASS" if passed == len(samples) and len(samples) == 9 else "FAIL",
                   passed=passed, cases=len(samples), rows=rows)
    save(out / "assessment.json", summary)
    print(json.dumps({"status": summary["status"], "passed": passed,
                      "cases": len(samples)}))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
