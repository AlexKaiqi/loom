"""Before-execution byte snapshots of driver, candidate, contract and original fixtures."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]


def begin(batch, module=None):
    assert batch and "/" not in batch and ".." not in batch
    out = ROOT / "validation/components/provider/evidence" / batch
    out.mkdir(parents=True, exist_ok=False)
    paths = set(p for p in (ROOT / "design/g3/provider").rglob("*") if p.is_file())
    paths.update((ROOT / "validation/components/provider").glob("*.py"))
    if module:
        candidate = ROOT / module.replace(".", "/")
        if candidate.is_dir(): paths.update(candidate.rglob("*.py"))
        elif candidate.with_suffix(".py").is_file(): paths.add(candidate.with_suffix(".py"))
    hashes = {}
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        target = out / "snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / "before.json").write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        inputs=hashes,module=module),indent=2)+"\n")
    return out, hashes


def unchanged(hashes):
    return [name for name, value in hashes.items() if hashlib.sha256((ROOT / name).read_bytes()).hexdigest()!=value]
