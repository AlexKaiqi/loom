"""M01 fixed six-sample entry. Artifact checks are not end-to-end acceptance.

The integration API is defined in design/g3/system/entry-contract.md.
The default CLI prepares fixtures and exits 2 without starting any facilities.
Explicit --execute-real uses the existing bootstrap and independent observer.
Runtime replies alone never establish sample PASS.
"""
import asyncio
import copy
import time
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "design/g3/system/inputs.json"
CASES = ROOT / "design/g3/system/cases.json"
CONTRACT = ROOT / "design/g3/system/contract.md"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare_samples(out):
    """Only the original v5 and seeded inputs, three separate real-run fixtures each."""
    source = json.loads(INPUTS.read_text())
    rows = json.loads(CASES.read_text())["cases"]
    if len([row for row in rows if row["id"] == "M01"]) != 1:
        raise ValueError("missing or duplicate original M01 case")
    samples = []
    for name in ("v5", "seeded"):
        values = source["integer_inputs"][name]
        if not isinstance(values, list) or any(type(x) is not int for x in values):
            raise ValueError("original integer fixture is invalid")
        raw = (json.dumps(values, ensure_ascii=False) + "\n").encode()
        for repeat in range(1, 4):
            sample_id = f"M01-{name}-{repeat}"
            base = out / sample_id
            surface = base / "surface"
            workspace = base / "workspace"
            original = base / "observer-original" / "numbers.json"
            (surface / "blocks").mkdir(parents=True)
            workspace.mkdir()
            original.parent.mkdir()
            original.write_bytes(raw)
            original.chmod(0o444)
            (workspace / "numbers.json").write_bytes(raw)
            (surface / "surface.md").write_text(
                "# Working surface\n\n"
                "Read the goal in blocks/goal.md and the working notes in blocks/notes.md.\n"
            )
            (surface / "blocks/goal.md").write_text(
                "Read numbers.json in the authorized Workspace. Compute its integer sum "
                "and write report.json there. Use the authorized Runtime working "
                "environment to update blocks/notes.md with an actual Markdown link "
                "to the accessible historical report location. Submit one authorized "
                "application notification through the provided thin emit facility, "
                "then read it from the next explicit Step input.\n"
            )
            (surface / "blocks/notes.md").write_text("# Working notes\n")
            (surface / "template.md").write_text(
                "{{blocks/goal.md}}\n{{blocks/usage.md}}\n{{blocks/notes.md}}\n")
            (surface / "emit.py").write_bytes((ROOT / "lore_runtime/emit_cli.py").read_bytes())
            (surface / "blocks/usage.md").write_text(
                "# Available ordinary tools and output format\n\n"
                "Use the existing shell tool with target workspace or runtime. "
                "report.json must contain a JSON integer field named sum. "
                "Do not report completion without writing the files.\n\n"
                "After the Workspace report is published, the next explicit Step's "
                "history catalog gives the accepted Workspace version and its actual "
                "read-only /input/history/ path. In the runtime shell, actually read "
                "report.json from that catalog directory and output its original bytes. "
                "Write blocks/notes.md with a Markdown link whose destination is that "
                "exact absolute historical report path. Use the supplied catalog; "
                "do not invent a version, digest or path.\n\n"
                "The Runtime directory contains the supplied ordinary emit.py helper. "
                "Its usage is python3 emit.py NAME JSON_OBJECT; it stages a notification "
                "for the trusted host and does not itself claim delivery. Stage exactly "
                "one application notification named m01.report.ready after the report "
                "and notes are written. Then read that notification from the next "
                "explicit Step's event input and acknowledge its actual name before "
                "giving the final answer. Do not emit it again.\n")
            sample = {
                "id": sample_id, "input_name": name, "repeat": repeat,
                "surface": str(surface), "workspace": str(workspace),
                "original_input": str(original), "original_sha256": sha(original),
                "before_files": {
                    str(q): sha(q)
                    for q in [original, workspace / "numbers.json",
                              *sorted(q for q in surface.rglob("*") if q.is_file())]
                },
                "status": "UNVERIFIED",
            }
            samples.append(sample)
    return samples


def check_artifact_files(sample, report_path, notes_path, report_location):
    """Trusted collector only: resolve F versions/authorization before this call.

    No application-supplied host path is safe input. This returns only the
    existing content oracle's result; it cannot mark an M01 sample successful.
    The original observer input, not the writable Workspace input, is used.
    """
    if __package__:
        from .artifact_oracles import sum_files, ArtifactError
    else:
        from artifact_oracles import sum_files, ArtifactError
    original = Path(sample["original_input"])
    if sha(original) != sample["original_sha256"]:
        raise ArtifactError("original observer input changed")
    return sum_files(original, report_path, notes_path, report_location)


async def execute_sample(rt, sample, config, initial_refs, observer):
    """Call real services only; return observations, never infer M01 PASS.

    The caller owns actual service/observer construction. None or missing
    methods are rejected before open; no fallback result or fake is provided.
    """
    for obj, names in [(rt, ("open", "register", "start", "drive_until", "query", "close")),
                       (observer, ("begin", "collect_m01", "mark_accepting", "mark_finished"))]:
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
    targets = refs["execution_targets"]
    if (not isinstance(targets, list) or
            any(not isinstance(t, dict) or "resource_id" not in t for t in targets) or
            {t["resource_id"] for t in targets} != {sid, wid}):
        raise ValueError("M01 needs the two original registered execution targets")
    if sha(sample["original_input"]) != sample["original_sha256"]:
        raise ValueError("original observer input changed before execution")
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
            "execution_targets": targets,
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
        # Original M01 sample clock begins before first explicit acceptance.
        # 2026-09-14 (m01-output-budget amendment, batch-af counterexample): the
        # whole-chain drive budget was the third 300-second deadline (besides the
        # node step deadline and the S scope budget). Archive-enabled real chains
        # now run 8+ invocations; the runner abandoned the chain at start+300s
        # exactly and sealed mid-notification-step. 300 -> 900, still inside the
        # observed O7 wall limit of 1800.
        deadline = time.monotonic() + 900
        observer.mark_accepting()
        accepting = True
        replies["accepted"] = rt.start(cfg["principal"], request)
        if deadline <= time.monotonic():
            raise TimeoutError("M01 acceptance consumed its original 300 second budget")
        replies["drive"] = await asyncio.wait_for(
            rt.drive_until(cfg["principal"], request_id,
                           deadline_monotonic=deadline),
            timeout=deadline - time.monotonic())
        observer.mark_finished()
        accepting = False
        replies["query"] = rt.query(cfg["principal"], request_id)
        # After query (m01-real-2026-09-14as counterexample: execution records
        # created during query/close landed after an earlier final sample) and
        # before close removes the containers.
        await observer.final_tick()
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
    # This independent collector reads original stores, never the replies above.
    try:
        observations = await observer.collect_m01(sample, request_id)
    except Exception as error:
        observations = {"status": "FAIL", "checks": [],
                        "error": {"type": type(error).__name__, "message": str(error)}}
        if failure is None:
            failure = error
    if failure is not None:
        return {"id": sample["id"], "status": "FAIL",
                "error": {"type": type(failure).__name__, "message": str(failure)},
                "runtime_replies": replies, "observations": observations}
    try:
        if not isinstance(observations, dict) or "artifact_files" not in observations:
            raise RuntimeError("MISSING: independently resolved original F artifacts")
        files = observations["artifact_files"]
        artifacts = check_artifact_files(
            sample, files["report_path"], files["notes_path"], files["report_location"])
    except Exception as error:
        return {"id": sample["id"], "status": "FAIL",
                "error": {"type": type(error).__name__, "message": str(error)},
                "runtime_replies": replies, "observations": observations}
    return {"id": sample["id"], "status": "UNVERIFIED_PENDING_INTEGRATION_ORACLE",
            "runtime_replies": replies, "observations": observations,
            "artifact_content": artifacts}


def main():
    # The finite executable wrapper owns construction; this file keeps original cases.
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from validation.system.m01_run import main as run_main
    return run_main()


if __name__ == "__main__":
    raise SystemExit(main())
