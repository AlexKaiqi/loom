"""Bounded ordinary source bytes and manifests. No Session or execution policy."""

from pathlib import Path, PurePosixPath
from decimal import Decimal, InvalidOperation
import base64, hashlib, io, json, os, stat, tarfile
from .errors import ExecutionError, require

SCOPE = ("namespace", "surface_id", "session_id", "session_generation")
EXEC = (
    "execution_id",
    "object_generation",
    "request_digest",
    "container_id",
    "exec_id",
    "volume_id",
    "freeze_generation",
)


def invalid(message):
    raise ExecutionError("INVALID_REQUEST", message)


def json_value(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid("duplicate JSON field")
            result[key] = value
        return result

    try:
        return json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda value: invalid("nonfinite JSON"),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ExecutionError("INVALID_REQUEST", "invalid bounded JSON") from exc


def file_object(path, cap=18874368, contents=True):
    p = Path(path)
    require(
        p.is_absolute() and not p.is_symlink(),
        "INVALID_REQUEST",
        "absolute original file required",
    )
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            require(
                stat.S_ISREG(before.st_mode) and before.st_size <= cap,
                "INVALID_REQUEST",
                "original file exceeds ordinary profile",
            )
            parts, length, sha = [], 0, hashlib.sha256()
            while True:
                part = os.read(fd, 524288)
                if not part:
                    break
                length += len(part)
                require(
                    length <= cap, "INVALID_REQUEST", "original file grew beyond limit"
                )
                sha.update(part)
                if contents:
                    parts.append(part)
            after = os.fstat(fd)
            require(
                (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                )
                == (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                )
                and length == before.st_size,
                "INVALID_REQUEST",
                "original changed during read",
            )
            return {
                "path": str(p),
                "sha256": sha.hexdigest(),
                "bytes": length,
                "root": {"dev": before.st_dev, "ino": before.st_ino},
            }, (b"".join(parts) if contents else None)
        finally:
            os.close(fd)
    except (OSError, TypeError, ValueError) as exc:
        raise ExecutionError("INVALID_REQUEST", "original file unavailable") from exc


def reference(ref, cap=18874368):
    require(
        type(ref) is dict and {"path", "sha256"} <= ref.keys(),
        "INVALID_REQUEST",
        "original reference incomplete",
    )
    fact, raw = file_object(ref["path"], cap)
    require(
        ref["sha256"] == fact["sha256"]
        and ("bytes" not in ref or ref["bytes"] == fact["bytes"])
        and ("size" not in ref or ref["size"] == fact["bytes"])
        and ("root" not in ref or ref["root"] == fact["root"]),
        "INVALID_REQUEST",
        "original reference bytes or inode differ",
    )
    return fact, raw


def document(ref):
    return json_value(reference(ref, 2097152)[1])


def relative(name):
    if name.startswith("./"):
        name = name[2:]
    require(
        name == "."
        or (
            name
            and not name.startswith("/")
            and all(p not in ("", ".", "..") for p in name.split("/"))
        ),
        "INVALID_REQUEST",
        "unsafe ordinary member name",
    )
    return name


def archive_manifest(raw):
    require(len(raw) <= 18874368, "INVALID_REQUEST", "ordinary archive limit")
    rows, logical = {}, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as source:
            for item in source:
                name = relative(item.name)
                require(
                    name not in rows and len(rows) < 512,
                    "INVALID_REQUEST",
                    "duplicate/member limit",
                )
                require(
                    item.uid == item.gid == 1000
                    and 0 <= item.mode <= 4095
                    and not item.sparse,
                    "INVALID_REQUEST",
                    "unsupported ordinary ownership/mode/sparse",
                )
                require(
                    not any(
                        k.startswith(
                            (
                                "SCHILY.xattr.",
                                "SCHILY.acl.",
                                "GNU.sparse.",
                                "LIBARCHIVE.xattr",
                            )
                        )
                        for k in item.pax_headers
                    ),
                    "INVALID_REQUEST",
                    "unsupported archive metadata",
                )
                ns = (
                    Decimal(item.pax_headers.get("mtime", str(item.mtime))) * 1000000000
                )
                require(
                    ns.is_finite() and ns == ns.to_integral_value(),
                    "INVALID_REQUEST",
                    "mtime must have exact nanoseconds",
                )
                row = {
                    "mode": item.mode,
                    "uid": item.uid,
                    "gid": item.gid,
                    "mtime_ns": int(ns),
                    "xattrs": {},
                }
                if item.isfile():
                    require(
                        0 <= item.size <= 16777216,
                        "INVALID_REQUEST",
                        "ordinary member byte limit",
                    )
                    data = source.extractfile(item).read(16777217)
                    logical += len(data)
                    require(
                        len(data) == item.size and logical <= 16777216,
                        "INVALID_REQUEST",
                        "incomplete or excessive ordinary bytes",
                    )
                    row.update(
                        kind="file",
                        byte_length=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    )
                elif item.isdir():
                    row["kind"] = "dir"
                elif item.issym():
                    row.update(
                        kind="symlink",
                        target_base64=base64.b64encode(
                            os.fsencode(item.linkname)
                        ).decode(),
                    )
                elif item.islnk():
                    row.update(kind="hardlink", target=relative(item.linkname))
                else:
                    invalid("unsupported ordinary member type")
                rows[name] = row
    except (
        tarfile.TarError,
        OSError,
        ValueError,
        OverflowError,
        InvalidOperation,
    ) as exc:
        raise ExecutionError("INVALID_REQUEST", "invalid ordinary archive") from exc
    require(
        rows.get(".", {}).get("kind") == "dir", "INVALID_REQUEST", "root member absent"
    )
    for name, row in rows.items():
        if name != ".":
            require(
                rows.get(str(PurePosixPath(name).parent), {}).get("kind") == "dir",
                "INVALID_REQUEST",
                "invalid ordinary parent",
            )
        if row["kind"] == "hardlink":
            target = rows.get(row["target"], {})
            require(
                target.get("kind") == "file"
                and all(
                    row[k] == target[k]
                    for k in ("mode", "uid", "gid", "mtime_ns", "xattrs")
                ),
                "INVALID_REQUEST",
                "hardlink original or metadata differs",
            )
    return rows, logical


def snapshot(ref, expected):
    require(
        type(ref) is dict and ref.get("owner") == "S",
        "INVALID_REQUEST",
        "ordinary S source required",
    )
    for key in ("namespace", "session_id", "session_generation"):
        require(
            ref.get(key) == expected[key],
            "UNAUTHORIZED",
            "S original Session scope differs",
        )
    body = document({"path": ref["record_path"], "sha256": ref["record_sha256"]})
    require(
        set(body)
        == {"schema", "origin", *SCOPE, "original_execution", "archive", "manifest"}
        and body["schema"] == "lore-x-session-ordinary-snapshot/v1",
        "INVALID_REQUEST",
        "ordinary record schema differs",
    )
    require(
        all(body[k] == expected[k] for k in (*SCOPE, "original_execution")),
        "UNAUTHORIZED",
        "registered original execution differs",
    )
    fact, raw = reference(body["archive"])
    manifest_fact, manifest_raw = reference(body["manifest"], 2097152)
    for prefix, actual in (("archive", fact), ("manifest", manifest_fact)):
        require(
            all(
                ref[prefix + "_" + key] == actual[key]
                for key in ("path", "sha256", "bytes")
            ),
            "INVALID_REQUEST",
            "top original reference differs",
        )
    manifest = json_value(manifest_raw)
    require(
        set(manifest)
        == {
            "schema",
            "namespace",
            "session_id",
            "session_generation",
            "metadata_profile",
            "entries",
            "logical_bytes",
            "archive_sha256",
            "archive_bytes",
        }
        and manifest["schema"] == "lore-x-session-ordinary-manifest/v1"
        and manifest["metadata_profile"] == "linux-posix-session-no-xattr-acl-v1",
        "INVALID_REQUEST",
        "ordinary manifest schema differs",
    )
    require(
        all(
            manifest[k] == expected[k]
            for k in ("namespace", "session_id", "session_generation")
        ),
        "UNAUTHORIZED",
        "manifest Session differs",
    )
    rows, logical = archive_manifest(raw)
    require(
        manifest["entries"] == rows
        and manifest["logical_bytes"] == logical
        and manifest["archive_sha256"] == fact["sha256"]
        and manifest["archive_bytes"] == len(raw),
        "INVALID_REQUEST",
        "ordinary archive manifest does not describe actual complete bytes",
    )
    if body["origin"] == "empty-initial":
        require(
            expected["original_execution"] is None
            and rows
            == {
                ".": {
                    "kind": "dir",
                    "mode": 448,
                    "uid": 1000,
                    "gid": 1000,
                    "mtime_ns": 0,
                    "xattrs": {},
                }
            },
            "INVALID_REQUEST",
            "empty initial record conceals data",
        )
    else:
        require(
            body["origin"] == "checkpoint"
            and type(expected["original_execution"]) is dict,
            "INVALID_REQUEST",
            "original snapshot origin missing",
        )
    return {
        "raw_archive": raw,
        "archive_fact": fact,
        "record": body,
        "manifest": manifest,
    }


def readonly(mount):
    source = mount["source"]
    root = Path(source["path"])
    require(
        root.is_absolute() and root.resolve() == root and root.is_dir(),
        "INVALID_REQUEST",
        "original directory required",
    )
    identity = root.stat()
    require(
        (identity.st_dev, identity.st_ino) == (source["dev"], source["ino"]),
        "INVALID_REQUEST",
        "original directory was replaced",
    )
    manifest = document(mount["manifest_ref"])
    require(
        manifest.get("schema") == "lore-x-readonly-tree/v1"
        and manifest["role"] == mount["role"]
        and manifest["root"] == source
        and manifest["source_ref"] == mount["content_ref"],
        "INVALID_REQUEST",
        "readonly manifest/source association differs",
    )
    actual = {}
    for p in [root, *sorted(root.rglob("*"))]:
        st = p.lstat()
        row = {
            "mode": stat.S_IMODE(st.st_mode),
            "uid": st.st_uid,
            "gid": st.st_gid,
            "mtime_ns": st.st_mtime_ns,
        }
        require(
            not os.listxattr(p, follow_symlinks=False),
            "INVALID_REQUEST",
            "readonly metadata outside profile",
        )
        if stat.S_ISDIR(st.st_mode):
            row["kind"] = "dir"
        elif stat.S_ISREG(st.st_mode):
            fact, _ = file_object(p, 268435456, contents=False)
            row.update(kind="file", byte_length=fact["bytes"], sha256=fact["sha256"])
        elif stat.S_ISLNK(st.st_mode):
            resolved = p.resolve(strict=True)
            require(
                resolved.is_relative_to(root),
                "INVALID_REQUEST",
                "readonly symlink escapes source",
            )
            row.update(
                kind="symlink",
                target=os.readlink(p),
                resolved_relative=resolved.relative_to(root).as_posix(),
            )
        else:
            invalid("readonly source special member")
        actual["." if p == root else p.relative_to(root).as_posix()] = row
        require(len(actual) <= 8192, "INVALID_REQUEST", "readonly member limit")
    require(
        actual == manifest["entries"],
        "INVALID_REQUEST",
        "actual complete readonly tree differs",
    )
    return manifest
