"""Preregistered budget-admission counterexamples; real R + ProviderBridge + localhost.

Protocol: validation/provider_budget/admission-protocol.json. Cases PBO-01..
PBO-07. The same probe run against the unfixed implementation must fail PBO-01
(the recorded m01-real-005 blocker shape) while preserving the unchanged
behaviors; after the recorded fix the whole set must pass. This probe never
establishes M01 PASS and never contacts a real model.
"""
import argparse
import copy
import hashlib
import http.server
import importlib
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMITS = dict(max_requests=6, max_input_tokens=15360,
              max_output_tokens_per_request=2048, max_request_body_bytes=15360, max_seconds=300)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def need(value, message):
    if not value:
        raise AssertionError(message)


class CaseAbort(Exception):
    """Stops later cases after one case already recorded its failure."""


def rejected(function):
    try:
        function()
    except Exception as error:
        return getattr(error, "code", getattr(error, "reason", type(error).__name__))
    raise AssertionError("expected rejection")


def worker(out):
    sys.path.insert(0, str(ROOT))
    from lore_control import ControlStore
    from lore_provider.request import SHELL
    try:
        from lore_runtime.provider_owner import (ProviderOwner, common_prefix_length,
                                                 projected_request_tokens)
        functions = dict(common=common_prefix_length, projected=projected_request_tokens)
    except ImportError:
        # Before the recorded fix these pure functions do not exist; PBO-06 is
        # then recorded as NOT_RUN_BEFORE_FIX and the pure-function properties
        # cannot mask the admission behavior under test.
        functions = None
    from lore_session.provider import ProviderBridge
    from lore_runtime.session_plan_files import compact

    href = {"owner": "F", "sha256": "a" * 64}
    cap = {"owner": "F", "sha256": "b" * 64}
    control = ControlStore(out / "R.sqlite",
                           {"runtime": {"namespaces": ["n"], "roles": ["runtime", "submit", "admin"]}},
                           reference_checker=lambda ref, purpose, expected: purpose == "harness" and ref == href)
    calls = []
    script = {"phase": "idle", "index": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            index = script["index"]
            script["index"] += 1
            phase = script["phase"]
            body_items = []
            if phase == "normal":
                prompt = script["usage"].pop(0)
            elif phase == "overflow":
                prompt = script["usage"].pop(0)
            elif phase == "truncate":
                prompt = 40
            else:
                prompt = 10
            message = dict(role="assistant", content="step response " + str(index))
            body = json.dumps(dict(id="response-" + str(index), object="chat.completion", created=0,
                                   model="deepseek-v4-flash",
                                   choices=[dict(index=0, message=message, finish_reason="stop")],
                                   usage=dict(prompt_tokens=prompt, completion_tokens=2,
                                              total_tokens=prompt + 2))).encode()
            with control._lock:
                all_rows = [dict(row) for row in control.db.execute(
                    "SELECT * FROM requests WHERE kind='provider_transport'")]
                matches = [row for row in all_rows
                    if json.loads(row["payload_json"]).get("request_sha256") == sha(raw)]
            import os as _os
            if _os.environ.get("PROBE_DEBUG") and (len(matches) != 1 or matches[0]["phase"] != "issued"):
                print("HANDLER DEBUG raw_len", len(raw), "sha", sha(raw)[:12],
                      "rows", [(r["id"][:24], r["phase"],
                                json.loads(r["payload_json"]).get("request_sha256", "")[:12])
                               for r in all_rows], flush=True)
            need(len(matches) == 1 and matches[0]["phase"] == "issued",
                 "HTTP entered before original R dispatch")
            calls.append(dict(index=index, phase=phase, request_sha256=sha(raw),
                              response_sha256=sha(body), request_bytes=len(raw),
                              R_request_id=matches[0]["id"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            if phase == "truncate":
                # Declared length exceeds the body; the connection then closes,
                # so the saved transport is genuinely incomplete (status UNKNOWN).
                self.send_header("Content-Length", str(len(body) + 4096))
                self.end_headers()
                self.wfile.write(body)
                self.connection.close()
                return
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    endpoint = dict(scheme="http", host="127.0.0.1", port=server.server_port)
    root = out / "provider"
    rows = []
    old_shape = new_shape = detail_pbo06 = None

    def key():
        return "public-owner-fixture"

    owners = []

    def owner(limits=None):
        value = Owner(control, root, endpoint, principal="runtime", budget=limits or copy.deepcopy(LIMITS),
                      credential_provider=key, timeout=5)
        owners.append(value)
        return value

    def reference(ref, purpose, expected):
        if purpose == "receipt":
            return any(value.control_reference(ref, purpose, expected) for value in owners)
        return purpose == "harness" and ref == href

    control.reference_checker = reference

    def scope_and_frame(name, entry, system_size, step_count, pad=300):
        operation = "op-" + name
        if control.db.execute("SELECT 1 FROM requests WHERE id=?", (operation,)).fetchone() is None:
            control.accept("runtime", dict(id=operation, namespace="n", kind="invocation",
                                           payload=dict(harness_ref=href, capability_ref=cap, source_result_ref=None)))
            claimed = control.claim("worker-" + name, time.monotonic())
            need(claimed["id"] == operation, "fixture fair claim order")
        scope = dict(session_id=name, operation_id=operation, response_entry_id=entry,
                     session_scope=dict(namespace="n", surface_id="surface", session_id=name,
                                        session_generation=1),
                     harness_ref=compact(href), capability_ref=compact(cap),
                     input_ref=dict(id="input-" + name, sha256="c" * 64), source_result_ref=None)
        effect = "s-provider-" + sha(json.dumps([scope["session_scope"], operation, entry],
                                                ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode())
        messages = [dict(role="user", content="goal " + name + " " + "U" * system_size)]
        for step in range(step_count):
            # Assistant turns carry one native shell call so the following
            # toolResult has its original pending id, exactly as the real
            # protocol pairs them.
            messages.append(dict(role="assistant", timestamp=step,
                                 content=[dict(type="text", text="A" * pad),
                                          dict(type="toolCall", id="call-" + str(step), name="shell",
                                               arguments=dict(target="workspace", script="echo " + str(step)))]))
            messages.append(dict(role="toolResult", toolCallId="call-" + str(step), toolName="shell",
                                 content="T" * pad, isError=False))
            # The entry id rides on the LAST user text: the wire JSON carries no
            # response entry identity, so without it two entries of one session
            # would produce byte-identical requests and the handler's
            # one-issued-row check could not tell them apart. Keeping the id at
            # the end also preserves the real M01 shape where the request prefix
            # (template plus history) stays shared and only the new step diverges.
            messages.append(dict(role="user", content="S" * pad + "-" + entry))
        frame = dict(type="provider.request", session_id=name, operation_id=operation,
                     response_entry_id=entry, effect_id=effect,
                     payload=dict(systemPrompt="P" * system_size, messages=messages, tools=[SHELL]))
        return scope, frame

    def record(name, function):
        try:
            detail = function()
            rows.append(dict(id=name, status="PASS", detail=detail))
        except Exception as error:
            rows.append(dict(id=name, status="FAIL", error=repr(error)))
            raise

    Owner = importlib.import_module("lore_runtime.provider_owner").ProviderOwner
    try:
        # PBO-05 first-request fallback: no rows, byte cap enforced (unchanged shape).
        first_owner = owner(dict(LIMITS, max_input_tokens=1024, max_request_body_bytes=1024,
                                 max_output_tokens_per_request=64))
        script["phase"] = "normal"
        script["usage"] = [10]
        scope_f, frame_f = scope_and_frame("FIRST", "e1", 120, 0)
        value = first_owner.complete(scope_f, frame_f)
        need(value["status"] == "RECEIVED" and value["wire"]["accepted"], "first request within cap must be admitted")
        scope_f2, frame_f2 = scope_and_frame("FIRST2", "e1", 1200, 0)
        reason = rejected(lambda: first_owner.complete(scope_f2, frame_f2))
        need(reason == "budget_exceeded", "first request over the fixed body cap must stay rejected")
        rows.append(dict(id="PBO-05", status="PASS",
                         detail="first request fallback: in-cap admitted, over-body-cap budget_exceeded"))

        # PBO-04 request count exhausted (unchanged).
        count_owner = owner(dict(LIMITS, max_requests=2, max_input_tokens=4000))
        script["usage"] = [100, 100, 100, 100, 100, 100]
        scopes_c = [scope_and_frame("COUNT", "e" + str(i), 120, 1) for i in range(1, 4)]
        count_owner.complete(scopes_c[0][0], scopes_c[0][1])
        count_owner.complete(scopes_c[1][0], scopes_c[1][1])
        reason = rejected(lambda: count_owner.complete(scopes_c[2][0], scopes_c[2][1]))
        need(reason == "budget_exceeded", "request count must stay exhausted at the cap")
        rows.append(dict(id="PBO-04", status="PASS",
                         detail="request count cap still exhausts the scope"))

        # PBO-03 unresolved usage blocks admission (unchanged).
        script["phase"] = "truncate"
        script["usage"] = [40, 40, 40, 40, 40, 40]
        unres_owner = owner()
        scope_u1, frame_u1 = scope_and_frame("UNRES", "e1", 120, 1)
        value = unres_owner.complete(scope_u1, frame_u1)
        need(value["status"] == "UNKNOWN" and not value["wire"]["transport"]["complete"],
             "truncated transport must stay UNKNOWN")
        scope_u2, frame_u2 = scope_and_frame("UNRES", "e2", 120, 2)
        reason = rejected(lambda: unres_owner.complete(scope_u2, frame_u2))
        need(reason == "budget_unknown", "unresolved original usage must stay blocking")
        rows.append(dict(id="PBO-03", status="PASS",
                         detail="truncated transport stays UNKNOWN and blocks the next admission"))

        # PBO-02 genuine overflow stays rejected.
        script["phase"] = "overflow"
        script["usage"] = [2900] * 6
        over_owner = owner()
        scopes_o = [scope_and_frame("OVER", "e" + str(i), 60, 1, pad=120) for i in range(1, 7)]
        for index in range(5):
            value = over_owner.complete(scopes_o[index][0], scopes_o[index][1])
            need(value["status"] == "RECEIVED", "overflow setup step must be received")
        reason = rejected(lambda: over_owner.complete(scopes_o[5][0], scopes_o[5][1]))
        need(reason == "budget_exceeded", "genuine projected overflow must stay rejected")
        rows.append(dict(id="PBO-02", status="PASS",
                         detail="genuine projected overflow still rejected under the projection rule"))

        # PBO-01 the recorded blocker shape: five received steps at 1200 tokens
        # each, then a sixth request whose full body bytes no longer fit under
        # the byte-as-token reservation. Steps sized so the old rule admits
        # 1-5 and blocks exactly the legitimate sixth step; the recorded fix
        # must admit the sixth and finish with real totals below the budget.
        script["phase"] = "normal"
        script["usage"] = [1200, 1200, 1200, 1200, 1200, 1250]
        m01_owner = owner()
        pairs = [scope_and_frame("M01", "e" + str(i), 2200, i - 1) for i in range(1, 7)]
        for index in range(5):
            value = m01_owner.complete(pairs[index][0], pairs[index][1])
            need(value["status"] == "RECEIVED", "blocker setup step must be received")
        bridge = ProviderBridge(root, endpoint, dict(model="deepseek-v4-flash", max_completion_tokens=2048,
                                session_scope=pairs[0][0]["session_scope"],
                                input_ref=pairs[0][0]["input_ref"], harness_ref=pairs[0][0]["harness_ref"],
                                capability_ref=pairs[0][0]["capability_ref"]), timeout=5)
        prepared5, _, raw5 = bridge._prepared(pairs[4][0], pairs[4][1])
        prepared6, _, raw6 = bridge._prepared(pairs[5][0], pairs[5][1])
        used = 5 * 1200
        old_shape = dict(body5=len(raw5), body6=len(raw6), used_before=used,
                         old_rule_sum=used + len(raw6))
        need(len(raw5) + 4 * 1200 <= LIMITS["max_input_tokens"],
             "fixture sizing: old rule must have admitted steps 1-5")
        need(used + len(raw6) > LIMITS["max_input_tokens"],
             "fixture sizing: sixth body must exceed the old byte reservation")
        new_shape = None
        if functions is not None:
            common = functions["common"](raw5, raw6)
            bound = functions["projected"](1200, common, len(raw6))
            new_shape = dict(common_bytes=common, projected_bound=bound,
                             projected_total=used + bound)
            need(used + bound <= LIMITS["max_input_tokens"],
                 "fixture sizing: recorded fix must admit the sixth step")
        try:
            value = m01_owner.complete(pairs[5][0], pairs[5][1])
            need(value["status"] == "RECEIVED" and value["wire"]["accepted"],
                 "recorded blocker shape must complete after the fix")
        except Exception as error:
            # Before the recorded fix this exact rejection IS the blocker
            # evidence; record it as the PBO-01 case result and stop here.
            rows.append(dict(id="PBO-01", status="FAIL", error=repr(error),
                             code=getattr(error, "code", None),
                             detail="legitimate sixth step rejected before the fix"))
            raise CaseAbort from error
        total, _ = Owner._usage(m01_owner, m01_owner._records(pairs[0][0]["session_scope"]))
        need(total == 5 * 1200 + 1250 and total <= LIMITS["max_input_tokens"],
             "actual cumulative usage must stay under the budget after six steps")
        rows.append(dict(id="PBO-01", status="PASS",
                         detail=dict(recorded_blocker_shape=old_shape,
                                     fix_admission_bound=new_shape, actual_total_tokens=total)))

        # PBO-06 projection properties on the pure functions (after fix only;
        # before the fix the PBO-01 rejection above already ends the run).
        margin = 64
        a, b = b"same-prefix-alpha", b"same-prefix-alpha"
        need(projected_request_tokens(900, common_prefix_length(a, b), len(b)) == 900 + margin,
             "identical bodies project tokens_last plus margin only")
        a, b = b"same-prefix", b"same-prefix-plus-tail"
        need(projected_request_tokens(900, common_prefix_length(a, b), len(b)) == 900 + 10 + margin,
             "append-only growth projects the byte delta")
        a, b = b"same-prefix-AAAtail", b"same-prefix-BBBtail"
        bound = projected_request_tokens(900, common_prefix_length(a, b), len(b))
        need(bound >= 900 + margin and bound <= 900 + len(b) + margin,
             "equal-byte rewrite inflates the bound but stays byte-bounded")
        a, b = b"short-but-was-long", b"short"
        need(projected_request_tokens(900, common_prefix_length(a, b), len(b)) == 900 + margin,
             "shrinking body inside a shared prefix projects tokens_last plus margin only")
        a, b = b"totally", b"different"
        need(projected_request_tokens(900, common_prefix_length(a, b), len(b)) == 900 + len(b) + margin,
             "unrelated bodies project the full new byte span plus margin")
        # Recorded m01-real-005 shape: 7140 actual tokens used, a 9886-byte
        # sixth request whose last 1500 bytes are new (template + history are
        # shared with the fifth request).
        recorded = projected_request_tokens(1900, common_prefix_length(
            b"P" * 8386, b"P" * 8386 + b"T" * 1500), 9886)
        need(recorded == 1900 + 1500 + margin and 7140 + recorded <= 15360 and 7140 + 9886 > 15360,
             "recorded m01-real-005 shape: new rule admits, old reservation blocked")
        detail_pbo06 = dict(margin=margin, recorded_shape_bound=recorded)
        rows.append(dict(id="PBO-06", status="PASS", detail=detail_pbo06))
    except CaseAbort:
        pass
    except Exception as error:
        # Case failures are recorded by record(); any setup error is recorded
        # here so the report always reaches evidence, then reported as FAIL.
        import traceback
        rows.append(dict(id="WORKER", status="FAIL", error=repr(error),
                         traceback=traceback.format_exc()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
        save(out / "http.json", calls)
        control.close()
    before_run = functions is None
    blocker_reproduced = any(c["id"] == "PBO-01" and c["status"] == "FAIL"
                             and (c.get("code") == "budget_exceeded"
                                  or "budget_exceeded" in (c.get("error") or ""))
                             for c in rows)
    non_worker = [c for c in rows if c["id"] != "WORKER"]
    all_pass = (len(non_worker) == 6 and all(c["status"] == "PASS" for c in non_worker)
                and not thread.is_alive())
    if all_pass:
        interpretation = "AFTER_FIX_EVIDENCE: all PBO cases pass against the current source"
    elif blocker_reproduced and not all_pass:
        interpretation = "BEFORE_FIX_EVIDENCE: the recorded m01 blocker (budget_exceeded on the legitimate sixth step) is reproduced under the old admission rule"
    else:
        interpretation = "UNEXPECTED: neither the expected before-fix blocker nor a full pass"
    result = dict(status="PASS" if all_pass else "FAIL",
                  blocker_reproduced=blocker_reproduced,
                  interpretation=interpretation,
                  cases=rows, HTTP=len(calls),
                  pbo06=detail_pbo06,
                  pbo01_shape=dict(old=old_shape, new=new_shape),
                  thread_stopped=not thread.is_alive(),
                  scope="real R/ProviderBridge localhost only; not real-model M01 evidence")
    save(out / "actual.json", result)
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch")
    parser.add_argument("--worker", type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    assert args.batch and args.batch == Path(args.batch).name, "fresh batch id required"
    out = ROOT / "validation/provider_budget/evidence" / args.batch
    out.mkdir(parents=True, exist_ok=False)
    target = ROOT / "lore_runtime/provider_owner.py"
    workspace = out / "workspace"
    files = [Path(__file__), target, ROOT / "lore_runtime/session_plan_files.py",
             ROOT / "lore_provider/request.py", ROOT / "lore_provider/transport.py",
             ROOT / "lore_execution/profile.json",
             ROOT / "validation/provider_budget/admission-protocol.json"]
    for folder in ["lore_control", "lore_session", "lore_provider", "lore_files", "lore_execution"]:
        files.extend(sorted((ROOT / folder).glob("*.py")))
    sources = []
    for source in files:
        destination = workspace / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        sources.append(dict(original=str(source), sha256=sha(source.read_bytes())))
    save(out / "sources.json", sources)
    actual = out / "actual"
    actual.mkdir()
    command = [sys.executable, "-B", str(workspace / Path(__file__).relative_to(ROOT)),
               "--worker", str(actual)]
    process = subprocess.run(command, cwd=workspace,
                             env=dict(PATH="/usr/bin:/bin:/usr/sbin", LANG="C.UTF-8",
                                      PYTHONDONTWRITEBYTECODE="1"),
                             capture_output=True, timeout=120)
    (out / "stdout").write_bytes(process.stdout)
    (out / "stderr").write_bytes(process.stderr)
    same = all(sha(Path(v["original"]).read_bytes()) == v["sha256"] for v in sources)
    result = dict(status="PASS" if process.returncode == 0 and same else "FAIL",
                  exit_code=process.returncode, source_unchanged=same, source_count=len(sources))
    save(out / "result.json", result)
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
