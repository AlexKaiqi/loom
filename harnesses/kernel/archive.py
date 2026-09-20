"""Ordinary, durable Surface archives. No Runtime state or private file API."""
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def directory(path):
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise ValueError("kernel Surface and archive must be real directories")
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def save(surface, kind, value):
    surface = Path(surface)
    # Do not follow a replaced Work/Surface boundary. All further operations use
    # directory descriptors, including the temporary file and atomic rename.
    if not stat.S_ISDIR(surface.parent.lstat().st_mode):
        raise ValueError("kernel Work must be a real directory")
    root = directory(surface)
    archive = None
    try:
        try:
            os.mkdir("archive", dir_fd=root)
            os.fsync(root)
        except FileExistsError:
            pass
        archive = os.open("archive", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            index_stat = os.stat("index.jsonl", dir_fd=archive, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(index_stat.st_mode) or index_stat.st_nlink != 1:
                raise ValueError("kernel archive index must be an ordinary file with one link")
        raw = encode({"format": 1, "kind": kind, "original": value})
        digest = hashlib.sha256(raw).hexdigest()
        name = digest + ".json"
        reference = {"path": "archive/" + name, "sha256": digest, "bytes": len(raw), "mode": "lossless"}
        try:
            existing = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=archive)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            with os.fdopen(existing, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or os.fstat(stream.fileno()).st_nlink != 1 or stream.read() != raw:
                    raise ValueError("kernel archive content changed")
            return reference
        temporary = "." + uuid.uuid4().hex + ".tmp"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=archive)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temporary, name, src_dir_fd=archive, dst_dir_fd=archive)
            os.fsync(archive)
            fd = os.open("index.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644, dir_fd=archive)
            with os.fdopen(fd, "wb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or os.fstat(stream.fileno()).st_nlink != 1:
                    raise ValueError("kernel archive index must be an ordinary file")
                stream.write(encode(reference) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(archive)
        finally:
            try:
                os.unlink(temporary, dir_fd=archive)
            except FileNotFoundError:
                pass
        return reference
    finally:
        if archive is not None:
            os.close(archive)
        os.close(root)
