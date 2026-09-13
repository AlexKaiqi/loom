"""Complete bounded ordinary archives; source links are data, never authority."""

from pathlib import Path, PurePosixPath
import io, os, stat, tarfile
from .errors import ExecutionError, require
from .journal import digest
from .engine import command, PROFILE


def inspect(raw, budget):
    require(len(raw) <= budget["archive_bytes"], "ARCHIVE_LIMIT", "raw archive limit")
    members = {}
    logical = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                name = member.name
                while name.startswith("./"):
                    name = name[2:]
                if name in ("", "."):
                    name = "."
                path = PurePosixPath(name)
                require(
                    not path.is_absolute()
                    and ".." not in path.parts
                    and name not in members,
                    "UNSUPPORTED",
                    "unsafe or repeated archive path",
                )
                require(
                    member.isdir()
                    or member.isfile()
                    or member.issym()
                    or member.islnk(),
                    "UNSUPPORTED",
                    "unsupported ordinary member",
                )
                require(
                    member.uid == 1000 and member.gid == 1000,
                    "UNSUPPORTED",
                    "ownership outside verified identity mapping",
                )
                require(
                    not any(
                        k.startswith(("SCHILY.xattr", "SCHILY.acl", "LIBARCHIVE.xattr"))
                        for k in member.pax_headers
                    ),
                    "UNSUPPORTED",
                    "metadata outside private volume capabilities",
                )
                for parent in path.parents:
                    if str(parent) in members:
                        require(
                            members[str(parent)]["kind"] == "directory",
                            "UNSUPPORTED",
                            "link or file parent",
                        )
                item = {
                    "mode": member.mode,
                    "uid": member.uid,
                    "gid": member.gid,
                    "mtime": member.pax_headers.get("mtime", str(member.mtime)),
                }
                if member.isfile():
                    logical += member.size
                    require(
                        logical <= budget["expanded_bytes"],
                        "ARCHIVE_LIMIT",
                        "expanded ordinary bytes exceeded",
                    )
                    data = archive.extractfile(member).read()
                    require(
                        len(data) == member.size,
                        "UNSUPPORTED",
                        "incomplete archive member",
                    )
                    item.update(kind="file", sha256=digest(data), size=len(data))
                elif member.isdir():
                    item["kind"] = "directory"
                elif member.issym():
                    item.update(kind="symlink", target=member.linkname)
                else:
                    link = member.linkname
                    while link.startswith("./"):
                        link = link[2:]
                    require(
                        link in members and members[link]["kind"] == "file",
                        "UNSUPPORTED",
                        "hardlink must refer to original known regular member",
                    )
                    item.update(kind="hardlink", target=link)
                members[name] = item
                require(
                    len(members) <= budget["inodes"],
                    "ARCHIVE_LIMIT",
                    "archive inode/member budget",
                )
    except (tarfile.TarError, OSError, ValueError) as exc:
        raise ExecutionError("UNSUPPORTED", "invalid complete archive") from exc
    require(
        "." in members and members["."]["kind"] == "directory",
        "UNSUPPORTED",
        "archive lacks original root",
    )
    return members


def initial(request):
    root = Path(request["input_root"])
    budget = request["budgets"]
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in [".", *dirs, *files]:
            p = Path(base) / name
            s = p.lstat()
            require(
                stat.S_ISREG(s.st_mode)
                or stat.S_ISDIR(s.st_mode)
                or stat.S_ISLNK(s.st_mode),
                "UNSUPPORTED",
                "input special member",
            )
            require(
                not os.listxattr(p, follow_symlinks=False),
                "UNSUPPORTED",
                "unsupported actual input metadata",
            )
    raw = command(
        [
            "/usr/bin/tar",
            "--format=pax",
            "--numeric-owner",
            "--pax-option=delete=atime,delete=ctime",
            "-cpf",
            "-",
            "-C",
            str(root),
            ".",
        ],
        limit=budget["archive_bytes"],
    )
    inspect(raw, budget)
    return raw


def import_volume(engine, record, raw):
    inspect(raw, record.get("limits", record["request"]["budgets"]))
    volume = record["binding"]["volume_id"]
    engine.helper(
        record,
        [
            "--user",
            "1000:1000",
            "--mount",
            "type=volume,src=" + volume + ",dst=/work,volume-nocopy",
            PROFILE["image"],
            "tar",
            "--numeric-owner",
            "--no-same-owner",
            "-xpf",
            "-",
            "-C",
            "/work",
        ],
        data=raw,
    )


def export_volume(engine, record):
    volume = record["binding"]["volume_id"]
    b = record.get("limits", record["request"]["budgets"])
    # Reject special and sparse logical excess before tar can silently omit or expand them.
    code = "import os,stat,json;total=0;types=[];metadata=bool(os.listxattr('/work',follow_symlinks=False))\nfor root,ds,fs in os.walk('/work',followlinks=False):\n for n in ds+fs:\n  p=os.path.join(root,n);s=os.lstat(p);types.append(stat.S_IFMT(s.st_mode));total+=s.st_size if stat.S_ISREG(s.st_mode) else 0;metadata=metadata or bool(os.listxattr(p,follow_symlinks=False))\nprint(json.dumps({'logical':total,'types':types,'unsupported_metadata':metadata}))"
    import json

    args = [
        "--user",
        "0:0",
        "--cap-add",
        "DAC_OVERRIDE",
        "--mount",
        "type=volume,src=" + volume + ",dst=/work,readonly,volume-nocopy",
        PROFILE["image"],
    ]
    facts = json.loads(
        engine.helper(record, [*args, "python", "-c", code], limit=1048576)
    )
    require(
        not facts["unsupported_metadata"],
        "UNSUPPORTED",
        "ordinary export cannot discard ACL/xattr metadata",
    )
    require(
        facts["logical"] <= b["expanded_bytes"], "ARCHIVE_LIMIT", "logical export limit"
    )
    require(
        all(t in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK) for t in facts["types"]),
        "UNSUPPORTED",
        "special output member",
    )
    raw = engine.helper(
        record,
        [
            *args,
            "tar",
            "--format=pax",
            "--numeric-owner",
            "--pax-option=delete=atime,delete=ctime",
            "-cpf",
            "-",
            "-C",
            "/work",
            ".",
        ],
        limit=b["archive_bytes"],
    )
    return raw, inspect(raw, b)
