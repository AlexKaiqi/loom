"""V4 probe: X profile pinning reproducible inside the pinned VM (DRAFT).

Protocol: validation/substrate/protocol-substrate-001.json, batch V4_engine_pin.
Status: DRAFT / UNVERIFIED — never executed; must not be executed until the suite
is frozen and the S0 identity gate passes.

Runs INSIDE the pinned Lima VM against the rootful Docker daemon installed by
the pinned template. Four preregistered equality criteria (all must hold):
  1. `docker version` Server.Version equals lore_execution/profile.json
     engine_version (same comparison semantics as lore_execution/engine.py).
  2. python image pulled BY DIGEST; RepoDigests contains the profile digest.
  3. seccomp file sha256 equals profile.json seccomp_sha256.
  4. docker volume lore-runtime-deps maps to
     /var/lib/docker/volumes/lore-runtime-deps/_data (fixed volume path
     reproducible — the Docker Desktop coupling side effect must be absent).
Recorded observation (NOT a criterion): `docker manifest inspect` shape of the
pinned digest (manifest list? which architectures?) — input to the arm64
amendment per the survey.

Negative control (--expect-reject-engine X): feed a wrong engine_version and
verify the comparator refuses it; acceptance violates the expectation.

Exit codes: 0 criterion met / expected rejection observed; 2 violated; 3 blocked.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

LORE_ROOT = Path(__file__).resolve().parents[4]


def docker(*args: str) -> str:
    result = subprocess.run(["sudo", "-n", "docker", *args],
                            capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError("docker %s failed: %s" % (args[0], result.stderr.strip()[:500]))
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=str(LORE_ROOT / "lore_execution" / "profile.json"))
    parser.add_argument("--seccomp", default=str(LORE_ROOT / "lore_execution" / "seccomp.json"))
    parser.add_argument("--volume", default="lore-runtime-deps")
    parser.add_argument("--expect-reject-engine", help="negative control: comparator must refuse this version")
    args = parser.parse_args()

    if sys.platform != "linux":
        print(json.dumps({"verdict": "BLOCKED", "reason": "probe requires Linux guest, got " + sys.platform}))
        return 3

    profile = json.loads(Path(args.profile).read_text())
    pinned_engine = args.expect_reject_engine or profile["engine_version"]
    digest = profile["image"].split("@", 1)[1] if "@" in profile["image"] else profile["image"]

    checks = {}
    manifest_record = None
    server = json.loads(docker("version", "--format", "{{json .Server}}"))
    checks["engine_version"] = {"pinned": pinned_engine, "actual": server.get("Version"),
                                "equal": server.get("Version") == pinned_engine}

    if not args.expect_reject_engine:
        docker("pull", "python@" + digest)
        repodigests = json.loads(docker("image", "inspect", "--format", "{{json .RepoDigests}}",
                                        "python@" + digest))
        digest_ok = any(item.endswith("@" + digest) for item in repodigests)
        checks["image_digest"] = {"pinned": digest, "repo_digests": repodigests, "equal": digest_ok}

        seccomp_digest = hashlib.sha256(Path(args.seccomp).read_bytes()).hexdigest()
        checks["seccomp_sha256"] = {"pinned": profile["seccomp_sha256"], "actual": seccomp_digest,
                                    "equal": seccomp_digest == profile["seccomp_sha256"]}

        docker("volume", "create", args.volume)
        volume_path = json.loads(docker("volume", "inspect", "--format", "{{json .Mountpoint}}", args.volume))
        expected_path = "/var/lib/docker/volumes/%s/_data" % args.volume
        checks["volume_fixed_path"] = {"pinned": expected_path, "actual": volume_path,
                                       "equal": volume_path == expected_path}

        # Recorded observation only (never a criterion): manifest shape of the
        # pinned digest, input to the arm64 per-arch digest amendment.
        try:
            manifest_record = json.loads(docker("manifest", "inspect", "python@" + digest))
        except RuntimeError as exc:
            manifest_record = "RECORD_ONLY_UNAVAILABLE: " + str(exc)

    violated = [name for name, item in checks.items() if not item["equal"]]
    if args.expect_reject_engine:
        if checks["engine_version"]["equal"]:
            print(json.dumps({"verdict": "FAIL",
                              "reason": "comparator accepted a wrong engine version (negative control violated)",
                              "checks": checks}))
            return 2
        print(json.dumps({"verdict": "PASS", "reason": "wrong engine version rejected", "checks": checks}))
        return 0
    if violated:
        print(json.dumps({"verdict": "FAIL", "reason": "criteria violated: " + ",".join(violated),
                          "checks": checks, "manifest_record": manifest_record}, default=str))
        return 2
    print(json.dumps({"verdict": "PASS", "reason": "engine/digest/seccomp/volume pins reproducible",
                      "checks": checks, "manifest_record": manifest_record}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
