"""V2 probe: inotify delivery from host-side writes into the pinned VM (DRAFT).

Protocol: validation/substrate/protocol-substrate-001.json, batch V2_inotify_delivery.
Status: DRAFT / UNVERIFIED — never executed; must not be executed until the suite
is frozen and the S0 identity gate passes.

Runs INSIDE the pinned Lima VM and watches a shared-mount directory with two
independent layers:

  raw layer     an observer built from the product's actual inotify binding and
                mask constants (lore_files.window_linux._inotify/_MASK/_LOST)
                with dynamic recursion (new directories get their own watch),
                collecting the raw event stream. Criterion: the preregistered
                host-side sequence must deliver create, close_write, a complete
                MOVED_FROM/MOVED_TO cookie pair, delete, and nested-dir create.
  window layer  the real lore_files.window_linux.StableWindow (lease + recursive
                inotify + lost-event masks) entered before the writes. Its
                assert_clean() MUST raise CHANGE_OBSERVED afterwards — a silent
                pass means the product observer is blind on this mount, which is
                a criterion violation, not a success.

Boundary notes (preregistered): guest read-leases do not extend to host-side
writers through the shared mount, so only inotify can detect host-side changes —
this is exactly what the batch measures. Directories created during the window
are outside window.py's entry-time recursion; the nested criterion therefore
applies to the raw layer (dynamic recursion), while the window layer only needs
to reject the change it can see.

Modes:
  observe  main criterion (writer must be started by the runner on the host).
  silent   negative control: no host writes; any event or CHANGE_OBSERVED
           violates the expectation (rejects a false-positive observer).
  shadow   negative control: monitor opened only AFTER the writer finished;
           its queue must be empty while the writer ops file is non-empty —
           rejects a probe that synthesizes events from filesystem scans.

Exit codes: 0 criterion met / expected-rejection observed; 2 violated; 3 blocked.
"""
import argparse
import json
import os
import struct
import sys
import threading
import time
from pathlib import Path

LORE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(LORE_ROOT))

from lore_files.errors import FileError                    # noqa: E402
from lore_files.util import identity                       # noqa: E402
from lore_files.window_linux import _LOST, _MASK, StableWindow, _inotify  # noqa: E402

LIMITS = {"max_entries": 4096, "max_logical_bytes": 1 << 20, "max_archive_bytes": 1 << 20, "window_seconds": 8}
EXPECTED_CLASSES = {"create", "close_write", "move_pair", "delete", "nested_create"}


class RawObserver:
    """Product-mask inotify collector with dynamic directory recursion."""

    def __init__(self, root: Path):
        self.root = root
        self.monitor = _inotify().inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.monitor < 0:
            raise RuntimeError("cannot create inotify monitor")
        self.watches = {}
        self.events = []
        self.lost = []
        self._watch_dir(root)

    def _watch_dir(self, path: Path):
        wd = _inotify().inotify_add_watch(self.monitor, os.fsencode(path), _MASK)
        if wd < 0:
            raise RuntimeError("add_watch failed: " + os.strerror(ctypes.get_errno()) + " " + str(path))
        self.watches[wd] = str(path)

    def _add_new_dirs(self):
        for path in sorted(self.root.rglob("*")):
            if path.is_dir() and str(path) not in self.watches.values():
                self._watch_dir(path)

    def collect(self) -> dict:
        while True:
            try:
                raw = os.read(self.monitor, 65536)
            except BlockingIOError:
                break
            offset = 0
            while offset < len(raw):
                wd, mask, cookie, length = struct.unpack_from("iIII", raw, offset)
                leaf = os.fsdecode(raw[offset + 16:offset + 16 + length].split(b"\0", 1)[0])
                offset += 16 + length
                if mask & _LOST:
                    self.lost.append({"wd": wd, "mask": mask, "name": leaf})
                    continue
                path = self.watches.get(wd)
                self.events.append({"wd": wd, "mask": mask, "cookie": cookie,
                                    "name": leaf, "watch": path})
        self._add_new_dirs()
        return {"events": self.events, "lost": self.lost}


def classify(events: list, lost: list, watch_root: str) -> dict:
    classes = {key: False for key in EXPECTED_CLASSES}
    moves = {}
    for event in events:
        mask = event["mask"]
        if mask & 0x100 and event["name"]:                       # IN_CREATE
            classes["create"] = True
            # Any create observed on a watch other than the root watch proves
            # delivery into a directory nested below the watch root (the raw
            # observer adds watches for directories created during the run).
            if event["watch"] != watch_root:
                classes["nested_create"] = True
        if mask & 0x8:                                           # IN_CLOSE_WRITE
            classes["close_write"] = True
        if mask & 0x40:                                          # IN_MOVED_FROM
            moves.setdefault(event["cookie"], []).append("from")
        if mask & 0x80:                                          # IN_MOVED_TO
            moves.setdefault(event["cookie"], []).append("to")
        if mask & 0x200:                                         # IN_DELETE
            classes["delete"] = True
    for cookie, sides in moves.items():
        if sorted(sides) == ["from", "to"]:
            classes["move_pair"] = True
    missing = sorted(name for name, seen in classes.items() if not seen)
    return {"delivered": {k: v for k, v in classes.items()}, "missing": missing, "moves": moves, "lost": lost}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["observe", "silent", "shadow"], default="observe")
    parser.add_argument("--root", required=True, help="watch root on the shared mount")
    parser.add_argument("--writer-events", help="JSONL file written by the host-side writer")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if sys.platform != "linux":
        print(json.dumps({"verdict": "BLOCKED", "reason": "probe requires Linux guest, got " + sys.platform}))
        return 3
    if args.mode == "observe" and not args.writer_events:
        print(json.dumps({"verdict": "BLOCKED", "reason": "observe mode requires --writer-events"}))
        return 3

    watch_root = Path(args.root) / "v2watch"
    watch_root.mkdir(parents=True, exist_ok=True)
    (watch_root / "leased.txt").write_bytes(b"substrate-v2-leased-preexisting\n")
    ops = []
    if args.writer_events and Path(args.writer_events).exists():
        for line in Path(args.writer_events).read_text().splitlines():
            if line.strip():
                ops.append(json.loads(line))

    if args.mode == "silent":
        observer = RawObserver(watch_root)
        ident = identity(watch_root)
        with StableWindow([(watch_root, ident)], LIMITS) as window:
            time.sleep(3.0)
            result = observer.collect()
            try:
                window.assert_clean()
                silent = True
            except FileError as exc:
                silent = False
                reason = str(exc)
        if result["lost"] or not silent or result["events"]:
            print(json.dumps({"verdict": "FAIL", "reason": "events observed without host writes",
                              "observer": result, "silent": silent}))
            return 2
        print(json.dumps({"verdict": "PASS", "reason": "no false positives in silent window"}))
        return 0

    if args.mode == "shadow":
        if not ops:
            print(json.dumps({"verdict": "FAIL", "reason": "writer ops file empty; host side did not run"}))
            return 2
        observer = RawObserver(watch_root)   # opened only AFTER writes finished
        result = observer.collect()
        if result["events"] or result["lost"]:
            print(json.dumps({"verdict": "FAIL", "reason": "post-hoc monitor saw events (queue pollution?)",
                              "observer": result}))
            return 2
        print(json.dumps({"verdict": "PASS", "reason": "post-hoc monitor empty while writer ops recorded; "
                                                       "probe does not synthesize events"}))
        return 0

    # ---- observe (main criterion) ----
    marker_begin, marker_done = watch_root.parent / "begin", watch_root.parent / "done"
    # Markers live OUTSIDE the watched root so they generate no inotify events.
    raw = RawObserver(watch_root)
    started = time.monotonic()
    verdict, reason, contract, result = "FAIL", "", "unknown", None
    try:
        ident = identity(watch_root)
        with StableWindow([(watch_root, ident)], LIMITS) as window:
            # Writer (host side) polls for this marker; every sequence event now
            # lands inside the entered window.
            marker_begin.write_bytes(b"1")
            while not marker_done.exists() and time.monotonic() - started < args.timeout:
                result = raw.collect()
                time.sleep(0.2)
            result = raw.collect()
            elapsed = time.monotonic() - started
            try:
                window.assert_clean()
                contract = "SILENT"
            except FileError as exc:
                contract = str(exc.code)
                reason = str(exc)
    except FileError as exc:
        print(json.dumps({"verdict": "FAIL", "reason": "window error: " + str(exc),
                          "observer": raw.collect()}))
        return 2
    if not marker_done.exists():
        print(json.dumps({"verdict": "FAIL", "reason": "writer done marker never appeared (timeout)",
                          "observer": result}))
        return 2
    classes = classify(result["events"], result["lost"], str(watch_root))
    missing = list(classes["missing"])
    if classes["lost"]:
        print(json.dumps({"verdict": "FAIL", "reason": "lost-event masks observed", "observer": result}))
        return 2
    if contract != "CHANGE_OBSERVED":
        verdict = "FAIL"
        reason = "product window did not reject host-side writes (contract=%s); observer blind" % contract
    elif missing:
        verdict = "FAIL"
        reason = "event classes not delivered: " + ",".join(missing)
    else:
        verdict = "PASS"
        reason = "all preregistered classes delivered; product window rejected the change"
    print(json.dumps({"verdict": verdict, "reason": reason, "contract": contract,
                      "observer": result, "classification": classes,
                      "writer_ops": ops, "elapsed_s": elapsed}))
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
