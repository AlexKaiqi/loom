#!/usr/bin/env python3
"""Build and activate one shared Linux facility; leave Work data and grants alone."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

SOURCE = Path(__file__).resolve().parent.parent


def run(argv, **kwargs):
    return subprocess.run([str(x) for x in argv], check=True, **kwargs)


def expect_link(path, target):
    if path.is_symlink():
        if os.readlink(path) != str(target):
            raise ValueError(f'Refusing to replace an unrelated link: {path}')
    elif path.exists():
        raise ValueError(f'Refusing to replace an existing file or directory: {path}')


def copy_component(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('node_modules', '__pycache__', '*.pyc', 'evidence'))


def assemble(release, docker, installation, roots, state):
    build = release / 'build'
    build.mkdir()
    for component in ('runtime', 'services/model', 'harnesses', 'templates', 'deploy'):
        copy_component(SOURCE / component, build / component)
    (build / 'docs').mkdir()
    shutil.copyfile(SOURCE / 'docs/loom-design-book.html', build / 'docs/loom-design-book.html')
    image_tag = 'loom-work:' + release.name
    run([docker, 'build', '--tag', image_tag, '-f', build / 'deploy/work/Dockerfile', build])
    image_id = subprocess.check_output([docker, 'image', 'inspect', '--format', '{{.Id}}', image_tag], text=True).strip()
    container = installation + '-' + release.name
    command = [docker, 'run', '--detach', '--name', container, '--label', 'loom.installation=' + installation,
               '--privileged', '--cgroupns=host', '--env', 'LOOM_FACILITY_ID=' + installation,
               '--mount', 'type=bind,src=' + str(state) + ',dst=/var/lib/loom-host',
               '--mount', 'type=volume,src=' + installation + '-execution,dst=/var/lib/loom-execution',
               '--add-host', 'host.docker.internal:host-gateway']
    for root in roots:
        if ',' in str(root):
            raise ValueError('Docker workspace mount paths cannot contain commas')
        command += ['--mount', 'type=bind,src=' + str(root) + ',dst=' + str(root)]
    command += [image_id]
    run(command, stdout=subprocess.DEVNULL)
    activated = False
    try:
        for _ in range(150):
            ready = subprocess.run([docker, 'exec', container, 'test', '-f', '/run/loom/execution.toml'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready.returncode == 0:
                break
            time.sleep(.1)
        else:
            raise ValueError('shared Linux facility did not become ready; inspect its Docker logs')
        run([docker, 'exec', container, 'loom-runtime', '--help'], stdout=subprocess.DEVNULL)
        run([docker, 'exec', container, 'node', '--input-type=module', '-e',
             'await import("/opt/loom/services/model/agent.mjs"); '
             'const {apiFor}=await import("/opt/loom/services/model/pi.mjs"); '
             'if(typeof (await apiFor({api:"openai-completions"})).streamSimple!=="function")process.exit(2)'])
        (release / 'bin').mkdir()
        shutil.copyfile(SOURCE / 'scripts/launcher.py', release / 'bin/loom')
        (release / 'bin/loom').chmod(0o755)
        info = {'format': 2, 'docker': docker, 'installation_id': installation, 'container': container, 'image_id': image_id,
                'workspace_roots': list(map(str, roots)), 'host_state': str(state),
                'design_sha256': hashlib.sha256((build / 'docs/loom-design-book.html').read_bytes()).hexdigest()}
        (release / 'installation.json').write_text(json.dumps(info, indent=2) + '\n')
        shutil.rmtree(build)
        activated = True
    finally:
        if not activated:
            subprocess.run([docker, 'rm', '-f', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install(prefix, bin_dir, roots):
    if sys.platform not in ('darwin', 'linux') or sys.version_info < (3, 11):
        raise ValueError('Loom installer requires macOS/Linux and Python 3.11+')
    docker = shutil.which('docker')
    if not docker:
        raise ValueError('Docker with a running Linux engine is required')
    docker = str(Path(docker).absolute())
    try:
        system = subprocess.check_output([docker, 'info', '--format', '{{.OSType}}'], text=True, timeout=15).strip()
    except subprocess.TimeoutExpired as error:
        raise ValueError('Docker engine did not respond within 15 seconds; restore Docker Desktop or the Linux engine before installing') from error
    if system != 'linux':
        raise ValueError('Docker must use a Linux engine')
    if any(',' in str(path) for path in [prefix, *roots]):
        raise ValueError('Docker bind mount paths cannot contain commas')
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    prefix.chmod(0o700)
    state = prefix / 'host-state'
    state.mkdir(mode=0o700, exist_ok=True)
    installation = 'loom-' + hashlib.sha256(str(prefix).encode()).hexdigest()[:16]
    with (prefix / '.install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = prefix / 'current'
        if current.exists() or current.is_symlink():
            if not current.is_symlink() or not os.readlink(current).startswith('releases/'):
                raise ValueError(f'Refusing to replace an unrelated installation path: {current}')
            old = json.loads((current / 'installation.json').read_text())
            if old['workspace_roots'] != list(map(str, roots)):
                raise ValueError('Workspace roots differ from the existing deployment; retain its mount layout on upgrade')
        launcher = bin_dir / 'loom'
        expect_link(launcher, current / 'bin/loom')
        releases = prefix / 'releases'
        releases.mkdir(exist_ok=True)
        release = Path(tempfile.mkdtemp(prefix='release-', dir=releases))
        pending = prefix / ('.current-' + uuid.uuid4().hex)
        activated = False
        try:
            assemble(release, docker, installation, roots, state)
            bin_dir.mkdir(parents=True, exist_ok=True)
            expect_link(launcher, current / 'bin/loom')
            if not launcher.is_symlink():
                launcher.symlink_to(current / 'bin/loom')
            pending.symlink_to(Path('releases') / release.name)
            os.replace(pending, current)
            activated = True
        finally:
            pending.unlink(missing_ok=True)
            if not activated:
                info = release / 'installation.json'
                if info.is_file():
                    container = json.loads(info.read_text())['container']
                    removed = subprocess.run([docker, 'rm', '-f', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if removed.returncode:
                        raise ValueError(f'Activation failed and facility cleanup is unconfirmed; retained {release}')
                shutil.rmtree(release)
        print(f'Installed: {launcher}\nWorkspace roots: ' + ', '.join(map(str, roots)))
        print(f'Next: {launcher} setup')
        print('A single Linux facility runs all Works. Previous releases, Work data and host configuration are retained.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix', type=Path)
    p.add_argument('--bin-dir', type=Path)
    p.add_argument('--workspace-root', type=Path, action='append', help='host directory available to the trusted controller; repeatable (default ~/Loom)')
    a = p.parse_args()
    prefix = (a.prefix or Path.home() / '.local/share/loom').expanduser().resolve()
    bindir = (a.bin_dir or (prefix / 'bin' if a.prefix else Path.home() / '.local/bin')).expanduser().resolve()
    roots = [x.expanduser().resolve() for x in (a.workspace_root or [Path.home() / 'Loom'])]
    try:
        install(prefix, bindir, roots)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Loom installation failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
