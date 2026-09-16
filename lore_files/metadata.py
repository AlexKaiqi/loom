"""No-follow ordinary directory observations for the host-v1 profile."""
import base64
import os
import sys

_XATTR_REJECT = {95} if sys.platform == "linux" else set()
# 2026-09-15 (amendment-linux-browser): on Linux hosts the evidence/workspace
# tree may live on a mount that rejects xattr syscalls (Docker Desktop
# virtiofs: EOPNOTSUPP/95). The observer contract accepts "no xattrs" rows, so
# the walk records an empty xattr set for such filesystems instead of failing
# the whole window. Explicit platform branch: darwin (APFS) keeps raising.


def _safe_xattrs(fd, follow=None):
    kwargs = {} if follow is None else {"follow_symlinks": follow}
    try:
        names = os.listxattr(fd, **kwargs)
        return {x: os.getxattr(fd, x, **kwargs) for x in names}
    except OSError as exc:
        if exc.errno in _XATTR_REJECT:
            return {}
        raise
import stat
from .errors import FileError, require
from .util import digest

SUPPORTED_SYSTEM_ATTRS = {"system.posix_acl_access", "system.posix_acl_default"}


def attrs_allowed(attrs):
    return all(name.startswith("user.") or name in SUPPORTED_SYSTEM_ATTRS for name in attrs)


def owner_allowed(uid, gid):
    return uid == os.geteuid() and gid in {os.getegid(), *os.getgroups()}


def encode(raw):
    return base64.b64encode(raw).decode("ascii")


def metadata(st, attrs, kind):
    require(owner_allowed(st.st_uid, st.st_gid), "UNSUPPORTED", "unsupported owner mapping")
    require(attrs_allowed(attrs), "UNSUPPORTED", "unsupported extended metadata")
    return dict(kind=kind, mode=stat.S_IMODE(st.st_mode), mtime_ns=st.st_mtime_ns,
                uid=st.st_uid, gid=st.st_gid,
                xattrs={name: encode(raw) for name, raw in sorted(attrs.items())})


def walk(root, limits, visit_dir=None, visit_file=None, include_data=True, tick=None):
    """Open each ancestor by dirfd; callbacks receive actual open kernel objects."""
    entries, contents, groups = {}, {}, {}
    logical = 0

    def check():
        if tick:
            tick()

    def descend(fd, name):
        nonlocal logical
        check()
        st = os.fstat(fd)
        require(stat.S_ISDIR(st.st_mode), "UNSUPPORTED", "root/parent is not directory")
        require(st.st_mode & 0o500 == 0o500, "UNREADABLE", "directory cannot be enumerated")
        require(len(entries) < limits["max_entries"], "LIMIT_EXCEEDED", "entry limit")
        if visit_dir:
            visit_dir(fd, name)
        attrs = _safe_xattrs(fd)
        entries[name] = metadata(st, attrs, "dir")
        with os.scandir(fd) as scan:
            names = sorted((e.name for e in scan), key=os.fsencode)
        for leaf in names:
            check()
            relative = leaf if name == "." else name + "/" + leaf
            observed = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            mode = observed.st_mode
            require(len(entries) < limits["max_entries"], "LIMIT_EXCEEDED", "entry limit")
            if stat.S_ISDIR(mode):
                sub = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    require((os.fstat(sub).st_dev, os.fstat(sub).st_ino) ==
                            (observed.st_dev, observed.st_ino), "CHANGE_OBSERVED", "directory replaced")
                    descend(sub, relative)
                finally:
                    os.close(sub)
            elif stat.S_ISREG(mode):
                require(mode & 0o400, "UNREADABLE", "file owner cannot read complete bytes")
                opened = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    actual = os.fstat(opened)
                    require((actual.st_dev, actual.st_ino) == (observed.st_dev, observed.st_ino),
                            "CHANGE_OBSERVED", "file replaced")
                    if visit_file:
                        visit_file(opened, relative)
                    key = (actual.st_dev, actual.st_ino)
                    if key not in groups:
                        logical += actual.st_size
                    require(logical <= limits["max_logical_bytes"], "LIMIT_EXCEEDED", "logical byte limit")
                    groups.setdefault(key, []).append(relative)
                    item = metadata(actual, _safe_xattrs(opened), "file")
                    if include_data:
                        data = bytearray()
                        while True:
                            check()
                            chunk = os.read(opened, min(65536, limits["max_logical_bytes"] + 1 - len(data)))
                            if not chunk:
                                break
                            data.extend(chunk)
                            require(len(data) <= limits["max_logical_bytes"], "LIMIT_EXCEEDED", "file grew beyond limit")
                        require(len(data) == actual.st_size, "CHANGE_OBSERVED", "file size changed")
                        contents[relative] = bytes(data)
                        item.update(size=len(data), sha256=digest(data))
                    else:
                        item.update(size=actual.st_size)
                    entries[relative] = item
                finally:
                    os.close(opened)
            elif stat.S_ISLNK(mode):
                anchored = f"/proc/self/fd/{fd}/" + leaf
                attrs = _safe_xattrs(anchored, follow=False)
                item = metadata(observed, attrs, "symlink")
                item["target_b64"] = encode(os.fsencode(os.readlink(leaf, dir_fd=fd)))
                entries[relative] = item
            else:
                raise FileError("UNSUPPORTED", "special object is outside ordinary-file profile")
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            descend(fd, ".")
        finally:
            os.close(fd)
    except PermissionError as exc:
        raise FileError("UNREADABLE", str(exc)) from exc
    except FileNotFoundError as exc:
        raise FileError("CHANGE_OBSERVED", str(exc)) from exc
    return dict(entries=entries, hardlink_groups=sorted(sorted(g) for g in groups.values() if len(g) > 1)), contents
