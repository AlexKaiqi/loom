"""External durable immutable execution association and original byte references."""

from pathlib import Path
import hashlib, json, os, threading, fcntl
from .errors import require


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".new")
    with temp.open("wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)
    sync_dir(path.parent)


class Journal:
    def __init__(self, path):
        self.root = Path(path).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.write_guard = None
        self.owner_fd = os.open(
            self.root / ".owner-lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(self.owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.owner_fd)
            self.owner_fd = None
            require(
                False,
                "CONTROL_BUSY",
                "one trusted execution observer owns this state directory",
            )

    def close(self):
        if self.owner_fd is not None:
            os.close(self.owner_fd)
            self.owner_fd = None

    def directory(self, id):
        path = self.root / digest(id.encode())
        path.mkdir(mode=0o700, exist_ok=True)
        return path

    def get(self, id):
        with self.lock:
            path = self.directory(id) / "record.json"
            return json.loads(path.read_bytes()) if path.exists() else None

    def put(self, value):
        with self.lock:
            path = self.directory(value["request"]["execution_id"]) / "record.json"
            data = canonical(value)
            if self.write_guard:
                self.write_guard(value, path, len(data))
            atomic(path, data)

    def blob(self, id, name, data):
        with self.lock:
            path = self.directory(id) / (name + "-" + digest(data) + ".blob")
            ref = dict(path=str(path), sha256=digest(data), size=len(data))
            if path.exists():
                require(
                    self.read(ref, len(data)) == data,
                    "RESULT_UNAVAILABLE",
                    "immutable original blob differs",
                )
                return ref
            if self.write_guard:
                record = self.get(id)
                if record:
                    self.write_guard(record, path, len(data))
            atomic(path, data)
            return dict(path=str(path), sha256=digest(data), size=len(data))

    def read(self, ref, limit):
        path = Path(ref["path"])
        require(
            not path.is_symlink() and path.resolve().is_relative_to(self.root),
            "RESULT_UNAVAILABLE",
            "reference outside execution store",
        )
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        require(
            len(data) <= limit
            and len(data) == ref["size"]
            and digest(data) == ref["sha256"],
            "RESULT_UNAVAILABLE",
            "original byte reference differs",
        )
        return data
