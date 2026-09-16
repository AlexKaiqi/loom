"""2026-09-14 restricted container load probe for the rebuilt dependency route.

Same preregistered protocol design/g3/s/container-preparation-protocol.json
(single/multi, bounded resources, network none, readonly rootfs, uid 1000) with
the 2026-09-14 environment paths: the dependency tree materialized under
.runtime-env/opt and the shared tsconfig at .runtime-env/opt/lore/config/tsconfig.json
(the same layout the X profile pins). The worker probe-public.mts is unchanged.
Preparation evidence only; it is not component acceptance or product execution.
"""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "validation/components/s"
sys.path.insert(0, str(HERE))
from oracle import pi_jsonl  # noqa: E402

out = ROOT / "validation/components/s/evidence" / sys.argv[1]
out.mkdir(parents=True, exist_ok=False)
image = "python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"
node = ROOT / ".runtime-env/opt/node"
pi = ROOT / ".runtime-env/opt/lore/research/repos/pi"
tsconfig = ROOT / ".runtime-env/opt/lore/config/tsconfig.json"
seccomp = ROOT / "lore_execution/seccomp.json"
result = {"scope": "G3_RESTRICTED_LOAD_PREPARATION_ONLY (2026-09-14 environment)",
          "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "inputs": {}, "runs": [], "checks": {}, "errors": []}
for p in [ROOT / "design/g3/s/container-preparation-protocol.json", node / "bin/node",
          tsconfig, seccomp, HERE / "probe-public.mts",
          ROOT / "design/g3/x-node-profile/dependencies.json"]:
    result["inputs"][str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()

wrapper = """from pathlib import Path
import subprocess,json,sys,os
mode=sys.argv[1]
env={"PATH":"/opt/node/bin:/usr/bin:/bin","HOME":"/work","LANG":"C.UTF-8","TSX_TSCONFIG_PATH":"/opt/lore/config/tsconfig.json"}
p=subprocess.run(["/opt/node/bin/node","--import","/opt/lore/research/repos/pi/node_modules/tsx/dist/loader.mjs","/opt/lore/validation/components/s/probe-public.mts",mode,"/work"],env=env,text=True,capture_output=True,timeout=30)
data={"exit":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"node":subprocess.run(["/opt/node/bin/node","--version"],capture_output=True,text=True).stdout,"ldd":subprocess.run(["ldd","/opt/node/bin/node"],capture_output=True,text=True).stdout,"files":{str(q.relative_to("/work")):q.read_text() for q in Path("/work").glob("*.jsonl")}}
print(json.dumps(data));sys.exit(p.returncode)
"""


def command(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, timeout=60, **kwargs)


try:
    for mode in ["single", "multi"]:
        argv = ["docker", "create", "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--security-opt", "seccomp=" + str(seccomp),
                "--user", "1000:1000", "--memory", "512m", "--memory-swap", "512m",
                "--pids-limit", "64", "--cpus", "1", "--shm-size", "1m",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,nr_inodes=4096,mode=1777",
                "--tmpfs", "/work:rw,nosuid,nodev,size=16m,nr_inodes=512,uid=1000,gid=1000,mode=0700"]
        for source, target in [(node, "/opt/node"), (pi, "/opt/lore/research/repos/pi"),
                               (tsconfig, "/opt/lore/config/tsconfig.json"),
                               (ROOT / "lore_session", "/opt/lore/lore_session"),
                               (HERE / "probe-public.mts", "/opt/lore/validation/components/s/probe-public.mts")]:
            argv += ["--mount", f"type=bind,src={source},dst={target},readonly"]
        argv += [image, "python3", "-c", wrapper, mode]
        created = command(argv)
        if created.returncode:
            raise RuntimeError(created.stderr)
        cid = created.stdout.strip()
        entry = {"mode": mode, "container_id": cid, "create_argv": argv}
        result["runs"].append(entry)
        try:
            before = command(["docker", "inspect", cid])
            (out / (mode + ".inspect-before.json")).write_text(before.stdout)
            ran = command(["docker", "start", "--attach", cid])
            (out / (mode + ".stdout")).write_text(ran.stdout)
            (out / (mode + ".stderr")).write_text(ran.stderr)
            after = command(["docker", "inspect", cid])
            (out / (mode + ".inspect-after.json")).write_text(after.stdout)
            entry["cli_exit"] = ran.returncode
            data = json.loads(ran.stdout)
            entry["worker_exit"] = data["exit"]
            entry["node"] = data["node"]
            (out / (mode + ".ldd.txt")).write_text(data["ldd"])
            final = pi_jsonl(data["files"][mode + "-final.jsonl"].encode())
            (out / (mode + ".original.jsonl")).write_text(data["files"][mode + "-final.jsonl"])
            for key in ["provider.jsonl", "effects.jsonl"]:
                (out / (mode + "." + key)).write_text(data["files"].get(key, ""))
            observation = json.loads(data["stdout"])
            entry["observation"] = observation
            provider = len(data["files"].get("provider.jsonl", "").splitlines())
            effects = len(data["files"].get("effects.jsonl", "").splitlines())
            result["checks"][mode + "_restricted_load"] = (
                ran.returncode == 0 and data["exit"] == 0 and data["node"].strip() == "v24.21.0"
                and provider == 1 and effects == (1 if mode == "single" else 0)
                and observation["result"] is not None
                and final["counts"]["assistant"] == 1)
        finally:
            removed = command(["docker", "rm", "--force", cid])
            entry["cleanup_exit"] = removed.returncode
            if removed.returncode:
                raise RuntimeError("container cleanup failed " + cid)
    if not all(result["checks"].values()):
        raise AssertionError("restricted load prediction failed")
except Exception as error:
    result["errors"].append(repr(error))
result["status"] = "OBSERVED_PREPARATION" if not result["errors"] else "INVESTIGATE"
(out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": result["status"], "checks": result["checks"], "errors": result["errors"]}))
raise SystemExit(0 if not result["errors"] else 1)
