#!/usr/bin/env python3
"""Describe an existing OpenSSH/systemd/NsJail facility; no Loom server to run."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state-directory', type=Path, default=Path('/var/lib/loom-process'))
    parser.add_argument('--nsjail', type=Path, default=Path('/usr/local/bin/nsjail'))
    parser.add_argument('--host-public-key', type=Path, default=Path('/etc/ssh/ssh_host_ed25519_key.pub'))
    args = parser.parse_args()
    if os.geteuid() != 0 or Path('/proc/1/comm').read_text().strip() != 'systemd':
        parser.error('run as administrator on the prepared systemd Linux facility')
    for name in ('systemctl', 'systemd-run', 'bash', 'tar', 'sha256sum', 'python3'):
        if shutil.which(name) is None:
            parser.error('missing prepared facility tool: ' + name)
    if shutil.which('python', path='/usr/local/loom-python/bin:/usr/local/bin:/usr/bin:/bin') is None:
        parser.error('the public toolchain must provide Python 3 as python (for example python-is-python3)')
    if not Path('/sys/fs/cgroup/cgroup.controllers').is_file():
        parser.error('cgroup v2 is required')
    subprocess.run(['systemctl', 'show', '--property=Version'], check=True, capture_output=True)
    state = args.state_directory
    if not state.is_absolute() or state.resolve() != state or state == Path('/'):
        parser.error('state directory must be absolute and have no symbolic components')
    state.mkdir(mode=0o711, parents=True, exist_ok=True)
    if state.stat().st_uid != 0 or state.stat().st_mode & 0o777 != 0o711:
        parser.error('existing state directory must be root-owned mode 0711')
    jail = args.nsjail.resolve(strict=True)
    host_key = args.host_public_key.read_text().strip()
    if not host_key.startswith('ssh-ed25519 '):
        parser.error('provide the facility OpenSSH Ed25519 public host key')
    options = dict(user='root', host_key=host_key, state_directory=str(state), nsjail=str(jail),
                   nsjail_sha256=hashlib.sha256(jail.read_bytes()).hexdigest(),
                   memory_bytes=536870912, processes=64, cpu_percent=100,
                   lease_seconds=600, request_timeout_seconds=30)
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(options, stream, indent=2)
        stream.write('\n')
    print('Non-secret provider options: ' + str(args.output))


if __name__ == '__main__':
    main()
