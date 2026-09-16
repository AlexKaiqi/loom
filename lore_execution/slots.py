"""X-owned slot reservations. A transport never owns quota or reclaims it."""

from contextlib import contextmanager
from pathlib import Path
import copy
import os
import stat
import threading

from .errors import require
from .journal import atomic, canonical, digest

MIB = 1048576
# 2026-09-14 (m01-output-budget amendment, batch-ag counterexample): the
# original slot envelope (3 MiB / 384 inodes per execution) was exhausted by a
# real archive-enabled chain: the notification-step invocation re-verified the
# whole task and filled the bounded slot history (SLOT_EXHAUSTED -> invocation
# paused -> chain could not release its publications). The envelope scales
# 8x on both axes; the helper container budgets derive from these constants.
CONTROL_BYTES = 8 * MIB
CONTROL_INODES = 1024


class SlotLedger:
    def __init__(self, journal, trusted_config):
        self.journal = journal
        self.config = trusted_config or {}
        self.registrations = {}
        self.helper_locks = {}
        for original in self.config.get("slots", []):
            slot = copy.deepcopy(original)
            sid = slot["slot_id"]
            require(
                sid not in self.registrations,
                "INVALID_REQUEST",
                "duplicate trusted slot",
            )
            require(
                Path(slot["state_root"]).resolve() == journal.root,
                "UNAUTHORIZED",
                "slot belongs to another execution store",
            )
            require(
                digest(canonical(slot["plan"])) == slot["plan_sha256"],
                "INVALID_REQUEST",
                "original slot plan digest differs",
            )
            self.registrations[sid] = slot
            self.helper_locks[sid] = threading.Lock()
            with journal.lock:
                old = self._load(sid)
                if old is not None:
                    require(
                        old["registration"] == slot,
                        "ID_CONFLICT",
                        "trusted slot registration changed",
                    )
                else:
                    helper = dict(
                        id="helper-" + digest(sid.encode()),
                        execution_id=None,
                        object_generation=None,
                        request_digest=slot["plan_sha256"],
                        role="helper",
                        state="RESERVED",
                        memory_bytes=slot["plan"]["helper_memory_bytes"],
                        cpu=slot["plan"]["cpus"]["helper"],
                        writable_bytes=3 * CONTROL_BYTES,
                        writable_inodes=128 + CONTROL_INODES,
                        objects=1,
                        holder=None,
                    )
                    row = dict(
                        slot_id=sid,
                        revision=slot["revision"],
                        plan_sha256=slot["plan_sha256"],
                        plan=slot["plan"],
                        registration=slot,
                        reservations={helper["id"]: helper},
                        released=False,
                    )
                    self._save(row)

    def _directory(self, sid):
        return self.journal.root / ".slots" / digest(sid.encode())

    def _load(self, sid):
        import json

        path = self._directory(sid) / "current.json"
        return json.loads(path.read_bytes()) if path.exists() else None

    def _save(self, row):
        directory = self._directory(row["slot_id"])
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        value = {k: v for k, v in row.items() if k != "record_ref"}
        raw = canonical(value)
        ref = dict(
            path=str(directory / ("slot-" + digest(raw) + ".blob")),
            sha256=digest(raw),
            size=len(raw),
        )
        if not Path(ref["path"]).exists():
            allocated, count, _ = self._allocated(directory)
            # Snapshot and atomic-current temporary coexist with the old current.
            require(
                allocated + 2 * self._blocks(len(raw) + 4096) <= 3 * CONTROL_BYTES
                and count + 3 <= 3 * CONTROL_INODES,
                "SLOT_EXHAUSTED",
                "bounded original slot history is full",
            )
            self._assert_totals(row, 2 * self._blocks(len(raw) + 4096), 3)
            atomic(ref["path"], raw)
        row["record_ref"] = ref
        atomic(directory / "current.json", canonical(row))

    @staticmethod
    def _blocks(size):
        return ((size + 4095) // 4096) * 4096

    @staticmethod
    def _allocated(directory):
        allocated = count = 0
        seen = set()
        for parent, dirs, files in os.walk(directory, followlinks=False):
            for name in dirs + files:
                path = Path(parent) / name
                st = path.lstat()
                require(
                    not stat.S_ISLNK(st.st_mode),
                    "INCOMPLETE_OBSERVATION",
                    "spool contains an unexpected alias",
                )
                key = (st.st_dev, st.st_ino)
                if key not in seen:
                    allocated += st.st_blocks * 512
                    count += 1
                    seen.add(key)
        # Unlinked files still held by this X observer remain physical debt.
        for fd in Path("/proc/self/fd").iterdir():
            try:
                target = os.readlink(fd)
                if target.startswith(str(directory) + "/") and target.endswith(
                    " (deleted)"
                ):
                    st = fd.stat()
                    key = (st.st_dev, st.st_ino)
                    if key not in seen:
                        allocated += st.st_blocks * 512
                        count += 1
                        seen.add(key)
            except FileNotFoundError:
                pass
        return allocated, count, seen

    def _spool_fact(self, reservation):
        directory = self.journal.root / digest(reservation["execution_id"].encode())
        original = reservation.get("retained_spool")
        if not directory.exists():
            require(
                original is not None,
                "INCOMPLETE_OBSERVATION",
                "unmeasured old spool disappeared",
            )
            return copy.deepcopy(original)
        st = directory.lstat()
        require(
            stat.S_ISDIR(st.st_mode),
            "INCOMPLETE_OBSERVATION",
            "old spool root is not its original directory",
        )
        root = {"dev": st.st_dev, "ino": st.st_ino}
        if original is not None:
            require(
                original["path"] == str(directory) and original["root"] == root,
                "INCOMPLETE_OBSERVATION",
                "retained spool root was replaced",
            )
        allocated, count, _ = self._allocated(directory)
        return dict(
            path=str(directory),
            root=root,
            allocated_bytes=max(
                allocated + st.st_blocks * 512,
                (original or {}).get("allocated_bytes", 0),
            ),
            inodes=max(count + 1, (original or {}).get("inodes", 0)),
        )

    def _assert_totals(self, row, extra_slot_bytes=0, extra_slot_inodes=0):
        totals = dict(
            objects=0, memory_bytes=0, cpu=0, writable_bytes=0, writable_inodes=0
        )
        for reservation in row["reservations"].values():
            if reservation["state"] in ("RELEASED", "RECLAIMED"):
                debt = self._spool_fact(reservation)
                totals["writable_bytes"] += debt["allocated_bytes"]
                totals["writable_inodes"] += debt["inodes"]
            else:
                for key in totals:
                    totals[key] += reservation[key]
        # The helper's reservation includes one control allowance. Account for
        # every additional old slot snapshot and the atomic-write peak as well.
        allocated, count, _ = self._allocated(self._directory(row["slot_id"]))
        totals["writable_bytes"] += max(0, allocated + extra_slot_bytes - CONTROL_BYTES)
        totals["writable_inodes"] += max(0, count + extra_slot_inodes - CONTROL_INODES)
        plan = row["plan"]
        for key, maximum in [
            ("objects", plan["max_objects"]),
            ("memory_bytes", plan["memory_bytes"]),
            ("cpu", sum(plan["cpus"].values())),
            ("writable_bytes", plan["all_active_writable_bytes"]),
            ("writable_inodes", plan["all_active_writable_inodes"]),
        ]:
            require(
                totals[key] <= maximum,
                "SLOT_EXHAUSTED",
                "original slot including retained spool " + key + " exhausted",
            )

    def _registration(self, slot_ref):
        require(
            type(slot_ref) is dict, "UNAUTHORIZED", "missing original slot reference"
        )
        sid = slot_ref.get("slot_id")
        require(sid in self.registrations, "UNAUTHORIZED", "slot is not registered")
        slot = self.registrations[sid]
        require(
            slot_ref.get("owner") == "trusted-X-configuration"
            and slot_ref.get("revision") == slot["revision"]
            and slot_ref.get("plan_sha256") == slot["plan_sha256"],
            "UNAUTHORIZED",
            "original slot association differs",
        )
        return slot

    def reserve(self, record, slot_ref, role):
        if slot_ref is None:
            return None
        slot = self._registration(slot_ref)
        require(
            role in ("session", "tool") and slot_ref.get("role") == role,
            "UNAUTHORIZED",
            "original slot role differs",
        )
        request, binding = record["request"], record["binding"]
        b, plan = request["budgets"], slot["plan"]
        memory, cpu = (
            plan[role + "_memory_bytes"],
            plan["cpus"]["S" if role == "session" else "tool"],
        )
        require(
            b["memory_bytes"] <= memory and b["cpu"] <= cpu,
            "SLOT_EXHAUSTED",
            "request exceeds original role reservation",
        )
        mounts = (
            b.get("work_bytes", b.get("volume_bytes", 0))
            + b["tmp_bytes"]
            + b["shm_bytes"]
        )
        inodes = (
            b.get("work_inodes", b.get("inodes", 0))
            + b.get("tmp_inodes", 64)
            + b.get("shm_inodes", 64)
        )
        rid = digest(
            canonical(
                [
                    binding["execution_id"],
                    binding["object_generation"],
                    binding["request_digest"],
                ]
            )
        )
        reservation = dict(
            id=rid,
            execution_id=binding["execution_id"],
            object_generation=binding["object_generation"],
            request_digest=binding["request_digest"],
            role=role,
            state="RESERVED",
            memory_bytes=memory,
            cpu=cpu,
            writable_bytes=mounts
            + b["stdout_bytes"]
            + b["stderr_bytes"]
            + 2 * b["archive_bytes"]
            + CONTROL_BYTES,
            writable_inodes=inodes + CONTROL_INODES + 4,
            objects=1,
            mount_bytes=mounts,
            mount_inodes=inodes,
        )
        with self.journal.lock:
            row = self._load(slot["slot_id"])
            prior = row["reservations"].get(rid)
            if prior is not None:
                require(
                    all(prior[k] == v for k, v in reservation.items() if k != "state"),
                    "ID_CONFLICT",
                    "original reservation changed",
                )
            else:
                active = [
                    r
                    for r in row["reservations"].values()
                    if r["state"] not in ("RELEASED", "RECLAIMED")
                ]
                require(
                    not any(r["role"] == role for r in active),
                    "SLOT_EXHAUSTED",
                    "original role is still occupied",
                )
                row["reservations"][rid] = reservation
                self._assert_totals(row)
                self._save(row)
            binding.update(
                slot_id=slot["slot_id"],
                slot_revision=slot["revision"],
                slot_reservation_id=rid,
            )
            record["artifacts"]["slot"] = copy.deepcopy(row["record_ref"])
            self.journal.put(record)
            return copy.deepcopy(prior or reservation)

    def snapshot(self, record):
        sid = record["binding"].get("slot_id")
        if sid is None:
            return None
        with self.journal.lock:
            row = self._load(sid)
            require(
                row is not None,
                "INCOMPLETE_OBSERVATION",
                "original slot record missing",
            )
            return copy.deepcopy(row["record_ref"])

    def release(self, record):
        sid = record["binding"].get("slot_id")
        if sid is None:
            return None
        with self.journal.lock:
            require(
                record.get("released") is True,
                "INCOMPLETE_OBSERVATION",
                "physical execution removal not confirmed",
            )
            require(
                record["request"]["schema_version"] == 1
                or all(
                    c.get("retention", {}).get("state") == "RELEASED"
                    for c in record.get("checkpoints", {}).values()
                ),
                "INCOMPLETE_OBSERVATION",
                "local checkpoint ownership remains live",
            )
            row = self._load(sid)
            reservation = row["reservations"][record["binding"]["slot_reservation_id"]]
            if (
                reservation["state"] != "RELEASED"
                or "retained_spool" not in reservation
            ):
                # Only the removed Engine role is returned. Original stream,
                # call, metadata and deleted-open file blocks remain charged.
                reservation["retained_spool"] = self._spool_fact(reservation)
                reservation["state"] = "RELEASED"
                self._save(row)
            return copy.deepcopy(row["record_ref"])

    def guard_write(self, record, path, data_bytes):
        sid = record["binding"].get("slot_id")
        if sid is None:
            return
        require(
            type(data_bytes) is int and data_bytes >= 0,
            "INVALID_REQUEST",
            "invalid write reservation",
        )
        directory = self.journal.directory(record["request"]["execution_id"])
        path = Path(path)
        require(
            path.is_absolute() and path.parent.resolve().is_relative_to(directory),
            "UNAUTHORIZED",
            "write outside original role spool",
        )
        with self.journal.lock:
            row = self._load(sid)
            reserved = row["reservations"][record["binding"]["slot_reservation_id"]]
            require(
                reserved["state"] not in ("RELEASED", "RECLAIMED"),
                "SLOT_EXHAUSTED",
                "role was already released",
            )
            self._assert_totals(row)
            allocated, count, _ = self._allocated(directory)
            b = record["request"]["budgets"]
            peak = self._blocks(data_bytes)
            require(
                allocated + peak
                <= b["stdout_bytes"]
                + b["stderr_bytes"]
                + 2 * b["archive_bytes"]
                + CONTROL_BYTES
                and count + 1 <= CONTROL_INODES + 4,
                "SLOT_EXHAUSTED",
                "physical role spool reservation exhausted",
            )

            def payload(p):
                return p.name.startswith(("checkpoint-", "stdout.", "stderr."))

            control = sum(
                p.lstat().st_blocks * 512
                for p in directory.rglob("*")
                if p.is_file() and not payload(p)
            )
            if not payload(path):
                require(
                    control + peak <= CONTROL_BYTES,
                    "SLOT_EXHAUSTED",
                    "original control record allowance exhausted",
                )

    @contextmanager
    def helper(self, record, reclaim_check=None):
        sid = record["binding"].get("slot_id")
        if sid is None:
            yield
            return
        lock = self.helper_locks[sid]
        require(
            lock.acquire(timeout=10), "SLOT_EXHAUSTED", "shared helper remains occupied"
        )

        def reclaimed(holder):
            if not callable(reclaim_check):
                return False
            try:
                return reclaim_check(copy.deepcopy(holder)) is True
            except Exception:
                return False

        try:
            with self.journal.lock:
                row = self._load(sid)
                helper = next(
                    r for r in row["reservations"].values() if r["role"] == "helper"
                )
                old_holder = copy.deepcopy(helper.get("holder"))
                unresolved = helper["state"] != "RESERVED" or old_holder is not None
            if unresolved:
                require(
                    old_holder is not None and reclaimed(old_holder),
                    "INCOMPLETE_OBSERVATION",
                    "old helper physical state is unresolved",
                )
                with self.journal.lock:
                    row = self._load(sid)
                    helper = row["reservations"][helper["id"]]
                    helper.update(state="RESERVED", holder=None)
                    self._save(row)
            with self.journal.lock:
                row = self._load(sid)
                helper = row["reservations"][helper["id"]]
                holder = {
                    k: record["binding"][k]
                    for k in ("execution_id", "object_generation", "request_digest")
                }
                helper.update(state="ACTIVE", holder=holder)
                self._save(row)
            failed = False
            try:
                yield
            except BaseException:
                failed = True
                raise
            finally:
                confirmed = reclaimed(holder)
                with self.journal.lock:
                    row = self._load(sid)
                    current = row["reservations"][helper["id"]]
                    current.update(
                        state="RESERVED" if confirmed else "UNKNOWN",
                        holder=None if confirmed else holder,
                    )
                    self._save(row)
                if not failed:
                    require(
                        confirmed,
                        "INCOMPLETE_OBSERVATION",
                        "helper result exists but original object reclamation is unconfirmed",
                    )
        finally:
            lock.release()
