"""2026-09-14 rebuild of the markdown-001 fixed parser snapshot.

Captures the exact installed sources and license files of the pinned parser
versions into validation/system/dependencies/markdown-001/ and writes the
manifest consumed by validation/system/prepare_artifact_oracles.py (relative to
site-packages) and validation/system/m01_run.py parser_dependencies (snapshot
paths relative to the repository root). Pure-Python distributions: the captured
bytes are platform-independent; version pins are what matters.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

PACKAGES = [
    {"distribution": "markdown-it-py", "version": "4.2.0", "module": "markdown_it"},
    {"distribution": "mdurl", "version": "0.1.2", "module": "mdurl"},
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    site = Path(args.site)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    source = out / "source"
    packages = []
    for item in PACKAGES:
        package_dir = site / item["module"]
        if not package_dir.is_dir():
            raise SystemExit("missing installed package: " + item["module"])
        target = source / item["module"]
        shutil.copytree(package_dir, target)
        sources, licenses = [], []
        for path in sorted(package_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            rel = path.relative_to(site).as_posix()
            snapshot = (Path("validation/system/dependencies/markdown-001/source") /
                        item["module"] / path.relative_to(package_dir)).as_posix()
            sources.append({"relative": rel, "snapshot": snapshot, "sha256": sha(path)})
        # PEP 503: dist-info directory names normalize hyphens to underscores.
        normalized = item["distribution"].replace("-", "_").lower()
        dist_info = site / (normalized + "-" + item["version"] + ".dist-info")
        candidates = [p for pattern in ("*LICENSE*", "*COPYING*", "*NOTICE*")
                      for p in sorted(dist_info.rglob(pattern))
                      if p.is_file() and p.is_symlink() is False]
        candidates += [p for pattern in ("LICENSE*", "COPYING*", "NOTICE*")
                       for p in sorted(package_dir.glob(pattern))
                       if p.is_file() and p.is_symlink() is False]
        for path in candidates:
            snapshot = ("validation/system/dependencies/markdown-001/source/licenses/" +
                        item["distribution"] + "-" +
                        path.relative_to(dist_info).as_posix().replace("/", "-"))
            licenses.append({"snapshot": snapshot, "sha256": sha(path)})
            destination = out.parents[3] / snapshot
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        if not licenses:
            raise SystemExit("no license file for " + item["distribution"])
        packages.append(dict(item, sources=sources, licenses=licenses))

    manifest = {
        "schema": "lore-markdown-parser-snapshot/v1", "date": "2026-09-14",
        "platform_note": "rebuilt 2026-09-14 for the Linux container validation environment; "
                         "version pins unchanged, source bytes captured from the pinned releases",
        "packages": packages}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    total = sum(len(p["sources"]) for p in packages)
    print(json.dumps({"packages": [p["distribution"] for p in packages],
                      "source_files": total,
                      "licenses": sum(len(p["licenses"]) for p in packages)}))


if __name__ == "__main__":
    main()
