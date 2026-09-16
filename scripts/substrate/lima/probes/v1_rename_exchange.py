"""V1 probe: renameat2 RENAME_EXCHANGE on the substrate mount (PREREGISTERED DRAFT).

Protocol: validation/substrate/protocol-substrate-001.json, batch V1_rename_exchange.
Status: DRAFT / UNVERIFIED — never executed; must not be executed until the suite
is frozen and the S0 identity gate passes.

Runs INSIDE the pinned Lima VM. Reuses product primitives (lore_files.install
_renameat2 binding, lore_files.util.identity, lore_files.metadata.walk) so the
observed mechanism is the product's actual syscall path; expectations come from
the preregistered contract (POSIX exchange semantics + state-swap equality),
not from this implementation.

Equality semantics follow the F publish contract (lore_files/install.py): the
post-exchange state of each path must equal the pre-exchange state of the OTHER
path, including metadata, content sha256 and hardlink groups (walk dicts). A
static expected tree cannot be constructed because mtime/uid/xattrs are
environment facts; build correctness is checked per-file via entry sha256.

Modes:
  exchange  main criterion: atomic swap of two fixed trees on the target mount;
            success requires return 0 + state-swap equality + dev/ino swap.
  exdev     negative control: exchange across two filesystems must fail with
            EXDEV; a succeeding exchange violates the expectation (exit 2).
  corrupt   negative control: the state comparison must REJECT a mismatched
            tree (proves the checker can refuse); exit 0 when rejection observed.

Exit codes: 0 = criterion met / expected rejection observed;
            2 = criterion violated (recorded verbatim, never retried);
            3 = environment/unsupported (BLOCKED, not FAIL).
"""
import argparse
import ctypes
import errno
import hashlib
import json
import shutil
import sys
from pathlib import Path

LORE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(LORE_ROOT))

from lore_files.errors import FileError          # noqa: E402
from lore_files.install import _renameat2        # noqa: E402
from lore_files.metadata import walk             # noqa: E402
from lore_files.util import identity, sync_dir   # noqa: E402

RENAME_EXCHANGE = 2
TREE_BASE = {"alpha.txt": b"substrate-v1-base-alpha\n", "beta/deep.txt": b"substrate-v1-base-beta\n"}
TREE_STAGED = {"alpha.txt": b"substrate-v1-staged-alpha\n", "beta/deep.txt": b"substrate-v1-staged-beta\n"}
LIMITS = {"max_entries": 4096, "max_logical_bytes": 1 << 20, "max_archive_bytes": 1 << 20, "window_seconds": 10}


def _build(root: Path, tree: dict) -> None:
    root.mkdir(parents=True)
    for rel, data in tree.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _state(root: Path) -> dict:
    return walk(root, LIMITS)[0]


def _verify_build(state: dict, tree: dict, label: str) -> None:
    entries = state["entries"]
    # walk records the root itself as "." plus every intermediate directory.
    expected_keys = {"."} | set(tree) | {"beta"}
    if set(entries) != expected_keys:
        raise AssertionError(label + ": unexpected entry set " + repr(sorted(entries)))
    for rel, data in tree.items():
        observed = entries.get(rel)
        if observed is None or observed.get("sha256") != hashlib.sha256(data).hexdigest():
            raise AssertionError(label + ": content mismatch for " + rel)


def _exchange(root: Path, staged: Path) -> dict:
    pre_root, pre_staged = _state(root), _state(staged)
    _verify_build(pre_root, TREE_BASE, "pre-exchange root")
    _verify_build(pre_staged, TREE_STAGED, "pre-exchange staged")
    root_id, staged_id = identity(root), identity(staged)
    result = _renameat2()(-100, bytes(root), -100, bytes(staged), RENAME_EXCHANGE)
    code = ctypes.get_errno()
    record = {"renameat2_ret": result, "errno": code}
    if result != 0:
        record["verdict"] = "FAIL"
        record["reason"] = "exchange returned nonzero errno=" + str(code)
        return record
    sync_dir(root.parent)
    if staged.parent != root.parent:
        sync_dir(staged.parent)
    post_root, post_staged = _state(root), _state(staged)
    root_id_after, staged_id_after = identity(root), identity(staged)
    try:
        if post_root != pre_staged:
            raise AssertionError("post-exchange root state != pre-exchange staged state "
                                 "(silent data loss shape, cf. docker/for-mac#7687)")
        if post_staged != pre_root:
            raise AssertionError("post-exchange staged state != pre-exchange root state")
        if root_id_after != staged_id or staged_id_after != root_id:
            raise AssertionError("directory dev/ino not swapped by exchange")
    except AssertionError as exc:
        record["verdict"] = "FAIL"
        record["reason"] = str(exc)
        return record
    record["verdict"] = "PASS"
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["exchange", "exdev", "corrupt"], required=True)
    parser.add_argument("--parent", required=True, help="directory on the mount under test")
    args = parser.parse_args()

    if sys.platform != "linux":
        print(json.dumps({"verdict": "BLOCKED", "reason": "probe requires Linux guest, got " + sys.platform}))
        return 3

    if args.mode == "exchange":
        parent = Path(args.parent)
        root, staged = parent / "v1-base", parent / "v1-staged"
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(staged, ignore_errors=True)
        _build(root, TREE_BASE)
        _build(staged, TREE_STAGED)
        record = _exchange(root, staged)
        print(json.dumps(record, default=str))
        return 0 if record["verdict"] == "PASS" else 2

    if args.mode == "exdev":
        parent = Path(args.parent)
        # /dev/shm is a distinct filesystem (tmpfs) inside the pinned guest.
        other = Path("/dev/shm/v1-exdev-staged")
        shutil.rmtree(parent / "v1-base", ignore_errors=True)
        shutil.rmtree(other, ignore_errors=True)
        _build(parent / "v1-base", TREE_BASE)
        _build(other, TREE_STAGED)
        result = _renameat2()(-100, bytes(parent / "v1-base"), -100, bytes(other), RENAME_EXCHANGE)
        code = ctypes.get_errno()
        record = {"renameat2_ret": result, "errno": code, "expected": "nonzero with EXDEV(18)"}
        if result != 0 and code == errno.EXDEV:
            record["verdict"] = "PASS"
            out = 0
        else:
            record["verdict"] = "FAIL"
            record["reason"] = "expected EXDEV rejection; observed ret=%s errno=%s" % (result, code)
            out = 2
        print(json.dumps(record, default=str))
        return out

    if args.mode == "corrupt":
        # The state comparison must refuse a mismatched tree: build a
        # staged-content tree and compare it against a base-content reference.
        parent = Path(args.parent)
        reference, target = parent / "v1-ref-base", parent / "v1-corrupt"
        shutil.rmtree(reference, ignore_errors=True)
        shutil.rmtree(target, ignore_errors=True)
        _build(reference, TREE_BASE)
        _build(target, TREE_STAGED)
        ref_state, actual_state = _state(reference), _state(target)
        if actual_state != ref_state:
            print(json.dumps({"verdict": "PASS", "reason": "rejection observed: mismatched tree differs from reference"}))
            return 0
        print(json.dumps({"verdict": "FAIL", "reason": "state comparison accepted a mismatched tree"}))
        return 2
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FileError as exc:
        print(json.dumps({"verdict": "FAIL", "reason": "FileError: %s" % exc}))
        sys.exit(2)
