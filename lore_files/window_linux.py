"""Linux read leases plus recursive inotify: a bounded observation window.

2026-09-14 platform split: this module is the Linux implementation, imported
verbatim from the previously verified single-file version (Git history keeps
the original). It is selected only on Linux; see window.py for dispatch and
the recorded darwin limitation.
"""
import ctypes
import errno
import fcntl
import os
import signal
import struct
import threading
import time
from pathlib import Path
from .errors import FileError, require
from .metadata import walk
from .util import identity, ordinary_path

_LIBC = None


def _inotify():
    """Lazy libc binding: module import stays safe on non-Linux hosts, while
    any actual Linux runtime use still binds the real symbols."""
    global _LIBC
    if _LIBC is None:
        _LIBC = ctypes.CDLL(None, use_errno=True)
        _LIBC.inotify_init1.argtypes = [ctypes.c_int]
        _LIBC.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    return _LIBC
_MASK = 0x00000FCE | 0x00002000  # modify, attrib, close-write, moves, create/delete, unmount
_LOST = 0x00004000 | 0x00008000 | 0x00002000
_SIGNAL_LOCK = threading.RLock()


class StableWindow:
    def __init__(self, roots, limits):
        self.roots = [(ordinary_path(path), expected) for path, expected in roots]
        self.limits = limits
        self.monitor = -1
        self.leases = {}
        self.watches = {}
        self.broken = False
        self.started = None
        self.prior = None
        self.entered = False

    def tick(self):
        require(time.monotonic() - self.started < self.limits["window_seconds"],
                "LIMIT_EXCEEDED", "stable observation window expired")

    def _signal(self, sig, frame):
        self.broken = True

    def _watch(self, fd, role):
        result = _inotify().inotify_add_watch(self.monitor, os.fsencode(f"/proc/self/fd/{fd}"), _MASK)
        if result < 0:
            raise FileError("OBSERVATION_LOST", os.strerror(ctypes.get_errno()))
        self.watches.setdefault(result, []).append(role)

    def _lease(self, fd, relative):
        st = os.fstat(fd)
        key = st.st_dev, st.st_ino
        if key in self.leases:
            return
        keep = os.dup(fd)
        try:
            fcntl.fcntl(keep, fcntl.F_SETOWN, os.getpid())
            fcntl.fcntl(keep, fcntl.F_SETLEASE, fcntl.F_RDLCK)
        except OSError as exc:
            os.close(keep)
            code = "WRITER_NOT_QUIESCENT" if exc.errno in (errno.EAGAIN, errno.EACCES) else "UNSUPPORTED"
            raise FileError(code, "read lease unavailable: " + relative) from exc
        self.leases[key] = keep
        # Directory watches follow the pathname used for an operation. A separate
        # inode watch observes chmod/xattr through any tree-external hardlink.
        self._watch(keep, ("inode", str(key), relative))

    def __enter__(self):
        _SIGNAL_LOCK.acquire()
        try:
            require(threading.current_thread() is threading.main_thread(), "UNSUPPORTED",
                    "host lease signal window requires the main thread")
            break_time = float(Path("/proc/sys/fs/lease-break-time").read_text())
            require(0 < self.limits["window_seconds"] < break_time, "UNSUPPORTED",
                    "kernel lease-break bound does not exceed requested window")
            self.started = time.monotonic()
            self.prior = signal.signal(signal.SIGIO, self._signal)
            self.entered = True
            self.monitor = _inotify().inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
            require(self.monitor >= 0, "OBSERVATION_LOST", "cannot create inotify instance")
            for root, expected in self.roots:
                require(identity(root) == expected, "STALE_BINDING", "root object identity changed")
                parent = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    self._watch(parent, ("parent", str(root.parent), root.name))
                finally:
                    os.close(parent)
                walk(root, self.limits,
                     visit_dir=lambda fd, name, r=root: self._watch(fd, ("tree", str(r), name)),
                     visit_file=self._lease, include_data=False, tick=self.tick)
            self.assert_clean()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def facts(self):
        return dict(monitor_fd=self.monitor, lease_fds=list(self.leases.values()),
                    roots=[dict(path=str(path), root=expected) for path, expected in self.roots])

    def _monitor_live(self):
        try:
            actual = os.readlink(f"/proc/self/fd/{self.monitor}")
        except OSError as exc:
            raise FileError("OBSERVATION_LOST", "monitor descriptor lost") from exc
        require(actual == "anon_inode:inotify", "OBSERVATION_LOST", "monitor descriptor replaced")

    def _events(self):
        self._monitor_live()
        found = []
        while True:
            try:
                raw = os.read(self.monitor, 65536)
            except BlockingIOError:
                break
            except OSError as exc:
                raise FileError("OBSERVATION_LOST", "cannot read actual monitor") from exc
            require(raw, "OBSERVATION_LOST", "inotify ended")
            offset = 0
            while offset < len(raw):
                wd, mask, cookie, length = struct.unpack_from("iIII", raw, offset)
                leaf = os.fsdecode(raw[offset + 16:offset + 16 + length].split(b"\0", 1)[0])
                offset += 16 + length
                require(not mask & _LOST, "OBSERVATION_LOST", "inotify overflow, unmount or removed watch")
                roles = self.watches.get(wd)
                require(roles is not None, "OBSERVATION_LOST", "unregistered watch")
                relevant = [role for role in roles if role[0] in ("tree", "inode") or not leaf or leaf == role[2]]
                if relevant:
                    found.append(dict(mask=mask & ~0x40000000, cookie=cookie, name=leaf, roles=relevant))
        return found

    def assert_clean(self, exchange=None):
        self.tick()
        self._monitor_live()
        require(not self.broken, "CHANGE_OBSERVED", "read lease break signal")
        for fd in self.leases.values():
            try:
                current = fcntl.fcntl(fd, fcntl.F_GETLEASE)
            except OSError as exc:
                raise FileError("OBSERVATION_LOST", "lease descriptor lost") from exc
            require(current == fcntl.F_RDLCK, "CHANGE_OBSERVED", "read lease no longer intact")
        events = self._events()
        if exchange is None:
            require(not events, "CHANGE_OBSERVED", "changes during stable window: " + repr(events))
        else:
            self._check_exchange_events(events, exchange)

    def _check_exchange_events(self, events, exchange):
        paths = {str(Path(path)) for path in exchange}
        moves, self_moves = {}, set()
        for event in events:
            mask = event["mask"]
            if mask == 0x800 and not event["name"]:
                roles = [r for r in event["roles"] if r[0] == "tree" and r[2] == "." and r[1] in paths]
                require(roles, "CHANGE_OBSERVED", "unrelated moved directory")
                self_moves.update(r[1] for r in roles)
            elif mask in (0x40, 0x80) and event["cookie"]:
                actual = {str(Path(r[1]) / event["name"]) for r in event["roles"] if r[0] == "parent"}
                require(actual and actual <= paths, "CHANGE_OBSERVED", "unrelated rename")
                moves.setdefault(event["cookie"], []).append((mask, actual))
            else:
                raise FileError("CHANGE_OBSERVED", "unrelated event at exchange: " + repr(event))
        require(self_moves == paths and len(moves) == 2, "OBSERVATION_LOST", "missing exchange watch/cookie evidence")
        edges = []
        for pair in moves.values():
            require(len(pair) == 2 and {x[0] for x in pair} == {0x40, 0x80},
                    "CHANGE_OBSERVED", "incomplete rename cookie pair")
            source = next(x[1] for x in pair if x[0] == 0x40)
            target = next(x[1] for x in pair if x[0] == 0x80)
            require(len(source) == len(target) == 1 and source != target and source | target == paths,
                    "CHANGE_OBSERVED", "cookie does not connect original two names")
            edges.append((next(iter(source)), next(iter(target))))
        require(edges[0] == edges[1][::-1], "CHANGE_OBSERVED", "rename pairs are not a single exchange")

    def verify_roots(self, exchanged=False):
        expected = [root for _, root in self.roots]
        if exchanged:
            expected.reverse()
        for (path, _), root in zip(self.roots, expected):
            require(identity(path) == root, "STALE_BINDING", "root identity changed within window")

    def __exit__(self, exc_type, exc, tb):
        for fd in self.leases.values():
            try:
                fcntl.fcntl(fd, fcntl.F_SETLEASE, fcntl.F_UNLCK)
            finally:
                os.close(fd)
        self.leases.clear()
        if self.monitor >= 0:
            try:
                if os.readlink(f"/proc/self/fd/{self.monitor}") == "anon_inode:inotify":
                    os.close(self.monitor)
            except OSError:
                pass
            self.monitor = -1
        if self.entered:
            signal.signal(signal.SIGIO, self.prior)
            self.entered = False
        _SIGNAL_LOCK.release()
