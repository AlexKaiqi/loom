"""2026-09-14 rebuild of the X dependency selection manifest and original-host files.

Runs INSIDE the Linux validation container (paths/inodes/uid must be the ones the
X engine and readonly manifests will later observe). Mirrors the recorded
design/g3/x-node-profile schema: files[{source,target,sha256,bytes,mode}],
links[{source,link,target}], materialized by
validation/components/x_node_profile/fixtures.py dependencies().

The manifest is environment-derived (development.md step 3: regenerate paths and
physical identity on a new host; never copy old inode/device records). The
profile.json dependency_manifest pin is updated here and recorded as a platform
revision with provenance evidence.
"""
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

REPO = Path(os.environ["REPO"])
OPT = REPO / ".runtime-env/opt"
OUT = REPO / ".runtime-env/xnode"
DESIGN = REPO / "design/g3/x-node-profile"
ORIGINAL_HOST = (REPO / "validation/session-plan-evidence/"
                 "context-independent-001/workspace/original-host")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_selection():
    files, links = [], []
    for root, dirs, names in os.walk(OPT, followlinks=False):
        dirs.sort()
        for name in sorted(names):
            path = Path(root) / name
            rel = path.relative_to(OPT).as_posix()
            if path.is_symlink():
                links.append(dict(
                    source=str(path), target="/opt/" + rel, link=os.readlink(path)))
                continue
            st = path.stat()
            files.append(dict(
                source=str(path), target="/opt/" + rel, sha256=sha(path),
                bytes=st.st_size, mode=stat.S_IMODE(st.st_mode)))
    if not files:
        raise SystemExit("no dependency files found; build the tree first")
    value = {"schema": "lore-x-dependency-selection/v1", "date": "2026-09-14",
             "platform": "linux/arm64 container build",
             "inputs": {
                 "node_version": "24.21.0",
                 "node_tarball_sha256": "6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2",
                 "pi_commit": "71dca871bc80b6bc97be37f0ca3189399d651fff",
                 "pi_derived_patch": "packages/agent/src/harness/context.ts: '@earendil-works/chord/context' -> '../../../chord/src/context/index.ts' (the recorded single-line derived patch; registry chord ships no dist, tsx loads the workspace TS source; the type-only chord import needs no change)",
                 "tsx": "4.22.1", "esbuild": "0.28.2",
                 "provider_sdks": "lazy-loaded per-provider SDK packages pruned; the product bridges its own HTTP provider and never requests a pi-ai SDK provider"},
             "files": files, "links": links}
    DESIGN.mkdir(parents=True, exist_ok=True)
    # The selection manifest is a bounded file fact (<= 2,097,152 bytes); keep it
    # compact so the recorded selection fits the product's ordinary profile cap.
    (DESIGN / "dependencies.json").write_text(json.dumps(value, separators=(",", ":")) + "\n")
    print(json.dumps({"files": len(files), "links": len(links),
                      "manifest_sha256": sha(DESIGN / "dependencies.json")}))


def materialize():
    sys.path.insert(0, str(REPO / "validation/components/x_node_profile"))
    from fixtures import dependencies  # noqa: E402  (artifacts/snapshot_fixtures live there)
    OUT.mkdir(parents=True, exist_ok=True)
    mount = dependencies(OUT)
    Path(OUT / "deps-mount.json").write_text(json.dumps(mount, indent=1) + "\n")
    return mount


def original_host():
    ORIGINAL_HOST.mkdir(parents=True, exist_ok=False)
    shutil.copy2(DESIGN / "profile.json", ORIGINAL_HOST / "profile.json")
    shutil.copy2(DESIGN / "request-template.json", ORIGINAL_HOST / "request-template.json")
    shutil.copy2(OUT / "dependencies-manifest.json",
                 ORIGINAL_HOST / "dependencies-manifest.json")
    print("original-host:", sorted(p.name for p in ORIGINAL_HOST.iterdir()))


def repin_profile():
    profile = json.loads((DESIGN / "profile.json").read_text())
    old = dict(profile["dependency_manifest"])
    profile["dependency_manifest"] = {
        "path": "design/g3/x-node-profile/dependencies.json",
        "sha256": sha(DESIGN / "dependencies.json")}
    profile["platform_revision"] = {
        "date": "2026-09-14",
        "note": "dependency selection manifest and physical identity regenerated for the "
                "linux/arm64 container build; previous pin preserved in the revision record",
        "previous_dependency_manifest": old}
    (DESIGN / "profile.json").write_text(json.dumps(profile, indent=1) + "\n")
    # The trusted config binds the design profile by bytes; original-host copy
    # must be byte-identical, so regenerate it after the re-pin.
    shutil.copy2(DESIGN / "profile.json", ORIGINAL_HOST / "profile.json")
    print("profile dependency_manifest:", profile["dependency_manifest"])


if __name__ == "__main__":
    build_selection()
    materialize()
    original_host()
    repin_profile()
