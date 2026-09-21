"""Real native Linux installation; Docker is a forbidden command, not a mock."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/model'))
from provider_fixture import ProviderFixture


class NativeInstall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'linux' or os.geteuid() != 0:
            raise RuntimeError('Run this acceptance inside a prepared Linux facility as its administrator')
        cls.out = Path(os.environ.get('LOOM_NATIVE_INSTALL_EVIDENCE') or tempfile.mkdtemp(prefix='loom-native-install-')).resolve()
        cls.out.mkdir(parents=True, exist_ok=True)
        cls.out.chmod(0o755)
        cls.prefix = cls.out / 'installation with spaces'
        cls.workspace = cls.out / 'workspace'
        cls.binding = Path(os.environ['LOOM_EXECUTION_CONFIG'])
        cls.shims = cls.out / 'tools'; cls.shims.mkdir()
        cls.docker_calls = cls.out / 'forbidden-docker-calls'
        docker = cls.shims / 'docker'
        docker.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nimport sys\nPath(' + repr(str(cls.docker_calls)) + ').touch()\nsys.exit(99)\n')
        docker.chmod(0o755)
        cls.env = dict(os.environ, PATH=str(cls.shims)+os.pathsep+os.environ['PATH'], NATIVE_MODEL_KEY='synthetic-key', NATIVE_SANDBOX_KEY='synthetic-sandbox-key')
        cls.launcher = cls.prefix / 'bin/loom'
        cls.install('initial-install')

    @classmethod
    def call(cls, name, argv, env=None, timeout=300):
        result = subprocess.run(list(map(str, argv)), cwd=cls.out, env=env or cls.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        (cls.out / (name+'.log')).write_bytes(result.stdout)
        return result

    @classmethod
    def install(cls, name, env=None):
        # No --deployment: native is the Linux default.
        result = cls.call(name, [ROOT/'install.sh', '--prefix', cls.prefix, '--workspace-root', cls.workspace, '--execution-config', cls.binding], env=env, timeout=600)
        if result.returncode:
            raise AssertionError(result.stdout.decode())

    def test_01_installed_real_harness_and_isolation(self):
        release = (self.prefix/'current').resolve()
        info = json.loads((release/'installation.json').read_text())
        self.assertEqual(info['deployment'], 'native')
        self.assertNotIn('docker', info)
        self.assertEqual(info['runtime_sha256'], hashlib.sha256((release/'bin/loom-runtime').read_bytes()).hexdigest())
        result = self.call('isolation-probe', [self.launcher, 'check-facility'])
        self.assertEqual(result.returncode, 0, result.stdout.decode())
        self.assertIn(b'Work isolation and Python RPC ready', result.stdout)
        provider = ProviderFixture('text')
        thread = threading.Thread(target=provider.serve_forever, daemon=True); thread.start()
        try:
            model = self.out/'model.json'
            model.write_text(json.dumps({'id':'fixture-model','name':'Fixture','api':'openai-completions','provider':'fixture',
                'reasoning':False,'input':['text'],'contextWindow':32768,'maxTokens':1024,
                'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}))
            result = self.call('setup', [self.launcher,'setup','--sandbox-provider','opensandbox/v1','--model-file',model,
                '--model-endpoint',provider.base_url,'--sandbox-endpoint','http://127.0.0.1:2',
                '--model-key-env','NATIVE_MODEL_KEY','--sandbox-key-env','NATIVE_SANDBOX_KEY'])
            self.assertEqual(result.returncode,0,result.stdout.decode())
            host = tomllib.loads((Path(info['host_state'])/'.config/loom/config.toml').read_text())
            self.assertEqual(host['sandboxes']['code']['provider'],'opensandbox/v1')
            self.assertIn('options',host['profiles']['code'])
            project = self.workspace/'project';project.mkdir()
            (project/'source').write_bytes(b'preserved original\n')
            work = self.workspace/'work'
            for name, args in [('new',['new',work,'--userspace',project]),('ask',['ask',work,'Inspect native facility', '--request-id','native-check'])]:
                result = self.call(name,[self.launcher,*args])
                self.assertEqual(result.returncode,0,result.stdout.decode())
            self.assertIn(b'hello',result.stdout)
            with sqlite3.connect(work/'.loom/state.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM rounds WHERE state="handed_off"').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT count(*) FROM effects WHERE kind="model" AND resolution="native_result"').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT count(*) FROM pending').fetchone()[0],0)
            self.assertEqual((project/'source').read_bytes(),b'preserved original\n')
            self.assertEqual(len(provider.calls),1)
            (self.out/'model-calls.json').write_text(json.dumps(provider.calls,indent=2))
        finally:
            provider.shutdown();provider.server_close();thread.join()
        self.assertFalse(self.docker_calls.exists(),'native installation invoked Docker')

    def test_02_upgrade_retains_selected_components_and_configuration(self):
        old = (self.prefix/'current').resolve()
        info = json.loads((old/'installation.json').read_text())
        config = Path(info['host_state'])/'.config/loom/config.toml'
        before = config.read_bytes()
        old_python = old/'python/bin/python'
        code = 'import sys\nprint("ready",flush=True)\nsys.stdin.readline()\nfrom pylsp_jsonrpc.endpoint import Endpoint\nprint(sys.prefix,flush=True)\n'
        process = subprocess.Popen([old_python,'-I','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline(),'ready\n')
            self.install('upgrade')
            new = (self.prefix/'current').resolve()
            self.assertNotEqual(old,new)
            process.stdin.write('continue\n');process.stdin.flush()
            self.assertEqual(process.stdout.readline().strip(),str(old/'python'))
            self.assertEqual(process.wait(timeout=10),0)
            for name, exe in [('old',old/'bin/loom'),('new',self.launcher)]:
                result=self.call(name+'-after-upgrade',[exe,'check-facility'])
                self.assertEqual(result.returncode,0,result.stdout.decode())
            self.assertEqual(config.read_bytes(),before)
        finally:
            if process.poll() is None: process.kill()
            process.wait();process.stdin.close();process.stdout.close()
        self.assertFalse(self.docker_calls.exists())

    def test_03_failed_build_preserves_active_release(self):
        old = (self.prefix/'current').resolve()
        releases = sorted((self.prefix/'releases').iterdir())
        go = self.shims/'go';go.write_text('#!/bin/sh\nexit 23\n');go.chmod(0o755)
        try:
            result=self.call('failed-build',[ROOT/'install.sh','--prefix',self.prefix,'--workspace-root',self.workspace,'--execution-config',self.binding])
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((self.prefix/'current').resolve(),old)
            self.assertEqual(sorted((self.prefix/'releases').iterdir()),releases)
            self.assertEqual(self.call('retained-help',[self.launcher,'--help']).returncode,0)
        finally:
            go.unlink()


if __name__ == '__main__':
    unittest.main()
