"""Same Target contracts against the real prepared process facility."""
import json
import os
import signal
import subprocess
import time
from pathlib import Path
import test_targets
from support import assert_no_secrets, provider, query


class ProcessTargets(test_targets.Targets):
    def setUp(self):
        super().setUp()
        if not os.environ.get('LOOM_SSH_OPTIONS'):
            self.skipTest('real SSH/systemd/NsJail options required')

    def configure(self, *args, **kwargs):
        super().configure(*args, **kwargs)
        options = json.loads(Path(os.environ['LOOM_SSH_OPTIONS']).read_text())
        text = self.config.read_text()
        begin = text.index('[sandboxes.sandbox-main]')
        end = text.index('[execution]')
        native = ['[sandboxes.sandbox-main]', 'provider="ssh-process/v1"',
                  'api_key_env="LOOM_TEST_SANDBOX_KEY"',
                  'endpoint=' + json.dumps(kwargs['sandbox_endpoint']),
                  '[profiles.code]', 'service="sandbox-main"', '[profiles.code.options]']
        native.extend(k + '=' + json.dumps(v) for k, v in options.items())
        self.config.write_text(text[:begin] + '\n'.join(native) + '\n' + text[end:])

    def assert_native_probe(self, raw):
        value = json.loads(raw)
        self.assertEqual(value['platform'], 'linux')
        self.assertEqual(value['uid'], 65534)
        self.assertEqual(value['network'], 'denied')
        self.assertTrue(value['no_new_privileges'])

    def test_killed_controller_recovers_original_process_without_replay(self):
        self.env['LOOM_TEST_SANDBOX_KEY'] = Path(os.environ['LOOM_SANDBOX_KEY_FILE']).read_text().strip()
        policy = self.policy(timeout=60)
        worker = policy / 'worker.mjs'
        worker.write_text(worker.read_text().replace('c.listen();', '''
c.onRequest('policy.start',async p=>{
 const base={protocol_version:'loom/1',schema_version:1};
 const payload_ref=await c.request('record.put',{...base,media_type:'application/json',data_base64:Buffer.from(JSON.stringify({script:'echo once >> app/executions; sleep 30',timeout:40})).toString('base64')});
 await c.request('effect.request',{...base,request_key:'once',kind:'tool.exec',environment:'sandbox',target:'default',payload_ref});
 throw new Error('observer must kill the controller first');
});c.listen();
'''))
        work = self.base/'work'; source = self.base/'source'; source.mkdir()
        self.call('create',work,'--harness',policy,'--definition',self.definition(userspace=True))
        self.call('grant-resource',work,'app',source); self.admit(work)
        with provider(work) as server:
            self.configure(server,sandbox_endpoint=os.environ['LOOM_SANDBOX_ENDPOINT'])
            child = subprocess.Popen(self.command('run',work),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
            try:
                deadline = time.monotonic()+10
                while time.monotonic()<deadline:
                    effects = query(work,"SELECT * FROM effects WHERE kind='tool.exec'")
                    if effects and effects[0]['receipt'] and json.loads(effects[0]['receipt']).get('phase')=='accepted':
                        break
                    time.sleep(.02)
                else:
                    self.fail('original remote execution was never accepted')
                effect = effects[0]; receipt = json.loads(effect['receipt'])
                self.assertEqual(receipt['binding']['provider'],'ssh-process/v1')
                child.kill(); stdout,stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode,-signal.SIGKILL)
                (self.base/'killed-controller.json').write_text(json.dumps(dict(stdout=stdout,stderr=stderr,receipt=receipt)))
                # A changed current Profile must not redirect original Query/Cancel.
                self.config.write_text(self.config.read_text().replace('state_directory="/var/lib/loom-process"','state_directory="/var/lib/different-process-facility"'))
                observed = self.call('query-remote',work,effect['round_id'],effect['id'])
                self.assertEqual(observed['execution_id'],receipt['execution_id'])
                self.assertEqual(observed['status']['SubState'],'running')
                cancelled = self.call('cancel-effect',work,effect['round_id'],effect['id'])
                self.assertEqual(cancelled['cancellation'],'stop_confirmed')
                self.call('recover',work)
                self.call('run',work,ok=False); self.call('resume',work,ok=False)
                saved = query(work,"SELECT * FROM effects WHERE kind='tool.exec'")
                self.assertEqual(len(saved),1)
                self.assertEqual(saved[0]['status'],'unknown')
                self.assertEqual(saved[0]['resolution'],'unresolved')
                self.assertEqual(saved[0]['cancellation'],'stop_confirmed')
                self.assertEqual(saved[0]['content_delivery'],'pending')
                self.assertEqual(query(work,'SELECT state FROM rounds'),[{'state':'blocked'}])
                self.assertEqual(json.loads(saved[0]['receipt'])['execution_id'],receipt['execution_id'])
                self.assertEqual(server.calls,[])
                self.assertFalse((source/'executions').exists())
                options=json.loads(receipt['binding']['options_json'])
                import hashlib
                remote=Path(options['state_directory'])/receipt['sandbox_id']/hashlib.sha256(effect['id'].encode()).hexdigest()/'task/app/executions'
                # This suite runs on the fixture host, independently of the adapter.
                self.assertEqual(remote.read_text(),'once\n')
            finally:
                if child.poll() is None: child.kill()
                child.communicate(timeout=5)

    def tearDown(self):
        if hasattr(self, 'base') and (self.base / 'work').exists():
            key = Path(os.environ['LOOM_SANDBOX_KEY_FILE']).read_bytes().strip()
            assert_no_secrets(self.base / 'work', [key, b'go-acceptance-synthetic-key'])
        super().tearDown()
