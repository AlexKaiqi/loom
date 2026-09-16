"""Offline environment-profile registry check; no Docker, no Engine construction.

Covers the locally checkable part of design/g3/x/amendment-environment-profile-2026-09-15:
registry integrity and digest recomputation, the frozen-identity cross-check that
engine.py enforces, the request-contract field addition, and the backend seam
ownership declaration. Full request-path behavior stays with the real X suite
(cases X001-X028 as the behavior-preservation anchor, X029/X030 for rejection).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

rows = []


def check(name, ok, detail=""):
    rows.append(dict(name=name, passed=bool(ok), detail=detail))


def main():
    from lore_execution.backend import BACKEND_OWNED_PROFILE_FIELDS
    from lore_execution.journal import canonical, digest
    from lore_execution.requests import (
        ENVIRONMENT_PROFILE_SHA256,
        FIELDS,
        PROFILES,
    )

    raw = json.loads((ROOT / "lore_execution/environment_profiles.json").read_text())
    check("registry schema", type(raw) is dict and raw.get("schema") == 2
          and type(raw.get("profiles")) is list and len(raw["profiles"]) == 2)
    entries = {e["id"]: e for e in raw["profiles"]}
    for e in raw["profiles"]:
        body = {k: v for k, v in e.items() if k != "profile_sha256"}
        check("digest recomputes: " + e["id"],
              e["profile_sha256"] == digest(canonical(body)))
    entry = entries["fixed-python-linux-v1"]
    profile = json.loads((ROOT / "lore_execution/profile.json").read_text())
    check("v1 identity matches frozen profile",
          entry["image"] == profile["image"] and entry["image_id"] == profile["image_id"]
          and entry["seccomp_sha256"] == profile["seccomp_sha256"]
          and entry["engine_version"] == profile["engine_version"])
    check("v1 semantics preserved", entry["network"] == "none" and entry["endpoints"] == []
          and entry["interpreter_argv"] == [["python", "-c"], ["python3", "-c"], ["/bin/sh", "-c"]])
    check("request contract carries profile_sha256", "profile_sha256" in FIELDS)
    check("exported digest equals registry", ENVIRONMENT_PROFILE_SHA256 == entry["profile_sha256"])
    check("loaded registry matches file", set(PROFILES) == set(entries)
          and PROFILES[entry["id"]]["profile_sha256"] == entry["profile_sha256"])
    browser = entries["linux-browser-v1"]
    seccomp_file = ROOT / "lore_execution" / browser["seccomp_path"]
    check("browser entry identity",
          browser["seccomp_path"] == "seccomp-browser.json"
          and seccomp_file.is_file()
          and browser["seccomp_sha256"] == digest(seccomp_file.read_bytes())
          and browser["image"].startswith("sha256:")
          and browser["image"] == browser["image_id"]
          and browser["network"] == "none" and browser["endpoints"] == [])
    check("browser per-profile budget maxima",
          set(browser["budget_maxima"]) <= {
              "memory_bytes", "pids", "cpu", "deadline_seconds",
              "tmp_bytes", "shm_bytes", "tmp_inodes", "shm_inodes"}
          and browser["budget_maxima"]["memory_bytes"] > 134217728
          and browser["budget_maxima"]["deadline_seconds"] > 20)
    check("v1 entry has no schema-2 extensions",
          "seccomp_path" not in entry and "budget_maxima" not in entry)
    check("backend seam declares profile ownership",
          BACKEND_OWNED_PROFILE_FIELDS == frozenset({"profile_sha256"})
          and BACKEND_OWNED_PROFILE_FIELDS <= FIELDS)

    record = dict(check="environment-profile-offline-007", rows=rows,
                  passed=all(r["passed"] for r in rows))
    out = ROOT / "validation/components/x/evidence/environment-profile-offline-007"
    out.mkdir(parents=True, exist_ok=False)
    (out / "assessment.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(passed=record["passed"],
                          failed=[r["name"] for r in rows if not r["passed"]]),
                    ensure_ascii=False))


if __name__ == "__main__":
    main()
