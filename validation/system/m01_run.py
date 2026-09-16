"""Finite M01 assembly: prepare by default; --execute-real runs the six originals.

Uses actual working-tree imports, with before copies and after hashes. It does
not claim execution from the copies. No fixed-response path can pass real M01.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from validation.system.m01 import (prepare_samples, execute_sample, save, sha,
                                    INPUTS, CASES, CONTRACT)
PROFILE = ROOT / "validation/profiles/openai-proxy.json"
ORIGINAL_HOST = ROOT / "validation/session-plan-evidence/context-independent-001/workspace/original-host"
MARKDOWN = ROOT / "validation/system/dependencies/markdown-001/manifest.json"
LIMITS = dict(model_responses=24, steps=24, response_tokens=16384,
              total_input_tokens=49152, seconds=1800)
PRODUCTS = ("lore_control", "lore_events", "lore_execution", "lore_files",
            "lore_provider", "lore_session", "lore_runtime", "harnesses")


def fact(path):
    path = Path(path).absolute()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def parser_dependencies():
    """Use the already accepted parser snapshot; no install or alternate parser."""
    manifest = json.loads(MARKDOWN.read_text())
    files = []
    for package in manifest["packages"]:
        for row in package["sources"] + package["licenses"]:
            path = ROOT / row["snapshot"]
            if sha(path) != row["sha256"]:
                raise RuntimeError("fixed artifact parser source/notice changed")
            files.append(path)
    location = MARKDOWN.parent / "source"
    sys.path.insert(0, str(location))
    for package in manifest["packages"]:
        module = importlib.import_module(package["module"])
        if not Path(module.__file__).resolve().is_relative_to(location):
            raise RuntimeError("artifact parser imported outside fixed source")
        if module.__version__ != package["version"]:
            raise RuntimeError("artifact parser version changed")
    return files


def configuration(sample, url, endpoint):
    """Same concrete bootstrap profile as the independently tested assembly."""
    from lore_runtime.startup_assets import CODE_FILES
    out = Path(sample["surface"]).parent
    host = out / "host"
    principal, namespace = "operator", sample["id"]
    authority = {principal: dict(namespaces=[namespace], roles=["admin", "runtime", "submit"])}
    deps = ORIGINAL_HOST / "dependencies-manifest.json"
    dm = json.loads(deps.read_text())
    # Bounded-context archive contract (m01-output-budget amendment 2026-09-14).
    # context_tokens is expressed in pi's chars/4 estimate and must stay below
    # the wire admission boundary (49152 real input tokens / 65536 body bytes).
    # 2026-09-14 (m01-output-budget amendment, batch-ae counterexample; the
    # raise was once reverted by a concurrent workspace write and re-applied
    # after batch-ak): fire-at 8192 keeps a workable working memory while the
    # growth stays far below the wire admission boundary. Old values
    # (16384/13312/1024/1536, fire-at 3072) retained in the amendment record.
    # 2026-09-16 (envelope alignment, user decision "现规模为准"): context_tokens
    # aligned to the wire-reachable scale (65536 body bytes / 4 chars-per-token
    # = 16384); reserve_tokens 40960->8192 keeps the fire-at threshold at 8192
    # so all existing criteria semantics are unchanged. Old values
    # (49152/40960) retained in the amendment record. M06's ARCHIVE pending
    # the same alignment + its own re-run (registered follow-up).
    archive = dict(context_tokens=16384, reserve_tokens=8192,
                   tail_reserve_tokens=4096, soft_tokens=8192)
    model = dict(id="glm-5.3", name="glm-5.3", api="lore-stdio",
                 provider="lore-provider", reasoning=False, input=["text", "image"],
                 cost=dict(input=0, output=0, cacheRead=0, cacheWrite=0),
                 contextWindow=archive["context_tokens"], maxTokens=16384)
    startup = dict(principal=principal, namespace=namespace,
        sources={d: dict(path=sample[d], resource_id=sample["id"] + "-" + d)
                 for d in ("surface", "workspace")},
        code_sources={name: fact(ROOT / name) for name in CODE_FILES},
        profile_ref=fact(ORIGINAL_HOST / "profile.json"),
        request_template_ref=fact(ORIGINAL_HOST / "request-template.json"),
        deps_mount=dict(role="dependencies", source=dm["root"], target="/opt",
                        read_only=True, manifest_ref=fact(deps), content_ref=dm["source_ref"]),
        model=model, capability_limits=dict(max_steps=24, archive=archive))
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
    # Cumulative input budget derived from the admitted chain shape
    # (m01-output-budget amendment, batch-ai counterexample): threshold
    # archiving extends real chains to 14-17 invocations; the cumulative
    # cap was sized for the pre-archive 5-8 call shape. Derived from existing
    # constants: max_requests (24) x max_request_body_bytes / 4 (chars per
    # token) = 24 x 16384 = 393216. Old value 49152 retained in the record.
    budget = dict(max_requests=24, max_input_tokens=393216,
        max_output_tokens_per_request=16384, max_request_body_bytes=65536, max_seconds=1800,
        reasoning_effort="medium")
    return dict(runtime=runtime, startup_root=str(host), startup=startup,
        provider=dict(root=str(out / "provider"), endpoint=endpoint, principal=principal,
                      timeout=300, budget=budget),
        initial_session_ref=initial)


def source_paths(parser_files):
    paths = {p for name in PRODUCTS for p in (ROOT / name).rglob("*")
             if p.is_file() and p.suffix in (".py", ".mts")}
    paths.update(parser_files)
    paths.update((ROOT / "validation/system").glob("*.py"))
    paths.update([INPUTS, CASES, CONTRACT, PROFILE, MARKDOWN,
        ROOT / "design/g3/system/entry-contract.md",
        ROOT / "design/g3/system/artifact-oracle-contract.md",
        ROOT / "design/g3/system/runtime-observer.md",
        ROOT / "validation/components/s/oracle.py", ROOT / "validation/components/e/support.py",
        ROOT / "validation/runtime_assembly_probe.py"])
    paths.update(ORIGINAL_HOST / name for name in
                 ("profile.json", "request-template.json", "dependencies-manifest.json"))
    import nats
    paths.update(Path(nats.__file__).parent.rglob("*.py"))
    return sorted(paths)


def capture(out, paths):
    rows = []
    for index, path in enumerate(paths):
        raw = path.read_bytes()
        target = out / "source-before" / (str(index) + "-" + path.name)
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw)
        rows.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                         bytes=len(raw), copy=str(target)))
    save(out / "source-before.json", dict(actual_import_scope="shared working tree, not copied execution",
        interpreter=sys.executable, pid=os.getpid(), files=rows,
        large_dependencies="Existing fixed dependency manifest/profile referenced; not recopied"))
    return rows


def unchanged(rows):
    changed = [row["path"] for row in rows if not Path(row["path"]).is_file()
               or sha(row["path"]) != row["sha256"]]
    recorded = {row["path"] for row in rows}
    current = {str(p) for name in PRODUCTS for p in (ROOT / name).rglob("*")
               if p.is_file() and p.suffix in (".py", ".mts")}
    current.update(str(p) for p in (ROOT / "validation/system").glob("*.py"))
    return sorted(set(changed) | (current - recorded))


class MissingEntry(RuntimeError):
    pass


def require_entries():
    # Class/function inspection only, before any Server or Runtime construction.
    try:
        from lore_runtime.bootstrap import assemble
        from validation.system.runtime_observer import Observer
        from validation.components.e.support import BINARY, BINARY_SHA
        if not callable(assemble) or sha(BINARY) != BINARY_SHA:
            raise ValueError("fixed bootstrap/NATS identity unavailable")
        for name in ("begin", "collect_m01", "notify", "mark_accepting", "mark_finished"):
            if not callable(getattr(Observer, name, None)):
                raise ValueError("Observer." + name + " is missing")
    except (ImportError, OSError, ValueError) as error:
        raise MissingEntry(str(error)) from error


def assess(value):
    """All original groups plus content; a Runtime query is never an oracle."""
    observed = value.get("observations", {})
    checks = observed.get("checks", [])
    groups = {c.get("group") for c in checks if isinstance(c, dict)}
    return (value.get("status") == "UNVERIFIED_PENDING_INTEGRATION_ORACLE"
        and observed.get("status") == "PASS"
        and {"O" + str(i) for i in range(1, 9)}.issubset(groups)
        and bool(checks) and all(isinstance(c, dict) and c.get("passed") is True for c in checks)
        and value.get("artifact_content", {}).get("passed") is True)


async def one(sample, endpoint, credential_provider, rows):
    from lore_runtime.bootstrap import assemble
    from validation.components.e.support import Server
    from validation.system.runtime_observer import Observer
    out = Path(sample["surface"]).parent
    server, runtime = None, None
    result = dict(id=sample["id"], status="FAIL")
    started = time.monotonic()
    save(out / "start.json", dict(id=sample["id"], monotonic=started,
        wall_time=time.time(), pid=os.getpid(), real_model=True))
    try:
        if unchanged(rows):
            raise RuntimeError("source changed before sample; no execution allowed")
        server = Server(out / "nats")
        whole = configuration(sample, server.url, endpoint)
        save(out / "config.json", whole)
        # New-baseline observation protocol (amendment-model-baseline-2026-09-15):
        # the batch under the switched baseline declares its expected wire model
        # scope; O7 asserts against this declaration, not batch z's glm-5.3
        # instrument. Lives only in the observer's config view; `whole` (the
        # assemble contract) stays byte-identical to the fixed owner schema.
        observer = Observer(config={**whole, "observer_seconds": LIMITS["seconds"] + 100, "observation": dict(
            expected_model="deepseek-v4-flash",
            expected_model_alias="deepseek-v4-flash-ga-260731")},
            output_dir=out / "observer")
        for method in ("begin", "collect_m01", "notify", "mark_accepting", "mark_finished"):
            if not callable(getattr(observer, method, None)):
                raise RuntimeError("MISSING: Observer." + method)
        await server.start()
        runtime = assemble(whole, credential_provider=credential_provider, checkpoint=observer.notify)
        # assemble does not register R; execute_sample owns the original request IDs.
        call_config = dict(principal="operator", registration_principal="operator",
            namespace=sample["id"], grants={"operator": ["read", "write"]},
            page_size=16, start_sequence=1, filters={})
        save(out / "call-config.json", dict(config=call_config, initial_refs=runtime.initial_refs))
        result = await execute_sample(runtime, sample, call_config, runtime.initial_refs, observer)
        result["status"] = "PASS" if assess(result) else "FAIL"
    except Exception as error:
        result.update(status="FAIL", error=dict(type=type(error).__name__, message=str(error)))
    finally:
        # execute_sample closes Runtime clients and collects before this server stops.
        # Also close a constructed but not opened Runtime after a begin/open failure.
        if runtime is not None and not runtime.closed:
            try:
                await runtime.close()
            except Exception as error:
                result.update(status="FAIL", runtime_close_error=dict(type=type(error).__name__, message=str(error)))
        if server is not None:
            try:
                server.close()
                result["nats"] = dict(lifecycle=server.lifecycle,
                    pid=None if server.proc is None else server.proc.pid,
                    reaped=server.proc is not None and server.proc.poll() is not None)
                if server.proc is not None and not result["nats"]["reaped"]:
                    result["status"] = "FAIL"
            except Exception as error:
                result.update(status="FAIL", close_error=dict(type=type(error).__name__, message=str(error)))
        changed = unchanged(rows)
        result["source_changed"] = changed
        if changed:
            result["status"] = "FAIL"
        result["total_with_setup_and_observation_seconds"] = time.monotonic() - started
        save(out / "finish.json", dict(monotonic=time.monotonic(), wall_time=time.time(),
            id=sample["id"], status=result["status"], source_changed=changed))
        save(out / "result.json", result)
    return result


async def real_samples(samples, endpoint, credential_file, rows):
    def credential_provider():
        # Trusted project-external lazy callback. Never copied, logged or sent to Node.
        return Path(credential_file).read_text(encoding="utf-8").strip()
    results = []
    stopped = False
    for sample in samples:
        if stopped:
            value = dict(id=sample["id"], status="NOT_RUN_AFTER_FAILURE",
                         reason="No automatic retry or further effects after the first failed sample")
            save(Path(sample["surface"]).parent / "result.json", value)
            save(Path(sample["surface"]).parent / "finish.json",
                 dict(id=sample["id"], status="NOT_RUN_AFTER_FAILURE", actually_started=False))
        else:
            value = await one(sample, endpoint, credential_provider, rows)
            stopped = value["status"] != "PASS"
        results.append(value)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", help="one fresh evidence directory name")
    parser.add_argument("--execute-real", action="store_true", help="run the original six real samples; no retries")
    args = parser.parse_args()
    if args.batch in ("", ".", "..") or Path(args.batch).name != args.batch:
        parser.error("batch must be one fresh directory name")
    # 2026-09-14: F capture windows need xattr support and X bind-mounts readonly
    # sources from daemon-visible paths; honor a volume-backed evidence root
    # mounted at its daemon-visible path (amendment-platform-revision-2026-09-14).
    out_root = (Path(os.environ["LORE_RUNTIME_OUT"]) if os.environ.get("LORE_RUNTIME_OUT")
                else ROOT / "validation/system/evidence")
    out = out_root / args.batch
    out.mkdir(parents=True, exist_ok=False)
    result = dict(case="M01", status="MISSING", exit_code=2, planned_real_samples=6,
        attempted_runtime_samples=0, passed_samples=0, original_per_sample_limits=LIMITS,
        fixed_response_wiring="Separate runtime_assembly_probe evidence; never real-model M01",
        real_model="glm-5.3", actual_execution="none", samples=[])
    rows = []
    try:
        parser_files = parser_dependencies()
        rows = capture(out, source_paths(parser_files))
        profile = json.loads(PROFILE.read_text())
        url = urlsplit(profile["endpoint"])
        if (url.scheme not in ("http", "https") or not url.hostname or url.username
                or url.password or url.path != profile["api_base_path"] or url.query or url.fragment
                or profile["api_base_path"] != "/api/plan/v3" or profile["provider_model"] != "glm-5.3"):
            raise ValueError("fixed public proxy profile differs")
        endpoint = dict(scheme=url.scheme, host=url.hostname,
                        port=url.port or (443 if url.scheme == "https" else 80),
                        path_prefix=url.path)
        credential_file = Path(profile["credential_file"])
        if not credential_file.is_absolute() or credential_file.is_relative_to(ROOT):
            raise ValueError("credential must remain in the fixed project-external location")
        samples = prepare_samples(out)
        save(out / "samples.json", samples)
        for sample in samples:
            save(Path(sample["surface"]).parent / "config-planned.json",
                 configuration(sample, "nats://127.0.0.1:0", endpoint))
        result["samples"] = samples
        if args.execute_real:
            require_entries()
            result["actual_execution"] = "shared working-tree source, original real proxy"
            result["samples"] = asyncio.run(real_samples(samples, endpoint, credential_file, rows))
            result["attempted_runtime_samples"] = sum(s["status"] != "NOT_RUN_AFTER_FAILURE" for s in result["samples"])
            result["passed_samples"] = sum(s["status"] == "PASS" for s in result["samples"])
            result["status"] = "PASS" if result["passed_samples"] == 6 else "FAIL"
            result["exit_code"] = 0 if result["status"] == "PASS" else 1
        else:
            result["missing_connections"] = ["Explicit actual run not performed; independent Observer acceptance and main-chain gate required before execution"]
    except MissingEntry as error:
        result["missing_connections"] = [str(error)]
        result["status"], result["exit_code"] = "MISSING", 2
    except Exception as error:
        result["error"] = dict(type=type(error).__name__, message=str(error))
        result["status"], result["exit_code"] = ("FAIL", 1) if args.execute_real else ("MISSING", 2)
    changed = unchanged(rows)
    save(out / "source-after.json", dict(changed=changed, unchanged=bool(rows) and not changed,
        files=[dict(path=row["path"], sha256=sha(row["path"]) if Path(row["path"]).is_file() else None) for row in rows]))
    if changed and args.execute_real:
        result["status"], result["exit_code"] = "FAIL", 1
    result["source_changed"] = changed
    save(out / "result.json", result)
    print(json.dumps({k: result[k] for k in ("status", "exit_code", "planned_real_samples",
        "attempted_runtime_samples", "passed_samples")}, ensure_ascii=False))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
