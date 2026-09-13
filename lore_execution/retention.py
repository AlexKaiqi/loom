"""Original checkpoint read pins and durable ownership handoff, without Pi policy."""

from contextlib import contextmanager
from pathlib import Path
import copy
import os
import stat

from .errors import ExecutionError, require
from .journal import digest, sync_dir


class Retention:
    def _checkpoint_item(self, record, fullref):
        require(
            type(fullref) is dict,
            "INVALID_REQUEST",
            "complete original checkpoint required",
        )
        matches = [
            c
            for c in record.get("checkpoints", {}).values()
            if c.get("artifact") == fullref
        ]
        require(
            len(matches) == 1,
            "UNAUTHORIZED",
            "checkpoint is not an original registered full reference",
        )
        return matches[0]

    def _pin_key(self, fullref):
        return fullref["path"], fullref["sha256"], fullref["size"]

    def _pins(self):
        if not hasattr(self, "_checkpoint_read_pins"):
            self._checkpoint_read_pins = {}
        return self._checkpoint_read_pins

    def _open_original(self, fullref):
        path = Path(fullref["path"])
        require(
            path.is_absolute()
            and path.parent.resolve().is_relative_to(self.journal.root)
            and not path.is_symlink(),
            "INCOMPLETE_OBSERVATION",
            "original checkpoint path escaped or aliased",
        )
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            st = os.fstat(fd)
            require(
                stat.S_ISREG(st.st_mode) and st.st_size == fullref["size"],
                "INCOMPLETE_OBSERVATION",
                "original checkpoint file shape differs",
            )
            return fd, st
        except BaseException as exc:
            if "fd" in locals():
                os.close(fd)
            if isinstance(exc, OSError):
                raise ExecutionError(
                    "INCOMPLETE_OBSERVATION",
                    "original checkpoint cannot be opened: " + str(exc),
                ) from exc
            raise

    def _read_original_fd(self, fd, fullref):
        # The admitted immutable fullref supplies the cap, not an untrusted new limit.
        chunks = []
        remaining = fullref["size"] + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        require(
            len(raw) == fullref["size"] and digest(raw) == fullref["sha256"],
            "INCOMPLETE_OBSERVATION",
            "original checkpoint bytes differ",
        )
        return raw

    @contextmanager
    def _checkpoint_read(self, record, fullref):
        key = self._pin_key(fullref)
        with self.journal.lock:
            current = self.journal.get(record["request"]["execution_id"])
            item = self._checkpoint_item(current, fullref)
            require(
                item.get("retention", {}).get("state", "LIVE") == "LIVE",
                "INCOMPLETE_OBSERVATION",
                "original checkpoint release is already pending",
            )
            fd, st = self._open_original(fullref)
            self._pins()[key] = self._pins().get(key, 0) + 1
        try:
            # Another thread must be able to inspect the pin and reject, not block on this hook.
            self._barrier("checkpoint_read_open_before_close", record)
            yield self._read_original_fd(fd, fullref), st
        finally:
            with self.journal.lock:
                os.close(fd)
                count = self._pins()[key] - 1
                if count:
                    self._pins()[key] = count
                else:
                    del self._pins()[key]

    def _owner(self, record, fullref, receipt):
        require(
            self.node_profile is not None,
            "UNAUTHORIZED",
            "trusted original owner resolver missing",
        )
        return self.node_profile.verify_owner_receipt(record, fullref, receipt)

    def _checkpoint_reply(self, record, fullref, item):
        retention = item.get("retention", {})
        checkpoint = dict(
            original_full_ref=copy.deepcopy(fullref),
            state=retention.get("state", "LIVE"),
        )
        for field in ("release_id", "owner_receipt_ref"):
            if field in retention:
                checkpoint[field] = copy.deepcopy(retention[field])
        return self._response(record) | {"checkpoint": checkpoint}

    def query_checkpoint(self, id, authority, fullref):
        record = self._load(id, authority)
        with self.journal.lock:
            item = self._checkpoint_item(record, fullref)
            retention = item.get("retention", {})
            state = retention.get("state", "LIVE")
            if state != "LIVE":
                # After an intent, the confirmed independent owner is also the read source.
                # Query never unlinks, credits or updates the original release transaction.
                self._owner(record, fullref, retention["owner_receipt_ref"])
                return self._checkpoint_reply(record, fullref, item)
        with self._checkpoint_read(record, fullref):
            pass
        return self._checkpoint_reply(record, fullref, item)

    def _no_local_reader(self, fullref, original_stat):
        require(
            not self._pins().get(self._pin_key(fullref)),
            "INCOMPLETE_OBSERVATION",
            "actual original checkpoint read is pinned",
        )
        identity = original_stat["dev"], original_stat["ino"]
        for path in Path("/proc/self/fd").iterdir():
            try:
                st = path.stat()
                require(
                    (st.st_dev, st.st_ino) != identity,
                    "INCOMPLETE_OBSERVATION",
                    "original checkpoint still has an open X descriptor",
                )
            except FileNotFoundError:
                pass

    def _original_stopped(self, record):
        binding = record["binding"]
        require(
            binding.get("container_id") and binding.get("exec_id"),
            "INCOMPLETE_OBSERVATION",
            "original physical identity absent",
        )
        state = self.engine.inspect(binding["container_id"])
        executed = self.engine.inspect_exec(binding["exec_id"])
        require(
            state is None or not state["State"]["Running"],
            "INCOMPLETE_OBSERVATION",
            "original namespace remains live",
        )
        require(
            executed is None or not executed["Running"],
            "INCOMPLETE_OBSERVATION",
            "original execution remains live",
        )
        require(
            state is not None
            or record.get("released") is True
            or "stopped" in record.get("artifacts", {}),
            "INCOMPLETE_OBSERVATION",
            "missing environment without original stop evidence",
        )

    def _release_preconditions(self, record, fullref, receipt):
        owner = self._owner(record, fullref, receipt)
        if owner["handoff_kind"] == "sealed_ownership_transfer":
            self._original_stopped(record)
        else:
            successor = owner["confirmed_successor_full_ref"]
            following = self._checkpoint_item(record, successor)
            require(
                successor["object_generation"] == fullref["object_generation"]
                and successor["freeze_generation"] > fullref["freeze_generation"]
                and following.get("retention", {}).get("state", "LIVE") == "LIVE",
                "UNAUTHORIZED",
                "successor is not a newer retained original checkpoint",
            )
        return owner

    def release_checkpoint(self, id, authority, release_id, fullref, receipt):
        record = self._live(id, authority, "checkpoint")
        require(
            type(release_id) is str and 0 < len(release_id) <= 128,
            "INVALID_REQUEST",
            "stable release identity required",
        )
        with self.journal.lock:
            item = self._checkpoint_item(record, fullref)
            for previous in record["checkpoints"].values():
                old = previous.get("retention", {})
                if old.get("release_id") == release_id:
                    require(
                        previous["artifact"] == fullref
                        and old["owner_receipt_ref"] == receipt,
                        "ID_CONFLICT",
                        "release identity changed original checkpoint or owner receipt",
                    )
            retention = item.get("retention")
            if retention is not None:
                require(
                    retention["release_id"] == release_id
                    and retention["owner_receipt_ref"] == receipt,
                    "ID_CONFLICT",
                    "checkpoint already has a different release association",
                )
                self._owner(record, fullref, receipt)
                if retention["state"] == "RELEASED":
                    require(
                        not Path(fullref["path"]).exists(),
                        "INCOMPLETE_OBSERVATION",
                        "released source unexpectedly reappeared",
                    )
                    return self._checkpoint_reply(record, fullref, item)
            else:
                # Pins reject before any release record or quota mutation.
                require(
                    not self._pins().get(self._pin_key(fullref)),
                    "INCOMPLETE_OBSERVATION",
                    "actual original checkpoint read is pinned",
                )
                self._release_preconditions(record, fullref, receipt)
                try:
                    fd, st = self._open_original(fullref)
                    try:
                        self._read_original_fd(fd, fullref)
                    finally:
                        os.close(fd)
                except OSError as exc:
                    raise ExecutionError(
                        "INCOMPLETE_OBSERVATION",
                        "original source cannot be inspected: " + str(exc),
                    ) from exc
                original_stat = dict(
                    dev=st.st_dev,
                    ino=st.st_ino,
                    size=st.st_size,
                    allocated_bytes=st.st_blocks * 512,
                )
                self._no_local_reader(fullref, original_stat)
                require(
                    not any(
                        c is not item
                        and c["artifact"].get("path") == fullref["path"]
                        and c.get("retention", {}).get("state") != "RELEASED"
                        for c in record["checkpoints"].values()
                    ),
                    "INCOMPLETE_OBSERVATION",
                    "another original checkpoint still uses this physical source",
                )
                retention = dict(
                    state="RELEASE_PENDING",
                    release_id=release_id,
                    owner_receipt_ref=copy.deepcopy(receipt),
                    original_stat=original_stat,
                )
                item["retention"] = retention
                self.journal.put(record)
        self._barrier("checkpoint_release_persisted_before_unlink", record)
        with self.journal.lock:
            self._no_local_reader(fullref, retention["original_stat"])
            self._release_preconditions(record, fullref, receipt)
            path = Path(fullref["path"])
            try:
                st = path.lstat()
            except FileNotFoundError:
                st = None
            if st is not None:
                require(
                    stat.S_ISREG(st.st_mode)
                    and (st.st_dev, st.st_ino)
                    == (
                        retention["original_stat"]["dev"],
                        retention["original_stat"]["ino"],
                    )
                    and st.st_size == retention["original_stat"]["size"],
                    "INCOMPLETE_OBSERVATION",
                    "release path is no longer the original inode",
                )
                path.unlink()
                sync_dir(path.parent)
            require(
                not path.exists(),
                "INCOMPLETE_OBSERVATION",
                "original checkpoint unlink not observed",
            )
        self._barrier("checkpoint_unlinked_before_ack", record)
        with self.journal.lock:
            # This one durable state transition returns the original two-checkpoint capacity.
            # A restart with RELEASE_PENDING and absent path reaches the same transition.
            retention["state"] = "RELEASED"
            self.journal.put(record)
        return self._checkpoint_reply(record, fullref, item)
