"""Check the public source tree without starting runtime facilities."""
from pathlib import Path
import hashlib
import importlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
PACKAGES = ("lore_control", "lore_events", "lore_execution", "lore_files",
            "lore_provider", "lore_runtime", "lore_session")

def main():
    checked = 0
    for folder in (*PACKAGES, "lore_validation", "simulations", "validation"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if any(part == "evidence" or part.endswith("-evidence") for part in path.parts):
                continue
            compile(path.read_bytes(), str(path), "exec")
            checked += 1
    for package in PACKAGES:
        for path in sorted((ROOT / package).glob("*.py")):
            module = package if path.name == "__init__.py" else package + "." + path.stem
            importlib.import_module(module)
    manifest = json.loads((ROOT / "docs/source-manifest.json").read_text())
    for record in manifest["product_files"]:
        path = ROOT / record["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("published product differs from snapshot: " + record["path"])
    print(json.dumps({"status": "PASS", "python_sources_compiled": checked,
                      "product_files_verified": len(manifest["product_files"]),
                      "scope": "syntax, product imports and published source identity only"}))

if __name__ == "__main__":
    main()
