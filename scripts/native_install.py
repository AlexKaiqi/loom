"""Install on an administrator-prepared Linux facility without a Docker client."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tomllib


def run(argv, **kwargs):
    return subprocess.run([str(x) for x in argv], check=True, **kwargs)


def prerequisites(execution_config):
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Native installation requires the Linux facility administrator (root); macOS can use --deployment docker or a prepared Linux host')
    if execution_config is None:
        raise ValueError('Native installation requires --execution-config with a private NsJail binding and delegated cgroup v2')
    info = execution_config.lstat()
    if not execution_config.is_file() or execution_config.is_symlink() or info.st_mode & 0o077:
        raise ValueError('Execution configuration must be a private regular file (0600)')
    cfg = tomllib.loads(execution_config.read_text())
    launcher = Path(cfg['launcher'])
    if not launcher.is_absolute() or hashlib.sha256(launcher.read_bytes()).hexdigest() != cfg['launcher_sha256']:
        raise ValueError('NsJail binary does not match execution configuration')
    controllers = (Path(cfg['cgroup_root']) / 'cgroup.subtree_control').read_text().split()
    if not {'cpu', 'memory', 'pids'} <= set(controllers):
        raise ValueError('Native installation requires delegated cpu, memory and pids controllers')
    for tool in ('go', 'node', 'npm', 'git', 'sqlite3', 'bash', 'setfacl'):
        if not shutil.which(tool):
            raise ValueError(f'Native installation requires {tool} in the administrator toolchain')
    run(['node', '-e', 'if(Number(process.versions.node.split(".")[0])<24)process.exit(2)'])
    return cfg


def assemble(source, release, installation, roots, state, cfg, copy_component):
    assets = release / 'assets'
    for component in ('runtime', 'services/model', 'harnesses', 'templates', 'deploy'):
        copy_component(source / component, assets / component)
    (assets / 'docs').mkdir()
    shutil.copyfile(source / 'docs/loom-design-book.html', assets / 'docs/loom-design-book.html')
    binaries = release / 'bin'
    binaries.mkdir()
    # Each release keeps its own launcher, Python packages and Node modules.
    # Switching current cannot switch a running owner's components.
    run(['go', 'build', '-trimpath', '-o', binaries / 'loom-runtime', './cmd/loom'], cwd=assets / 'runtime',
        env=dict(os.environ, CGO_ENABLED='0'))
    shutil.copyfile(cfg['launcher'], binaries / 'nsjail')
    (binaries / 'nsjail').chmod(0o755)
    python = release / 'python'
    run([sys.executable, '-m', 'venv', python])
    run([python / 'bin/pip', 'install', '--disable-pip-version-check', '--no-cache-dir', '--require-hashes', '-r',
         assets / 'harnesses/kernel/requirements.lock'])
    run(['npm', 'ci', '--omit=dev', '--no-audit', '--no-fund'], cwd=assets / 'services/model')
    (assets / 'bin').mkdir()
    model = assets / 'bin/loom-model'
    model.write_text('#!/bin/sh\nexec ' + shlex.quote(shutil.which('node')) + ' ' +
                     shlex.quote(str(assets / 'services/model/worker.mjs')) + ' "$@"\n')
    model.chmod(0o755)
    snapshot = dict(cfg, launcher=str(binaries / 'nsjail'), python_environment=str(python))
    binding = release / 'execution.toml'
    binding.write_text(''.join(k + ' = ' + json.dumps(v) + '\n' for k, v in snapshot.items()))
    binding.chmod(0o600)
    env = dict(os.environ, LOOM_EXECUTION_CONFIG=str(binding), LOOM_INSTALL_ROOT=str(assets))
    run([binaries / 'loom-runtime', 'check-facility'], env=env)
    run(['node', '--input-type=module', '-e',
         'await import(' + json.dumps(str(assets / 'services/model/agent.mjs')) + '); '
         'const {apiFor}=await import(' + json.dumps(str(assets / 'services/model/pi.mjs')) + '); '
         'if(typeof (await apiFor({api:"openai-completions"})).streamSimple!=="function")process.exit(2)'])
    shutil.copyfile(source / 'scripts/launcher.py', binaries / 'loom')
    (binaries / 'loom').chmod(0o755)
    versions = {name: subprocess.check_output(argv, text=True).strip() for name, argv in {
        'go': ['go', 'version'], 'node': ['node', '--version'], 'git': ['git', '--version'],
        'python': [python / 'bin/python', '--version'], 'sqlite': ['sqlite3', '--version']}.items()}
    info = {'format': 3, 'deployment': 'native', 'installation_id': installation,
            'workspace_roots': list(map(str, roots)), 'host_state': str(state), 'versions': versions,
            'runtime_sha256': hashlib.sha256((binaries / 'loom-runtime').read_bytes()).hexdigest(),
            'execution_sha256': hashlib.sha256(binding.read_bytes()).hexdigest(),
            'go_build_info': subprocess.check_output(['go', 'version', '-m', binaries / 'loom-runtime'], text=True),
            'dependency_sha256': {name: hashlib.sha256((assets/name).read_bytes()).hexdigest() for name in
                ('runtime/go.mod', 'runtime/go.sum', 'services/model/package-lock.json', 'harnesses/kernel/requirements.lock')},
            'design_sha256': hashlib.sha256((assets / 'docs/loom-design-book.html').read_bytes()).hexdigest()}
    (release / 'installation.json').write_text(json.dumps(info, indent=2) + '\n')
