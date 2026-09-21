"""Black-box shared-facility installation checks; preserve all failed evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get('LOOM_INSTALL_TEST_OUTPUT') or tempfile.mkdtemp(prefix='loom-install-validation-')).resolve()
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.prefix = cls.output / 'install with spaces'
        cls.home = cls.output / 'synthetic home'
        cls.home.mkdir()
        cls.outside = cls.output / 'outside checkout'
        cls.outside.mkdir()
        cls.env = os.environ.copy()
        # Docker client context remains available; its files are neither copied
        # into evidence nor mounted in the Work facility.
        cls.env.setdefault('DOCKER_CONFIG', str(Path.home() / '.docker'))
        cls.env['HOME'] = str(cls.home)
        cls.env.pop('LOOM_INSTALL_ROOT', None)
        cls.env['INSTALL_MODEL_KEY'] = 'synthetic-installer-model-key'
        cls.env['INSTALL_SANDBOX_KEY'] = 'synthetic-installer-sandbox-key'
        cls.docker = shutil.which('docker')
        if not cls.docker:
            raise RuntimeError('real Docker Linux engine required')
        cls.config = cls.home / '.config/loom/config.toml'
        cls.config.parent.mkdir(parents=True)
        cls.config.write_text('# user-owned sentinel\n[models.user]\nendpoint="https://example.invalid"\n')
        cls.config_bytes = cls.config.read_bytes()
        cls.observations = {}
        print(f'Installer observations: {cls.output}', file=sys.stderr)
        result = cls.invoke('initial-install', cls.install_command(), timeout=1800)
        if result.returncode:
            raise AssertionError(f'initial install failed; read {cls.output / "initial-install.log"}')
        cls.launcher = cls.prefix / 'bin/loom'

    @classmethod
    def install_command(cls, *extra):
        return [ROOT / 'install.sh', '--deployment', 'docker', '--prefix', cls.prefix, '--workspace-root', cls.output, *extra]

    @classmethod
    def invoke(cls, name, command, **kwargs):
        result = subprocess.run([str(p) for p in command], cwd=cls.outside, env=kwargs.pop('env', cls.env),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
        (cls.output / (name + '.log')).write_bytes(result.stdout)
        return result

    @classmethod
    def binding(cls, release=None):
        release = release or (cls.prefix / 'current').resolve()
        return json.loads((release / 'installation.json').read_text())

    @classmethod
    def tearDownClass(cls):
        (cls.output / 'observations.json').write_text(json.dumps(cls.observations, indent=2) + '\n')
        # Only containers with this test installation's retained identities are
        # removed. Keep image/release/log evidence and never prune Docker state.
        for release in (cls.prefix / 'releases').iterdir():
            if (release / 'installation.json').is_file():
                info = cls.binding(release)
                cls.invoke('cleanup-' + release.name, [cls.docker, 'rm', '-f', info['container']], timeout=30)

    def test_01_real_install_outside_source_and_harness_execution(self):
        current = (self.prefix / 'current').resolve()
        info = self.binding()
        self.assertTrue(self.launcher.is_symlink())
        self.assertEqual(self.invoke('installed-help', [self.launcher, '--help'], timeout=30).returncode, 0)
        inspect = self.invoke('facility-inspect', [self.docker, 'inspect', info['container']], timeout=30)
        actual = json.loads(inspect.stdout)[0]
        self.assertEqual(actual['Image'], info['image_id'])
        self.assertEqual(actual['Config']['Labels']['loom.installation'], info['installation_id'])
        self.assertFalse((current / 'build').exists())
        self.assertEqual(self.invoke('installed-pi', [self.docker, 'exec', info['container'], 'node', '-e',
            'import("/opt/loom/services/model/node_modules/@earendil-works/pi-ai/dist/index.js").then(m=>{if(typeof m.lazyStream!=="function")process.exit(2)})'], timeout=30).returncode, 0)
        # Start the controlled HTTP peer inside the facility. The installed CLI,
        # ordinary Python Harness, NsJail and actual Pi adapter remain real.
        shutil.copyfile(ROOT / 'tests/model/provider_fixture.py', self.output / 'provider_fixture.py')
        server_script = self.output / 'server.py'
        server_script.write_text('from provider_fixture import ProviderFixture\nimport json,sys,threading\n'
                                's=ProviderFixture("text")\nt=threading.Thread(target=s.serve_forever,daemon=True);t.start()\n'
                                'print(s.base_url,flush=True)\nsys.stdin.readline()\ns.shutdown();s.server_close();t.join()\n'
                                'print(json.dumps(s.calls),flush=True)\n')
        process = subprocess.Popen([self.docker, 'exec', '-i', info['container'], 'python3', str(server_script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, text=True)
        try:
            endpoint = process.stdout.readline().strip()
            self.assertTrue(endpoint.startswith('http://127.0.0.1:'))
            model = self.output / 'native-model.json'
            model.write_text(json.dumps({'id':'fixture-model','name':'Fixture','api':'openai-completions',
                'provider':'fixture','reasoning':True,'input':['text'],'contextWindow':32768,'maxTokens':1024,
                'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}))
            configured = self.invoke('installed-setup', [self.launcher,'setup','--sandbox-provider','opensandbox/v1','--model-file',model,
                '--model-endpoint',endpoint,'--sandbox-endpoint','http://127.0.0.1:2',
                '--model-key-env','INSTALL_MODEL_KEY','--sandbox-key-env','INSTALL_SANDBOX_KEY'],timeout=30)
            self.assertEqual(configured.returncode,0,configured.stdout.decode())
            work = self.output / 'portable work'
            task_files = self.output / 'task files'
            task_files.mkdir()
            task_files.joinpath('unchanged.txt').write_text('shared original')
            created = self.invoke('installed-new',[self.launcher,'new',work,'--userspace',task_files],timeout=30)
            self.assertEqual(created.returncode,0,created.stdout.decode())
            same = self.output/'same-project-work'
            other = self.output/'other-project-work'
            other_files = self.output/'other-project';other_files.mkdir()
            for name,destination,source in [('same-project',same,task_files),('other-project',other,other_files)]:
                result=self.invoke(name,[self.launcher,'new',destination,'--userspace',source],timeout=30)
                self.assertEqual(result.returncode,0,result.stdout.decode())
            resource=lambda p:tomllib.loads((p/'work.toml').read_text())['userspaces']['app']['resource']
            self.assertEqual(resource(work),resource(same),'same physical project acquired another resource identity')
            self.assertNotEqual(resource(work),resource(other),'independent projects collided on the template resource name')
            answered = self.invoke('installed-ask',[self.launcher,'ask',work,'Inspect installer dependency isolation','--request-id','installer-check'],timeout=60)
            self.assertEqual(answered.returncode,0,answered.stdout.decode())
            self.assertIn(b'hello',answered.stdout)
            with sqlite3.connect(work / '.loom/state.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM rounds WHERE state="handed_off"').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT count(*) FROM pending').fetchone()[0],0)
                self.assertGreater(db.execute('SELECT count(*) FROM events WHERE kind="projection.published"').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM effects WHERE kind="model" AND resolution="native_result"').fetchone()[0],1)
            self.assertEqual(task_files.joinpath('unchanged.txt').read_text(),'shared original')
            process.stdin.write('stop\n');process.stdin.flush()
            calls = json.loads(process.stdout.readline())
            self.assertEqual(len(calls),1)
            (self.output / 'provider-calls.json').write_text(json.dumps(calls,indent=2))
            self.assertEqual(process.wait(timeout=10),0)
        finally:
            if process.poll() is None: process.kill()
            process.wait(timeout=10)
            for pipe in (process.stdin,process.stdout,process.stderr):pipe.close()
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.observations['outside-source'] = {'release':str(current),'image_id':info['image_id'],'work':str(work)}

    def test_02_upgrade_retains_release_and_running_worker_binding(self):
        previous = (self.prefix / 'current').resolve()
        old = self.binding(previous)
        private_config = Path(old['host_state']) / '.config/loom/config.toml'
        config_bytes = private_config.read_bytes()
        self.assertIn(b'loom-model',config_bytes)
        self.assertNotIn(b'launcher_sha256',config_bytes)
        # This real Node process waits across activation and imports its Pi module
        # afterwards. Its already-selected container/image cannot change under it.
        script = 'process.stdout.write("ready\\n");process.stdin.once("data",async()=>{const m=await import("/opt/loom/services/model/node_modules/@earendil-works/pi-ai/dist/index.js");if(typeof m.lazyStream!=="function")process.exit(2);process.stdout.write(process.env.HOSTNAME+"\\n");process.exit(0)})'
        process = subprocess.Popen([self.docker,'exec','-i',old['container'],'node','-e',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=self.env,text=True)
        try:
            self.assertEqual(process.stdout.readline(),'ready\n')
            result = self.invoke('reinstall',self.install_command(),timeout=1800)
            self.assertEqual(result.returncode,0,result.stdout.decode())
            current=(self.prefix/'current').resolve();new=self.binding(current)
            self.assertNotEqual(previous,current)
            self.assertNotEqual(old['container'],new['container'])
            process.stdin.write('start\n');process.stdin.flush()
            old_hostname=process.stdout.readline().strip()
            self.assertEqual(process.wait(timeout=15),0)
            new_check=self.invoke('new-worker-import',[self.docker,'exec',new['container'],'node','-e',
                'import("/opt/loom/services/model/node_modules/@earendil-works/pi-ai/dist/index.js").then(()=>console.log(process.env.HOSTNAME))'],timeout=30)
            self.assertEqual(new_check.returncode,0,new_check.stdout.decode())
            self.assertNotEqual(old_hostname,new_check.stdout.decode().strip())
            self.assertEqual(self.invoke('old-launcher-after-upgrade',[previous/'bin/loom','--help'],timeout=30).returncode,0)
            self.assertEqual(self.invoke('new-launcher-after-upgrade',[self.launcher,'--help'],timeout=30).returncode,0)
            self.assertEqual(private_config.read_bytes(),config_bytes)
            self.assertEqual(self.config.read_bytes(),self.config_bytes)
            self.observations['upgrade']={'old':old,'new':new,'configuration_sha256':sha(private_config)}
        finally:
            if process.poll() is None:process.kill()
            process.wait(timeout=10)
            for pipe in (process.stdin,process.stdout,process.stderr):pipe.close()

    def test_03_failed_build_preserves_active_release(self):
        previous=os.readlink(self.prefix/'current')
        contents=sorted(p.name for p in (self.prefix/'releases').iterdir())
        info=self.binding()
        shims=self.output/'failed build tools';shims.mkdir()
        shim=shims/'docker'
        shim.write_text('#!'+sys.executable+'\nimport os,sys\nif sys.argv[1:2]==["build"]:\n print("deliberate image build failure",file=sys.stderr);sys.exit(23)\nos.execv('+repr(self.docker)+', ['+repr(self.docker)+']+sys.argv[1:])\n')
        shim.chmod(0o755)
        env=dict(self.env,PATH=str(shims)+os.pathsep+self.env['PATH'])
        result=self.invoke('failed-build',self.install_command(),env=env,timeout=60)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'deliberate image build failure',result.stdout)
        self.assertEqual(os.readlink(self.prefix/'current'),previous)
        self.assertEqual(sorted(p.name for p in (self.prefix/'releases').iterdir()),contents)
        self.assertEqual(self.binding(),info)
        self.assertEqual(self.invoke('after-failure-help',[self.launcher,'--help'],timeout=30).returncode,0)
        self.assertEqual(self.config.read_bytes(),self.config_bytes)
        self.observations['failed-build']={'current':previous,'retained':info}

    def test_04_unrelated_launcher_is_not_overwritten(self):
        bindir=self.output/'unrelated bin';bindir.mkdir()
        unrelated=bindir/'loom';unrelated.write_bytes(b'user executable must survive\n')
        before=unrelated.read_bytes()
        result=self.invoke('unrelated-launcher',[ROOT/'install.sh','--deployment','docker','--prefix',self.output/'unrelated prefix','--bin-dir',bindir,'--workspace-root',self.output],timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'Refusing to replace',result.stdout)
        self.assertEqual(unrelated.read_bytes(),before)

    def test_05_wrong_engine_never_activates(self):
        # Node belongs to the locked image now. The corresponding host prerequisite
        # failure is a non-Linux Docker engine, not a host Node version mismatch.
        shims=self.output/'wrong engine tools';shims.mkdir()
        shim=shims/'docker';shim.write_text('#!/bin/sh\nprintf "windows\\n"\n');shim.chmod(0o755)
        env=dict(self.env,PATH=str(shims)+os.pathsep+self.env['PATH'])
        prefix=self.output/'wrong engine install'
        result=self.invoke('wrong-engine',[ROOT/'install.sh','--deployment','docker','--prefix',prefix,'--workspace-root',self.output],env=env,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'Docker must use a Linux engine',result.stdout)
        self.assertFalse((prefix/'current').exists())


if __name__=='__main__':unittest.main()
