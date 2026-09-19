"""Skip combination-specific offline cases when this checkout is another stack."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "lore_harness"


def fact_kinds() -> set:
    data = json.loads((HARNESS / "manifest.json").read_text(encoding="utf-8"))
    return {entry["kind"] for entry in data.get("facts", {}).get("kinds", [])}


def skip_unless(*needed: str) -> bool:
    """Return True if the caller should exit 0 without running."""
    missing = [kind for kind in needed if kind not in fact_kinds()]
    if not missing:
        return False
    print("SKIP this checkout's lore_harness lacks %s" % missing)
    return True


def skip_unless_pin() -> bool:
    """Pin is a projection accessory; it does not add a fact kind."""
    path = HARNESS / "projection" / "main.py"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "Pinned (from facts every Round" in text:
        return False
    print("SKIP this checkout does not pin objective/acceptance")
    return True
