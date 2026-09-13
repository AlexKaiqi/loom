"""Validate caller-independent full bindings before any physical object is created."""

from pathlib import Path
import base64, math, os
from .errors import ExecutionError, require
from .journal import canonical, digest

FIELDS = {
    "schema_version",
    "execution_id",
    "caller",
    "invocation_id",
    "step_id",
    "source_result",
    "harness_version",
    "target_selector",
    "target_id",
    "binding_generation",
    "domain",
    "base_version",
    "input_manifest",
    "input_root",
    "cwd",
    "environment",
    "endpoints",
    "network",
    "budgets",
    "stdin_base64",
    "io_mode",
    "interpreter_argv",
    "script_base64",
}
MAXIMA = {
    "memory_bytes": 134217728,
    "pids": 32,
    "cpu": 0.5,
    "volume_bytes": 6291456,
    "inodes": 1024,
    "tmp_bytes": 1048576,
    "shm_bytes": 1048576,
    "stdout_bytes": 65536,
    "stderr_bytes": 65536,
    "combined_output_bytes": 98304,
    "archive_bytes": 8388608,
    "expanded_bytes": 12582912,
    "deadline_seconds": 20,
}


def validate(request, authority, state_dir, restore=False):
    require(
        type(request) is dict
        and not set(request)
        - FIELDS
        - {"readonly_mounts"}
        - ({"restore_source", "object_generation"} if restore else set())
        and FIELDS <= set(request),
        "INVALID_REQUEST",
        "unknown or missing execution field",
    )
    require(
        request["schema_version"] == 1 and type(request["schema_version"]) is int,
        "INVALID_REQUEST",
        "unsupported schema",
    )
    if "readonly_mounts" in request:
        mounts = request["readonly_mounts"]
        require(
            not restore
            and request["domain"] == "runtime"
            and type(mounts) is list
            and len(mounts) == 1
            and type(mounts[0]) is dict
            and set(mounts[0]) == {
                "role", "source", "target", "read_only", "manifest_ref", "content_ref"
            }
            and mounts[0]["role"] == "input"
            and mounts[0]["target"] == "/input"
            and mounts[0]["read_only"] is True,
            "INVALID_REQUEST",
            "only runtime execute supports one fixed readonly input",
        )
        require(
            type(authority.get("grant_ref")) is dict
            and type(authority.get("slot_ref")) is dict,
            "UNAUTHORIZED",
            "readonly input requires original trusted grant and slot",
        )
    for key in [
        "execution_id",
        "caller",
        "invocation_id",
        "step_id",
        "harness_version",
    ]:
        require(
            type(request[key]) is str and 0 < len(request[key]) <= 256,
            "INVALID_REQUEST",
            "missing stable " + key,
        )
    require(
        authority.get("caller") == request["caller"]
        and ("restore" if restore else "execute") in authority.get("grants", []),
        "UNAUTHORIZED",
        "caller lacks original grant",
    )
    require(
        Path(authority["state_dir"]).resolve() == Path(state_dir).resolve(),
        "UNAUTHORIZED",
        "control store scope differs",
    )
    require(
        authority.get("domain") == request["domain"]
        and request["domain"] in ("runtime", "task"),
        "UNAUTHORIZED",
        "domain differs",
    )
    require(
        authority["binding_generation"] == request["binding_generation"]
        and authority["base_version"] == request["base_version"],
        "STALE_BINDING",
        "resource generation/base differs",
    )
    target = Path(authority["target_path"]).resolve(strict=True)
    actual = target.stat()
    require(
        {"dev": actual.st_dev, "ino": actual.st_ino} == authority["target_identity"],
        "STALE_BINDING",
        "actual target root replaced",
    )
    selector = request["target_selector"]
    explicit = selector.get("target_id")
    location = Path(selector["location"]).resolve()
    require(
        set(selector) <= {"target_id", "location"},
        "INVALID_REQUEST",
        "unknown selector field",
    )
    if explicit is None and len(authority.get("same_location_targets", [])) > 1:
        raise ExecutionError("AMBIGUOUS", "multiple objects at selected location")
    if explicit is not None:
        require(
            explicit == authority["target_id"] and request["target_id"] == explicit,
            "UNAUTHORIZED",
            "explicit object lacks grant",
        )
    if location != target:
        new = (
            authority.get("allowed_parent")
            and Path(authority["allowed_parent"]).resolve() == target
            and location.is_relative_to(target)
            and not location.exists()
        )
        require(
            new,
            (
                "UNREGISTERED"
                if explicit is None and not str(location).startswith(str(target))
                else "UNAUTHORIZED"
            ),
            "selected location outside registered scope",
        )
    require(
        Path(request["input_root"]).resolve() == target,
        "UNAUTHORIZED",
        "input root outside original authority",
    )
    cwd = Path(request["cwd"])
    require(
        not cwd.is_absolute() and ".." not in cwd.parts,
        "INVALID_REQUEST",
        "working directory must remain within private tree",
    )
    require(
        request["environment"] == "fixed-python-linux-v1"
        and request["network"] == "none"
        and request["endpoints"] == [],
        "INVALID_REQUEST",
        "unapproved execution profile",
    )
    b = request["budgets"]
    require(
        type(b) is dict and set(b) == set(MAXIMA),
        "INVALID_REQUEST",
        "incomplete resource budget",
    )
    for key, maximum in MAXIMA.items():
        require(
            type(b[key]) in (int, float)
            and math.isfinite(b[key])
            and 0 < b[key] <= maximum,
            "INVALID_REQUEST",
            "unapproved " + key,
        )
        if key not in ("cpu", "deadline_seconds"):
            require(type(b[key]) is int, "INVALID_REQUEST", "noninteger " + key)
    require(
        request["io_mode"] in ("finite", "duplex"),
        "INVALID_REQUEST",
        "unknown input channel",
    )
    argv = request["interpreter_argv"]
    require(
        type(argv) is list
        and argv in (["python", "-c"], ["python3", "-c"], ["/bin/sh", "-c"]),
        "INVALID_REQUEST",
        "unapproved ordinary interpreter",
    )
    try:
        script = base64.b64decode(request["script_base64"], validate=True)
        stdin = base64.b64decode(request["stdin_base64"], validate=True)
        script.decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ExecutionError(
            "INVALID_REQUEST", "invalid original command bytes"
        ) from exc
    require(
        0 < len(script) <= 65536 and len(stdin) <= 65536,
        "INVALID_REQUEST",
        "input byte budget",
    )
    require(
        not request["input_manifest"].get("required_metadata"),
        "UNSUPPORTED",
        "required xattr/ACL unavailable in private volume profile",
    )
    if not restore:
        for item in request["input_manifest"]["files"]:
            p = target / item["path"]
            require(
                not p.is_symlink() and p.resolve().is_relative_to(target),
                "INPUT_VERSION_UNAVAILABLE",
                "input member escapes immutable scope",
            )
            with p.open("rb") as stream:
                data = stream.read(b["expanded_bytes"] + 1)
            require(
                len(data) == item["size"] and digest(data) == item["sha256"],
                "INPUT_VERSION_UNAVAILABLE",
                "actual input version differs",
            )
    return {
        "target_id": authority["target_id"],
        "domain": request["domain"],
        "request_digest": digest(canonical(request)),
        "script": script,
        "stdin": stdin,
        "input_root": str(target),
    }
