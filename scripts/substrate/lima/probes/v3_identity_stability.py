"""V3 probe: shared-mount dev/ino identity stability across VM lifecycle (DRAFT).

Protocol: validation/substrate/protocol-substrate-001.json, batch V3_identity_stability.
Status: DRAFT / UNVERIFIED — never executed; must not be executed until the suite
is frozen and the S0 identity gate passes.

Runs INSIDE the pinned Lima VM. Records a manifest (lore_files.util.identity:
dev/ino plus sha256 and size) for a fixed file set on the mount under test and,
as a control, on the VM-local disk. compare mode recomputes and diffs; any dev
or ino drift is a criterion violation per the preregistered pass criteria.

Modes:
  record   write manifest JSON to --manifest.
  compare  compare against --manifest; exit 0 identical / 2 drift (the diff is
           the FAIL evidence, recorded verbatim, never retried).

Negative control (run separately by the runner): record a manifest, replace one
file's bytes, compare — must report drift; proves the comparator can refuse.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

LORE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(LORE_ROOT))

from lore_files.util import identity  # noqa: E402

FIXED_SET = ["alpha.txt", "beta/one.txt", "beta/two.txt"]
CONTENT = {
    "alpha.txt": b"substrate-v3-alpha\n",
    "beta/one.txt": b"substrate-v3-one\n",
    "beta/two.txt": b"substrate-v3-two\n",
}


def seed(root: Path) -> None:
    for rel, data in CONTENT.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)


def manifest(root: Path) -> dict:
    out = {}
    for rel in FIXED_SET:
        target = root / rel
        data = target.read_bytes()
        item = identity(target)
        item.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data), rel=rel)
        out[rel] = item
    return {"root": str(root), "files": out}


def diff(before: dict, after: dict) -> list:
    rows = []
    for rel in FIXED_SET:
        old, new = before["files"].get(rel), after["files"].get(rel)
        if old is None or new is None:
            rows.append({"rel": rel, "field": "presence", "before": old, "after": new})
            continue
        for field in ("dev", "ino", "sha256", "size"):
            if old[field] != new[field]:
                rows.append({"rel": rel, "field": field, "before": old[field], "after": new[field]})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["record", "compare"], required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--seed", action="store_true", help="create the fixed set if absent")
    args = parser.parse_args()

    if sys.platform != "linux":
        print(json.dumps({"verdict": "BLOCKED", "reason": "probe requires Linux guest, got " + sys.platform}))
        return 3

    root = Path(args.root)
    if args.seed:
        seed(root)
    current = manifest(root)
    if args.mode == "record":
        Path(args.manifest).write_text(json.dumps(current, indent=1))
        print(json.dumps({"verdict": "RECORDED", "manifest": args.manifest, "files": FIXED_SET}))
        return 0

    stored = json.loads(Path(args.manifest).read_text())
    rows = diff(stored, current)
    if rows:
        print(json.dumps({"verdict": "FAIL", "reason": "identity drift across VM lifecycle",
                          "diff": rows, "before": stored, "after": current}))
        return 2
    print(json.dumps({"verdict": "PASS", "reason": "dev/ino and content stable", "files": FIXED_SET}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
