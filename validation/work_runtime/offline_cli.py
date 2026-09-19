#!/usr/bin/env python3
"""Offline CLI and install-surface checks. No network, no credentials."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lore_work import layout
from lore_work.cli import main


def _run(argv, env) -> tuple[int, str, str]:
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    stdout, stderr = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = stdout, stderr
        code = main(argv)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        os.environ.clear()
        os.environ.update(previous)
    return code, stdout.getvalue(), stderr.getvalue()


def _load(text):
    return json.loads(text)


def main_check() -> int:
    home = Path(tempfile.mkdtemp(prefix="loom-home-"))
    works = Path(tempfile.mkdtemp(prefix="loom-works-"))
    userspace = Path(tempfile.mkdtemp(prefix="loom-us-"))
    env = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT),
    }
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    code, out, err = _run(["init", str(works)], env)
    payload = _load(out)
    check("init", code == 0 and Path(payload["authority"]).is_file(), err or out)
    check("authority_name", Path(payload["authority"]).name == ".loom-authority.json", payload["authority"])
    check("init_sets_default_root", payload.get("works_root_default") is True, out)
    code, out, err = _run(["config", "works_root"], env)
    check("default_root_saved", code == 0 and Path(_load(out)["value"]).resolve() == works.resolve(), err or out)

    code, out, err = _run(["config", "provider.model", "local-test"], env)
    check("config_model", code == 0 and _load(out)["value"] == "local-test", err or out)

    code, out, err = _run(["config", "provider.api_key", "sk-secret"], env)
    check("config_rejects_key", code == 2 and ("unknown config key" in err or "must not store" in err), err)
    sneaky = Path(env["XDG_CONFIG_HOME"]) / "loom" / "config.json"
    sneaky.write_text(json.dumps({"schema": "loom.host/v1", "provider": {"api_key": "sk-secret"}}), encoding="utf-8")
    code, out, err = _run(["config"], env)
    check("config_file_rejects_key", code == 2 and "must not store" in err, err)
    sneaky.write_text(json.dumps({"schema": "loom.host/v1", "provider": {"model": "local-test"}}, indent=2) + "\n",
                      encoding="utf-8")

    code, out, err = _run(["harnesses"], env)
    listing = _load(out) if code == 0 else {}
    current = listing.get("current") or {}
    check("harnesses_current", code == 0 and current.get("harness"), err or out)
    check("harnesses_worktrees_list", isinstance(listing.get("worktrees"), list), json.dumps(listing))

    code, out, err = _run(
        ["--root", str(works), "create", "demo", "--harness", "kernel", "--userspace", str(userspace)],
        env)
    created = _load(out) if code == 0 else {"error": err or out}
    work = created.get("work") or {}
    check("create", code == 0 and work.get("schema") == "loom.work/v1", err or out)
    check("userspace_spec_fields", work.get("userspaces") == [{"id": userspace.name, "path": str(userspace)}],
          json.dumps(work.get("userspaces")))

    code, out, err = _run(
        ["--root", str(works), "admit", "demo", "--kind", "work.objective.set",
         "--payload", json.dumps({"objective": "say done"})],
        env)
    admitted = _load(out) if code == 0 else {}
    check("admit", code == 0 and admitted.get("created") is True, err or out)

    code, out, err = _run(
        ["--root", str(works), "run", "demo", "--provider", "faux",
         "--faux-response", json.dumps({"action": {"type": "emit", "kind": "work.completed",
                                                   "payload": {"evidence_refs": []}}})],
        env)
    ran = _load(out) if code == 0 else {}
    check("run_round", code == 0 and ran.get("status") == "committed", err or out)

    code, out, err = _run(["--root", str(works), "status"], env)
    listing = _load(out) if code == 0 else {}
    check("list_root", code == 0 and "demo" in (listing.get("works") or {}), err or out)

    copy = Path(tempfile.mkdtemp(prefix="loom-copy-")) / "demo"
    import shutil
    shutil.copytree(works / "demo", copy)
    check("copy_unlisted", layout.authority_entry(copy.parent, "demo") is None, str(copy))

    failed = [item for item in checks if not item[1]]
    print(json.dumps({"status": "PASS" if not failed else "FAIL",
                      "checks": [{"id": n, "ok": ok, "detail": d} for n, ok, d in checks]},
                     ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main_check())
