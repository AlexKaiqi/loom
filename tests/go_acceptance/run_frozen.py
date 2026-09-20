"""Freeze/rebuild Go source, execute independent checks and retain raw evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]


def sources():
    paths = []
    for name in ("runtime", "services/model", "harnesses", "tests/go_acceptance", "tests/model", "deploy", "scripts", "templates", "tests/harness", "tests/install", "tests/onboarding"):
        for path in (ROOT / name).rglob("*"):
            relative = path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink() or any(part in {"node_modules", "evidence", "__pycache__", "bin"} for part in relative.parts):
                continue
            paths.append(path)
    for name in ("README.md", "docs/loom-design-book.html", "AGENTS.md", "THIRD_PARTY.md", "install.sh", "Makefile", "go.work", "go.work.sum", "docs/development.md", "deploy/config.example.toml", "deploy/work.example.toml"):
        if (ROOT / name).is_file():
            paths.append(ROOT / name)
    return sorted(set(paths))


def fingerprint():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources()}


def main(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = fingerprint()
    index = {"started": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(), "python_driver": sys.version, "before": before, "commands": []}
    with tarfile.open(output / "source.tar.gz", "w:gz") as archive:
        for path in sources():
            archive.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    binary = output / "loom"
    env = dict(os.environ, LOOM_GO_BINARY=str(binary), LOOM_GO_EVIDENCE=str(output / "blackbox"))
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    if args.sandbox_key_file:
        env.update(LOOM_SANDBOX_ENDPOINT=args.sandbox_endpoint, LOOM_SANDBOX_KEY_FILE=str(Path(args.sandbox_key_file).resolve()), LOOM_SANDBOX_EVIDENCE=str(output / "sandbox-component"))
    def run(name, command, cwd=ROOT, timeout=300):
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=env, timeout=timeout)
        (output / (name + ".stdout")).write_text(result.stdout)
        (output / (name + ".stderr")).write_text(result.stderr)
        index["commands"].append({"name": name, "argv": list(map(str, command)), "cwd": str(cwd), "returncode": result.returncode, "source_unchanged": fingerprint() == before})
        (output / "index.json").write_text(json.dumps(index, indent=2))
        if result.returncode:
            raise RuntimeError(name + " failed; raw output retained")
    try:
        run("go-version", ["go", "version"])
        run("node-version", ["node", "--version"])
        run("git-version", ["git", "--version"])
        run("go-test", ["go", "test", "-race", "./...", "-count=1", "-v"], ROOT / "runtime")
        run("pi-component", [sys.executable, "-m", "unittest", "discover", "-s", "tests/model", "-v"])
        run("go-build", ["go", "build", "-o", binary, "./cmd/loom"], ROOT / "runtime")
        run("build-info", ["go", "version", "-m", binary])
        run("blackbox", [sys.executable, "-m", "unittest", "discover", "-s", "tests/go_acceptance", "-v"])
        if args.sandbox_key_file:
            run("remote", [sys.executable, "tests/go_acceptance/remote.py", "--binary", binary, "--sandbox-endpoint", args.sandbox_endpoint, "--sandbox-key-file", args.sandbox_key_file, "--output", output / "remote"])
            run("remote-work-only", [sys.executable, "tests/go_acceptance/remote.py", "--binary", binary, "--sandbox-endpoint", args.sandbox_endpoint, "--sandbox-key-file", args.sandbox_key_file, "--output", output / "remote-work-only", "--work-only"])
            run("remote-portable", [sys.executable, "tests/go_acceptance/remote.py", "--binary", binary, "--sandbox-endpoint", args.sandbox_endpoint, "--sandbox-key-file", args.sandbox_key_file, "--output", output / "remote-portable", "--portable"])
        if args.provider_env_file:
            if not args.sandbox_key_file:
                raise ValueError("live requires sandbox credentials")
            run("live", [sys.executable, "tests/go_acceptance/live.py", "--binary", binary, "--sandbox-endpoint", args.sandbox_endpoint, "--sandbox-key-file", args.sandbox_key_file, "--provider-env-file", args.provider_env_file, "--output", output / "live"], timeout=360)
    finally:
        index.update(after=fingerprint(), ended=datetime.now(timezone.utc).isoformat())
        index["source_unchanged"] = index["before"] == index["after"]
        (output / "index.json").write_text(json.dumps(index, indent=2))
    assert index["source_unchanged"], "source changed during frozen acceptance"
    (output / "PASS").write_text("Frozen scope checks passed; inspect contract and individual observations for limits.\n")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--sandbox-endpoint", default="http://127.0.0.1:18089")
    parser.add_argument("--sandbox-key-file")
    parser.add_argument("--provider-env-file")
    main(parser.parse_args())
