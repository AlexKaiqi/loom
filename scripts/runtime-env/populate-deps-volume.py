"""Materialize the readonly dependency tree on a Docker volume.

The validation container sees the repository through a bind mount whose
filesystem does not support xattrs (Errno 95), so the X dependency tree and its
readonly manifest must be materialized on a native container filesystem while
remaining bind-mountable by the host Docker daemon for X containers.

A named volume mounted INSIDE the helper container at its own daemon-visible
path (/var/lib/docker/volumes/<name>/_data) satisfies both: identity/xattrs are
recorded on the volume's ext4, and the recorded source path is exactly what the
Docker daemon resolves when X bind-mounts it read-only.

Run inside a container with the repository mounted read-only, the named volume
mounted at that daemon path, and DEPS_VOLUME set to the volume name.
"""
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(os.environ["REPO"])
VOLUME = os.environ["DEPS_VOLUME"]
DATA = Path("/var/lib/docker/volumes") / VOLUME / "_data"
OUT = DATA / "xnode"

sys.path.insert(0, str(REPO / "validation/components/x_node_profile"))
from fixtures import dependencies  # noqa: E402

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
mount = dependencies(OUT)
record = {
    "volume": VOLUME,
    "daemon_path": str(DATA),
    "tree": str(OUT / "dependencies"),
    "manifest": mount["manifest_ref"],
    "rebuilt": "2026-09-14",
}
(Path(os.environ["ORIGINAL_HOST_OUT"]) / "volume.json").write_text(
    json.dumps(record, indent=1) + "\n")
shutil.copy2(OUT / "dependencies-manifest.json",
             Path(os.environ["ORIGINAL_HOST_OUT"]) / "dependencies-manifest.json")
print(json.dumps({"tree_files": len(mount["manifest_ref"] and []) or "see-manifest",
                  "daemon_path": str(DATA), "volume": VOLUME}))
