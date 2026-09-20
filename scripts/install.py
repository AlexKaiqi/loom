#!/usr/bin/env python3
"""Assemble separately deployed Loom components; activate only a complete release."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

SOURCE = Path(__file__).resolve().parent.parent


def run(argv, **kwargs):
    subprocess.run([str(arg) for arg in argv], check=True, **kwargs)


def executable(name):
    value = shutil.which(name)
    if not value:
        raise ValueError(f"Missing {name}; install the prerequisites listed in docs/development.md")
    return str(Path(value).absolute())


def prerequisites():
    if sys.platform not in ("darwin", "linux"):
        raise ValueError("Loom installation supports macOS and Linux")
    if sys.version_info < (3, 10):
        raise ValueError("Loom installation and its bundled Harness require Python 3.10 or newer")
    paths = {name: executable(name) for name in ("go", "node", "npm", "git")}
    versions = {name: subprocess.check_output([path, "version" if name == "go" else "--version"], text=True).strip()
                for name, path in paths.items()}
    match = re.search(r"go(\d+)\.(\d+)", versions["go"])
    if not match or tuple(map(int, match.groups())) < (1, 24):
        raise ValueError("Loom requires Go 1.24 or newer")
    if not re.match(r"v24\.", versions["node"]):
        raise ValueError("Loom model component requires Node 24")
    return paths, versions


def expect_link(path, target):
    """Do not overwrite something the installer did not place here."""
    if path.is_symlink():
        if os.readlink(path) != str(target):
            raise ValueError(f"Refusing to replace an unrelated link: {path}")
    elif path.exists():
        raise ValueError(f"Refusing to replace an existing file or directory: {path}")


def copy_component(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", "evidence"))


def assemble(release, paths, versions):
    (release / "bin").mkdir()
    copy_component(SOURCE / "services/model", release / "services/model")
    copy_component(SOURCE / "harnesses", release / "harnesses")
    copy_component(SOURCE / "deploy", release / "deploy")
    # Build output and dependency installation never mutate the source checkout.
    run([paths["go"], "build", "-trimpath", "-o", release / "bin/loom-runtime", "./cmd/loom"], cwd=SOURCE / "runtime")
    run([paths["npm"], "ci", "--omit=dev", "--no-audit", "--no-fund"], cwd=release / "services/model")
    run([sys.executable, "-m", "venv", release / "venv"])
    python = release / "venv/bin/python3"
    run([python, "-m", "pip", "install", "--disable-pip-version-check", "-r", release / "harnesses/kernel/requirements.txt"])
    node_dir = str(Path(paths["node"]).parent)
    model_launcher = release / "bin/loom-model"
    model_launcher.write_text(
        "#!/bin/sh\nset -eu\nexec " + shlex.quote(paths["node"]) + " "
        + shlex.quote(str(release / "services/model/worker.mjs")) + ' "$@"\n', encoding="utf-8")
    model_launcher.chmod(0o755)
    launcher = release / "bin/loom"
    launcher.write_text(
        "#!/bin/sh\nset -eu\n"
        + "LOOM_INSTALL_ROOT=" + shlex.quote(str(release)) + "\nexport LOOM_INSTALL_ROOT\n"
        + "PATH=" + shlex.quote(os.pathsep.join((str(release / "bin"), str(release / "venv/bin"), node_dir))) + ':"${PATH:-/usr/bin:/bin}"\nexport PATH\n'
        + "exec " + shlex.quote(str(release / "bin/loom-runtime")) + ' "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    (release / "installation.json").write_text(json.dumps({"format": 1, "platform": sys.platform, "versions": versions}, indent=2) + "\n")
    # Import/start the installed copies, not source-tree dependencies.
    run([launcher, "--help"], cwd=release, stdout=subprocess.DEVNULL)
    run([model_launcher], input=b"", cwd=release)
    run([python, "-I", release / "harnesses/kernel/worker.py"], input=b"", cwd=release)


def install(prefix, bin_dir):
    paths, versions = prerequisites()
    prefix.mkdir(parents=True, exist_ok=True)
    # flock is released on exit/crash and makes same-prefix activation exclusive.
    with (prefix / ".install.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current = prefix / "current"
        if current.exists() or current.is_symlink():
            if not current.is_symlink() or not os.readlink(current).startswith("releases/"):
                raise ValueError(f"Refusing to replace an unrelated installation path: {current}")
        launcher = bin_dir / "loom"
        expected = current / "bin/loom"
        expect_link(launcher, expected)
        releases = prefix / "releases"
        releases.mkdir(exist_ok=True)
        release = Path(tempfile.mkdtemp(prefix="release-", dir=releases))
        pending_current = prefix / (".current-" + uuid.uuid4().hex)
        pending_launcher = bin_dir / (".loom-" + uuid.uuid4().hex)
        activated = False
        try:
            assemble(release, paths, versions)
            bin_dir.mkdir(parents=True, exist_ok=True)
            expect_link(launcher, expected)
            if not launcher.is_symlink():
                pending_launcher.symlink_to(expected)
                # link() rejects a newly appeared destination rather than replacing it.
                os.link(pending_launcher, launcher, follow_symlinks=False)
                pending_launcher.unlink()
            pending_current.symlink_to(Path("releases") / release.name)
            os.replace(pending_current, current)
            activated = True
        finally:
            pending_current.unlink(missing_ok=True)
            pending_launcher.unlink(missing_ok=True)
            if not activated:
                shutil.rmtree(release)
        print(f"\nInstalled Loom: {launcher}")
        print("Next: " + shlex.quote(str(launcher)) + " setup")
        print("Existing configuration and Work directories were left unchanged.")


def main():
    parser = argparse.ArgumentParser(description="Install Loom and its workers from this checkout without changing shell profiles or user configuration.")
    parser.add_argument("--prefix", type=Path, help="installation directory (default: ~/.local/share/loom)")
    parser.add_argument("--bin-dir", type=Path, help="launcher directory (default: ~/.local/bin, or PREFIX/bin with --prefix)")
    args = parser.parse_args()
    prefix = (args.prefix or Path.home() / ".local/share/loom").expanduser().resolve()
    bin_dir = (args.bin_dir or (prefix / "bin" if args.prefix else Path.home() / ".local/bin")).expanduser().resolve()
    try:
        install(prefix, bin_dir)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Loom installation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
