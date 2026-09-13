"""Bounded PAX ordinary-file codec; validation never extracts untrusted paths."""
import base64
import io
import os
import tarfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .errors import FileError, require
from .metadata import attrs_allowed, encode, owner_allowed, walk
from .util import digest, ordinary_path, sync_dir


def member_name(raw):
    name = raw[2:] if raw.startswith("./") else raw
    require(name == "." or (name and not name.startswith("/") and
            all(part not in ("", ".", "..") for part in name.split("/"))),
            "ARCHIVE_INVALID", "unsafe or ambiguous member path")
    require("\0" not in name, "ARCHIVE_INVALID", "NUL member path")
    return name


def pack(tree, contents, limits):
    out = io.BytesIO()
    previous = {name: group[0] for group in tree["hardlink_groups"] for name in group}
    emitted = {}
    with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT,
                      encoding="utf-8", errors="surrogateescape") as archive:
        # Parent-before-child path ordering also fixes the hardlink representative.
        for name in sorted(tree["entries"]):
            item = tree["entries"][name]
            member = tarfile.TarInfo(name)
            member.mode, member.uid, member.gid = item["mode"], item["uid"], item["gid"]
            member.mtime = item["mtime_ns"] // 1000000000
            member.pax_headers = {"mtime": str(Decimal(item["mtime_ns"]) / 1000000000)}
            member.pax_headers.update({"SCHILY.xattr." + key: base64.b64decode(value).decode("utf-8", "surrogateescape")
                                       for key, value in item["xattrs"].items()})
            data = None
            if item["kind"] == "dir":
                member.type = tarfile.DIRTYPE
            elif item["kind"] == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = os.fsdecode(base64.b64decode(item["target_b64"]))
            else:
                group = previous.get(name, name)
                if group in emitted:
                    member.type = tarfile.LNKTYPE
                    member.linkname = emitted[group]
                else:
                    emitted[group] = name
                    member.size = len(contents[name])
                    data = io.BytesIO(contents[name])
            archive.addfile(member, data)
            require(out.tell() <= limits["max_archive_bytes"], "LIMIT_EXCEEDED", "archive byte limit")
    raw = out.getvalue()
    require(len(raw) <= limits["max_archive_bytes"], "LIMIT_EXCEEDED", "archive padding exceeds limit")
    return raw


def unpack(raw, limits):
    require(len(raw) <= limits["max_archive_bytes"], "LIMIT_EXCEEDED", "archive byte limit")
    entries, contents, owners, groups = {}, {}, {}, {}
    logical = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:", encoding="utf-8", errors="surrogateescape") as archive:
            for member in archive:
                name = member_name(member.name)
                require(name not in entries, "ARCHIVE_INVALID", "duplicate member")
                require(len(entries) < limits["max_entries"], "LIMIT_EXCEEDED", "archive entry limit")
                if name != ".":
                    parent = str(Path(name).parent)
                    require(parent in entries and entries[parent]["kind"] == "dir", "ARCHIVE_INVALID", "undefined or linked parent")
                require(member.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE,
                                        tarfile.SYMTYPE, tarfile.LNKTYPE), "ARCHIVE_INVALID", "special archive member")
                require(not member.sparse, "UNSUPPORTED", "sparse extension requires explicit profile")
                require(owner_allowed(member.uid, member.gid), "UNSUPPORTED", "archive owner mapping unavailable")
                require(0 <= member.mode <= 0o7777, "ARCHIVE_INVALID", "invalid permission bits")
                attrs = {}
                accepted = {"mtime", "atime", "ctime", "path", "linkpath", "size", "uid", "gid", "uname", "gname", "hdrcharset"}
                for key, value in member.pax_headers.items():
                    if key.startswith("SCHILY.xattr."):
                        attrs[key[len("SCHILY.xattr."):]] = encode(value.encode("utf-8", "surrogateescape"))
                    else:
                        require(key in accepted, "UNSUPPORTED", "unknown PAX metadata: " + key)
                require(attrs_allowed(attrs), "UNSUPPORTED", "unsupported archive extended metadata")
                ns = Decimal(member.pax_headers.get("mtime", str(member.mtime))) * 1000000000
                require(ns.is_finite() and ns == ns.to_integral_value(), "ARCHIVE_INVALID", "mtime is not exact nanoseconds")
                kind = "dir" if member.isdir() else "symlink" if member.issym() else "file"
                item = dict(kind=kind, mode=member.mode, uid=member.uid, gid=member.gid,
                            mtime_ns=int(ns), xattrs=attrs)
                if member.islnk():
                    target = member_name(member.linkname)
                    require(target in contents, "ARCHIVE_INVALID", "hardlink target is not prior regular data")
                    data = contents[target]
                    item.update(size=len(data), sha256=digest(data))
                    require(item == entries[target], "ARCHIVE_INVALID", "hardlink metadata conflicts with inode")
                    owners[name] = owners[target]
                    groups[owners[name]].append(name)
                    contents[name] = data
                elif member.isfile():
                    require(0 <= member.size <= limits["max_logical_bytes"] - logical,
                            "LIMIT_EXCEEDED", "archive logical byte limit")
                    require(member.mode & 0o400, "UNREADABLE", "archive contains unreadable host file")
                    data = archive.extractfile(member).read(member.size + 1)
                    require(len(data) == member.size, "ARCHIVE_INVALID", "truncated regular member")
                    logical += len(data)
                    contents[name] = data
                    item.update(size=len(data), sha256=digest(data))
                    owners[name] = name
                    groups[name] = [name]
                elif member.issym():
                    require(member.mode == 0o777 and "\0" not in member.linkname,
                            "UNSUPPORTED", "symlink metadata not supported by host")
                    item["target_b64"] = encode(os.fsencode(member.linkname))
                else:
                    require(member.mode & 0o500 == 0o500, "UNREADABLE", "unreadable archive directory")
                entries[name] = item
        require(entries.get(".", {}).get("kind") == "dir", "ARCHIVE_INVALID", "missing explicit ordinary root")
    except (tarfile.TarError, ValueError, OverflowError, InvalidOperation) as exc:
        raise FileError("ARCHIVE_INVALID", "malformed archive") from exc
    return dict(entries=entries, hardlink_groups=sorted(sorted(g) for g in groups.values() if len(g) > 1)), contents


def materialize_tree(tree, contents, target, limits):
    """Only a new private root; there is no tar.extract or traversal through links."""
    target = ordinary_path(target)
    require(target.parent.is_dir(), "UNSUPPORTED", "target parent must already exist")
    require(not os.path.lexists(target), "CONFLICT", "target already exists")
    target.mkdir(mode=0o700)
    link_from = {name: group[0] for group in tree["hardlink_groups"] for name in group[1:]}
    try:
        for name in sorted(tree["entries"]):
            if name == ".":
                continue
            item = tree["entries"][name]
            path = target / name
            if item["kind"] == "dir":
                path.mkdir(mode=0o700)
            elif item["kind"] == "symlink":
                os.symlink(os.fsdecode(base64.b64decode(item["target_b64"])), path)
            elif name in link_from:
                os.link(target / link_from[name], path, follow_symlinks=False)
            else:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(contents[name])
                    stream.flush()
                    os.fsync(stream.fileno())
        # Apply metadata only after descendants are complete; no parent write alters mtime afterwards.
        for name in sorted(tree["entries"], key=lambda n: (n.count("/"), n), reverse=True):
            item = tree["entries"][name]
            path = target if name == "." else target / name
            os.chown(path, item["uid"], item["gid"], follow_symlinks=False)
            if item["kind"] != "symlink":
                os.chmod(path, item["mode"], follow_symlinks=False)
            for attribute, value in item["xattrs"].items():
                os.setxattr(path, attribute, base64.b64decode(value), follow_symlinks=False)
            os.utime(path, ns=(item["mtime_ns"], item["mtime_ns"]), follow_symlinks=False)
            if item["kind"] == "dir":
                sync_dir(path)
        actual, _ = walk(target, limits)
        require(actual == tree, "UNSUPPORTED", "host did not preserve complete metadata/bytes")
        sync_dir(target.parent)
    except OSError as exc:
        # Preserve the partial staging object; never label it a completed version.
        raise FileError("UNSUPPORTED", "materialization failed: " + str(exc)) from exc
    return target
