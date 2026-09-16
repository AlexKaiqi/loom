"""Fixed Unix Engine transport and bounded, non-shell helper invocations."""

from pathlib import Path
from contextlib import nullcontext
from urllib.parse import quote
import http.client, json, os, selectors, socket, subprocess, sys, time
from .errors import ExecutionError, require

PROFILE = json.loads((Path(__file__).parent / "profile.json").read_text())
SECCOMP = Path(__file__).parent / "seccomp.json"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}

# Platform branch (AGENTS.md): the docker CLI path is host-dependent. Docker
# Desktop on macOS installs at /usr/local/bin/docker; Linux hosts keep the
# historical /usr/bin/docker. LORE_DOCKER_CLI overrides explicitly.
DOCKER_CLI = os.environ.get("LORE_DOCKER_CLI") or (
    "/usr/local/bin/docker" if sys.platform == "darwin" else "/usr/bin/docker"
)


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path, timeout=5):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def command(argv, data=None, limit=16777216, timeout=10):
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ENV,
        close_fds=True,
    )
    watch = selectors.DefaultSelector()
    values = {"stdout": bytearray(), "stderr": bytearray()}
    pending = memoryview(data or b"")
    deadline = time.monotonic() + timeout
    for name in values:
        os.set_blocking(getattr(process, name).fileno(), False)
        watch.register(getattr(process, name), selectors.EVENT_READ, name)
    if process.stdin:
        os.set_blocking(process.stdin.fileno(), False)
        if pending:
            watch.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        else:
            process.stdin.close()
    try:
        while watch.get_map():
            require(
                time.monotonic() < deadline, "ENGINE_TIMEOUT", "bounded helper deadline"
            )
            for key, _ in watch.select(0.02):
                if key.data == "stdin":
                    try:
                        n = os.write(key.fd, pending[:65536])
                        pending = pending[n:]
                    except BrokenPipeError:
                        pending = memoryview(b"")
                    if not pending:
                        watch.unregister(key.fileobj)
                        process.stdin.close()
                    continue
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    watch.unregister(key.fileobj)
                    continue
                values[key.data].extend(chunk)
                require(
                    sum(map(len, values.values())) <= limit,
                    "ARCHIVE_LIMIT",
                    "bounded helper bytes exceeded",
                )
        rc = process.wait(timeout=1)
        require(
            rc == 0,
            "ENGINE_ERROR",
            bytes(values["stderr"]).decode(errors="replace")[:1000],
        )
        return bytes(values["stdout"])
    finally:
        watch.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        for port in (process.stdin, process.stdout, process.stderr):
            if port and not port.closed:
                port.close()


class Engine:
    def __init__(self, endpoint=None):
        from .journal import digest

        if endpoint is None:
            context = json.loads(
                command([DOCKER_CLI, "context", "inspect"], limit=1048576)
            )
            endpoint = context[0]["Endpoints"]["docker"]["Host"]
        require(
            endpoint.startswith("unix://"),
            "UNSUPPORTED",
            "Linux Unix Engine endpoint required",
        )
        self.path = endpoint[7:]
        actual = self.call("GET", "/version")
        require(
            actual["Version"] == PROFILE["engine_version"],
            "UNSUPPORTED",
            "Engine capability profile differs",
        )
        # Per-entry identity preflight (amendment-linux-browser-2026-09-15):
        # every registered profile must resolve to a locally present image and an
        # intact profile-scoped seccomp file; registration promises presence.
        from .requests import PROFILES

        base = Path(__file__).parent
        require(
            PROFILES,
            "PROFILE_CHANGED",
            "environment registry is empty",
        )
        for entry in PROFILES.values():
            seccomp_file = base / entry.get("seccomp_path", "seccomp.json")
            require(
                digest(seccomp_file.read_bytes()) == entry["seccomp_sha256"],
                "PROFILE_CHANGED",
                "seccomp bytes differ for " + entry["id"],
            )
            image = self.call("GET", "/images/" + entry["image"] + "/json")
            require(
                image["Id"] == entry["image_id"],
                "UNSUPPORTED",
                "image identity differs for " + entry["id"],
            )

    def call(self, method, path, value=None, missing=False):
        h = UnixHTTP(self.path)
        data = (
            None if value is None else json.dumps(value, separators=(",", ":")).encode()
        )
        try:
            h.request(
                method,
                "/v1.48" + path,
                body=data,
                headers={"Content-Type": "application/json"},
            )
            response = h.getresponse()
            body = response.read(4194305)
            require(len(body) <= 4194304, "ENGINE_ERROR", "Engine response cap")
            if missing and response.status == 404:
                return None
            require(
                200 <= response.status < 300,
                "ENGINE_ERROR",
                "Engine "
                + str(response.status)
                + ": "
                + body.decode(errors="replace")[:500],
            )
            return json.loads(body) if body else None
        except (OSError, http.client.HTTPException) as exc:
            raise ExecutionError("ENGINE_UNAVAILABLE", str(exc)) from exc
        finally:
            h.close()

    def inspect(self, cid):
        return self.call("GET", "/containers/" + cid + "/json", missing=True)

    def inspect_exec(self, eid):
        return self.call("GET", "/exec/" + eid + "/json", missing=True)

    def options(self, budget, seccomp_path=None):
        return [
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--security-opt",
            "seccomp=" + str(seccomp_path or SECCOMP),
            "--network",
            "none",
            "--memory",
            str(budget["memory_bytes"]),
            "--memory-swap",
            str(budget["memory_bytes"]),
            "--pids-limit",
            str(budget["pids"]),
            "--cpus",
            str(budget["cpu"]),
            "--shm-size",
            str(budget["shm_bytes"]),
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size="
            + str(budget["tmp_bytes"])
            + ",nr_inodes="
            + str(budget.get("tmp_inodes", 64)),
            *(
                [
                    "--tmpfs",
                    "/dev/shm:rw,nosuid,nodev,noexec,size="
                    + str(budget["shm_bytes"])
                    + ",nr_inodes="
                    + str(budget["shm_inodes"]),
                ]
                if "shm_inodes" in budget
                else []
            ),
            "--log-driver",
            "none",
        ]

    def slot_labels(self, record, role=None):
        if not record.get("slot_ref"):
            return []
        from .journal import digest

        return [
            "--label",
            "lore.x.slot_id=" + record["slot_ref"]["slot_id"],
            "--label",
            "lore.x.slot_owner=" + digest(str(self.slots.journal.root).encode()),
            "--label",
            "lore.x.role=" + (role or record["role"]),
        ]

    def helper(self, record, args, data=None, limit=16777216):
        def reclaimed(holder):
            from .journal import digest

            owner = digest(str(self.slots.journal.root).encode())
            labels = [
                "lore.x.slot_owner=" + owner,
                "lore.x.slot_id=" + record["slot_ref"]["slot_id"],
                "lore.x.role=helper",
                "lore.x.execution_id=" + holder["execution_id"],
            ]
            return not self.call(
                "GET",
                "/containers/json?all=true&filters="
                + quote(json.dumps({"label": labels})),
            )

        context = (
            self.slots.helper(record, reclaim_check=reclaimed)
            if getattr(self, "slots", None) and record.get("slot_ref")
            else nullcontext()
        )
        with context:
            return self._helper(record, args, data, limit)

    def _helper(self, record, args, data=None, limit=16777216):
        b = record.get("limits", record["request"]["budgets"])
        if record.get("slot_ref"):
            from .journal import digest

            owner = digest(str(self.slots.journal.root).encode())
            filters = quote(
                json.dumps(
                    {
                        "label": [
                            "lore.x.slot_owner=" + owner,
                            "lore.x.slot_id=" + record["slot_ref"]["slot_id"],
                        ]
                    }
                )
            )
            originals = self.call("GET", "/containers/json?all=true&filters=" + filters)
            active = [
                item for item in originals if item["State"] not in ("exited", "dead")
            ]
            require(
                len(active) < 3
                and not any(
                    item["Labels"].get("lore.x.role") == "helper" for item in active
                ),
                "INCOMPLETE_OBSERVATION",
                "original helper role remains occupied",
            )
            b = {
                **b,
                "memory_bytes": 134217728,
                "cpu": 0.25,
                "pids": 32,
                "tmp_bytes": 1048576,
                "tmp_inodes": 64,
                "shm_bytes": 1048576,
                "shm_inodes": 64,
            }

        cid = (
            command(
                [
                    DOCKER_CLI,
                    "create",
                    *self.options(b),
                    *self.slot_labels(record, "helper"),
                    "--label",
                    "lore.x.execution_id=" + record["request"]["execution_id"],
                    *(["-i"] if data is not None else []),
                    *args,
                ]
            )
            .decode()
            .strip()
        )
        try:
            return command(
                [
                    DOCKER_CLI,
                    "start",
                    "-a",
                    *(["-i"] if data is not None else []),
                    cid,
                ],
                data=data,
                limit=limit,
            )
        finally:
            self.call("DELETE", "/containers/" + cid + "?force=true", missing=True)
