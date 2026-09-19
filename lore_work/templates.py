"""Resolve the Harness tree of this checkout, or another git worktree.

One checkout carries one Harness (lore_harness/manifest.json). Other
combinations are other branches, typically mounted as worktrees. Runtime does
not compose accessories.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def catalog_root() -> Path:
    import lore_harness
    return Path(lore_harness.__file__).resolve().parent


def this_harness() -> Path:
    root = catalog_root()
    if not (root / "manifest.json").is_file():
        raise FileNotFoundError("this checkout has no lore_harness/manifest.json")
    return root


def _git_root() -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(catalog_root()),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return Path(out.stdout.strip())


def _branch_of(path: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    name = out.stdout.strip()
    return name or None


def list_worktrees() -> list:
    root = _git_root()
    if root is None:
        return []
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    rows, current = [], {}
    for line in out.stdout.splitlines():
        if not line:
            if current.get("path"):
                rows.append(current)
            current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line.split(" ", 1)[1]
        elif line.startswith("branch refs/heads/"):
            current["branch"] = line.split("refs/heads/", 1)[1]
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["branch"] = None
    if current.get("path"):
        rows.append(current)
    harnesses = []
    for row in rows:
        harness = Path(row["path"]) / "lore_harness"
        if (harness / "manifest.json").is_file():
            harnesses.append({
                "branch": row.get("branch"),
                "worktree": row["path"],
                "harness": str(harness),
            })
    return harnesses


def catalog() -> dict:
    here = this_harness()
    return {
        "current": {
            "branch": _branch_of(here),
            "harness": str(here),
        },
        "worktrees": list_worktrees(),
    }


def _branch_matches(branch: str | None, name: str) -> bool:
    """Match a worktree branch to a user-supplied stack name.

    Git forbids a ref that is a prefix of another, so stack nodes are named
    `h/kernel/pin/root`. Callers may pass that full name, the stem without
    `/root`, or a unique suffix such as `pin` or `kernel/pin`.
    """
    if not branch:
        return False
    if branch == name:
        return True
    stem = branch[:-5] if branch.endswith("/root") else branch
    if stem == name:
        return True
    if stem.endswith("/" + name) or branch.endswith("/" + name):
        return True
    return False


def resolve_harness(name_or_path: str) -> Path:
    raw = Path(name_or_path).expanduser()
    if raw.is_dir() and (raw / "manifest.json").is_file():
        return raw.resolve()
    if name_or_path in ("kernel", "lore_harness", "."):
        return this_harness()
    for row in list_worktrees():
        if _branch_matches(row.get("branch"), name_or_path):
            return Path(row["harness"])
    if "/" in name_or_path or name_or_path in (".", "..") or name_or_path.startswith("~"):
        raise FileNotFoundError("harness template without manifest.json: %s" % name_or_path)
    raise FileNotFoundError(
        "unknown harness %r; this checkout is kernel at %s; other combinations are worktrees"
        % (name_or_path, this_harness())
    )
