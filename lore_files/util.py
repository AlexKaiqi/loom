"""Finite canonical inputs and durable local control records."""
import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from .errors import FileError, require

DEFAULT_LIMITS = dict(max_entries=64, max_logical_bytes=1048576,
                      max_archive_bytes=2097152, window_seconds=10)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identity(path):
    st = os.stat(path, follow_symlinks=False)
    return dict(dev=st.st_dev, ino=st.st_ino)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        sync_dir(path.parent)
    except OSError as exc:
        raise FileError("PERSISTENCE_FAILED", str(exc)) from exc
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ordinary_path(path):
    """Reject aliases in every existing component, not just the last name."""
    p = Path(os.path.abspath(os.fspath(path)))
    for part in [*reversed(p.parents), p]:
        if part.is_symlink():
            raise FileError("STALE_BINDING", "symlink in controlled directory path")
    return p


class Journal:
    def __init__(self, root):
        self.root = Path(root) / "requests"
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.lockpath = Path(root) / "lock"

    @contextmanager
    def lock(self):
        fd = os.open(self.lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def path(self, request_id):
        require(isinstance(request_id, str) and request_id, "CONFLICT", "empty request ID")
        return self.root / (digest(request_id.encode()) + ".json")

    def get(self, request_id, inputs=None):
        path = self.path(request_id)
        if not path.exists():
            return None
        record = json.loads(path.read_bytes())
        if inputs is not None:
            require(canonical(record["inputs"]) == canonical(inputs), "CONFLICT",
                    "request ID already binds different complete inputs")
        return record

    def put(self, request_id, record):
        atomic_write(self.path(request_id), canonical(record))
