#!/usr/bin/env python3
"""Route the normal CLI into one installed shared Linux facility."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tomllib


def main():
    release = Path(__file__).resolve().parent.parent
    installation = json.loads((release / 'installation.json').read_text())
    if installation['deployment'] == 'native':
        if sys.platform != 'linux' or os.geteuid() != 0:
            raise ValueError('Native Work facility requires the Linux administrator controller identity')
        binary = release / 'bin/loom-runtime'
        binding = release / 'execution.toml'
        if hashlib.sha256(binary.read_bytes()).hexdigest() != installation['runtime_sha256'] or hashlib.sha256(binding.read_bytes()).hexdigest() != installation['execution_sha256']:
            raise ValueError('Native facility differs from installed release')
        assets = release / 'assets'
        env = dict(os.environ, LOOM_EXECUTION_CONFIG=str(binding), LOOM_INSTALL_ROOT=str(assets),
                   PATH=str(assets / 'bin') + os.pathsep + os.environ.get('PATH', ''))
        # Explicit CLI paths still override the private deployment defaults.
        args = ['--authority', installation['host_state'] + '/authority.sqlite', '--config',
                installation['host_state'] + '/.config/loom/config.toml', *sys.argv[1:]]
        os.execve(binary, [str(binary), *args], env)
    if installation['deployment'] != 'docker':
        raise ValueError('Unsupported facility deployment')
    docker, container = installation['docker'], installation['container']
    info = json.loads(subprocess.check_output([docker, 'inspect', container]))[0]
    if info['Config']['Labels'].get('loom.installation') != installation['installation_id']:
        raise ValueError('facility installation identity differs')
    if info['Image'] != installation['image_id']:
        raise ValueError('facility image differs from installed release')
    if not info['State']['Running']:
        subprocess.run([docker, 'start', container], check=True, stdout=subprocess.DEVNULL)
    cwd = str(Path.cwd().resolve())
    roots = installation['workspace_roots']
    if not any(cwd == r or cwd.startswith(r + '/') for r in roots):
        cwd = roots[0]
    argv = [docker, 'exec', '-i']
    if sys.stdin.isatty() and sys.stdout.isatty():
        argv += ['-t']
    # Only host configuration names credential variables. Values never occur in
    # Docker argv, Work files, image layers or launcher diagnostics.
    config = installation['host_state'] + '/.config/loom/config.toml'
    args = sys.argv[1:]
    if '--config' in args:
        position = args.index('--config') + 1
        if position == len(args):
            raise ValueError('--config requires a path')
        config = args[position]
    for arg in args:
        if arg.startswith('--config='):
            config = arg.split('=', 1)[1]
    names = set()
    if Path(config).is_file():
        settings = tomllib.loads(Path(config).read_text())
        for family in ('models', 'sandboxes'):
            for service in settings.get(family, {}).values():
                if service.get('api_key_env'):
                    names.add(service['api_key_env'])
                names.update(service.get('headers_env', {}).values())
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('invalid credential environment name')
        if name in os.environ:
            argv += ['--env', name]
    argv += ['--workdir', cwd, container, 'loom-runtime', *args]
    os.execv(docker, argv)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('loom facility: ' + str(error), file=sys.stderr)
        sys.exit(1)
