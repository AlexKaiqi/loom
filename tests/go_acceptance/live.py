"""Bounded live Go CLI → native Pi → official OpenSandbox acceptance.

Python is a test driver and independent SQL/file/Docker observer only. The policy
is Node; no Python Runtime participates. Secrets stay outside Work and evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from support import CLIFixture, ROOT, query, assert_no_secrets


OBJECTIVE = (
    "Read numbers.txt in Userspace using the shell tool. Compute its sum and write sum.txt containing only "
    "the integer and a newline. Use Surface shell to create report.md and notes.md describing the computed result "
    "and commands actually performed. Read back produced files to verify them and give a concise final answer. "
    "Use at most six model turns, tool timeout at most 30 seconds. The two domains are separate remote environments."
)


def secret(path, name):
    for line in Path(path).expanduser().read_text().splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() == name:
            return value.strip().strip("\"'")
    raise ValueError("required external provider credential unavailable")


def main(args):
    os.environ["LOOM_GO_BINARY"] = str(Path(args.binary).resolve())
    os.environ.pop("LOOM_GO_EVIDENCE", None)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = CLIFixture()
    fixture.setUp()
    # Keep immutable full Work/effect data in the caller-selected fresh batch.
    fixture.base = output
    fixture.authority = output / "authority.sqlite"
    fixture.config = output / "config.toml"
    model_key = secret(args.provider_env_file, "ARK_PLAN_API_KEY")
    sandbox_key = Path(args.sandbox_key_file).read_text().strip()
    fixture.env["LOOM_TEST_MODEL_KEY"] = model_key
    fixture.env["LOOM_TEST_SANDBOX_KEY"] = sandbox_key
    policy = fixture.policy(max_turns=6, timeout=240)
    worker = policy / "worker.mjs"
    source = worker.read_text().replace("INDEPENDENT NODE POLICY", "Work on the objective using remote shell. Keep evidence in report.md and notes.md in Surface. Task files are in Userspace; never invent evidence.")
    source = source.replace("p=>false && p.turn.context.messages.filter(m=>m.role===\"assistant\").length<2", 'p=>p.turn.message.stopReason === "toolUse"')
    source = source.replace("max_turns:6,timeout:240", "max_turns:6,timeout:240,options:{maxTokens:4000,temperature:0}")
    worker.write_text(source)
    manifest_path = policy / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tools"] = [{"name": "shell", "capability": "sandbox.shell", "description": "Run shell in the selected remote domain; only that domain files are visible.",
        "parameters": {"type": "object", "properties": {"target": {"type": "string", "enum": ["surface", "userspace"]}, "script": {"type": "string"}, "timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": 30}}, "required": ["target", "script"], "additionalProperties": False}}]
    manifest_path.write_text(json.dumps(manifest))
    work, userspace = output / "work", output / "userspace"
    definition = {
        "provider": "ark", "api": "openai-completions", "id": "glm-5.3-flash", "name": "GLM 5.3 Flash",
        "reasoning": True, "input": ["text"],
        "contextWindow": 32768, "maxTokens": 4000,
    }
    definition["cost"] = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    definition["compat"] = {"supportsStore": False, "supportsDeveloperRole": False}
    fixture.call("create", work, "--harness", policy, "--definition", fixture.definition(userspace=True, native=definition))
    userspace.mkdir()
    (userspace / "numbers.txt").write_text("2\n3\n5\n")
    fixture.call("grant", work, userspace)
    fixture.configure(model_endpoint="https://ark.cn-beijing.volces.com/api/plan/v3", sandbox_endpoint=args.sandbox_endpoint)
    fixture.admit(work, "live-go-objective", {"text": OBJECTIVE})
    observations = {"scope": "one bounded paid Ark/Pi/Go/OpenSandbox sample", "definition": definition, "budget": {"max_turns": 6, "timeout": 240, "max_output_tokens_per_call": 4000}, "pricing": "Zero cost placeholders are not price claims", "checks": []}
    try:
        result = fixture.call("run", work, timeout=300)
        assert result["state"] == "completed", result
        assert (userspace / "sum.txt").read_text().strip() == "10"
        for name in ("report.md", "notes.md"):
            content = (work / "surface" / name).read_bytes()
            assert content.strip()
            captured = subprocess.check_output(["git", "--git-dir=" + str(work / ".loom/versions.git"), "show", result["revision"] + ":" + name])
            assert captured == content
        assert "10" in (work / "surface/report.md").read_text()
        effects = query(work, "SELECT * FROM effects ORDER BY rowid")
        observations["effects"] = effects
        usage, shell_domains = [], set()
        for effect in effects:
            assert effect["status"] == "completed", effect
            settled = json.loads(effect["result"])
            if effect["kind"] == "model":
                ref = settled["artifact"]
                raw = (work / ref["path"]).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == ref["sha256"]
                message = json.loads(raw)["message"]
                usage.append({"usage": message["usage"], "stopReason": message["stopReason"], "content_types": [p["type"] for p in message["content"]]})
            if effect["kind"] == "sandbox.shell":
                receipt = settled["receipt"]
                assert receipt["released"] and receipt["exit_code"] == 0, receipt
                shell_domains.add(receipt["target"])
                assert not subprocess.check_output(["docker", "ps", "-aq", "--filter", "label=loom.operation=" + effect["id"]], text=True).strip()
                for artifact in receipt["artifacts"]:
                    assert hashlib.sha256((work / artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
        assert shell_domains == {"surface", "userspace"}
        assert 1 <= len(usage) <= 6
        assert sum(u["usage"]["input"] for u in usage) > 0
        assert sum(u["usage"]["output"] for u in usage) > 0
        assert usage[-1]["stopReason"] == "stop"
        assert not query(work, "SELECT * FROM pending")
        observations.update(round=result, usage=usage, checks=["independent sum(2,3,5)=10", "two remote domains", "report/notes Git bytes", "native provider usage", "durable completed effects", "no pending", "remote operation containers absent"])
        (output / "PASS").write_text("One bounded real provider / Go / remote sandbox sample, not a reliability or throughput claim.\n")
    except BaseException as error:
        observations["error"] = str(error).replace(model_key, "<redacted>").replace(sandbox_key, "<redacted>")
        raise
    finally:
        observations["rounds"] = query(work, "SELECT * FROM rounds")
        observations["effects"] = query(work, "SELECT * FROM effects ORDER BY rowid")
        (output / "observations.json").write_text(json.dumps(observations, indent=2))
        observations["secret_scan_objects"] = assert_no_secrets(output, [model_key.encode(), sandbox_key.encode()])
        (output / "observations.json").write_text(json.dumps(observations, indent=2))
        fixture.doCleanups()
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--provider-env-file", required=True)
    parser.add_argument("--sandbox-key-file", required=True)
    parser.add_argument("--sandbox-endpoint", required=True)
    parser.add_argument("--output", required=True)
    main(parser.parse_args())
