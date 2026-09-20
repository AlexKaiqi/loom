"""Actual Go -> isolated Harness -> Pi -> Work Bash -> next projection path."""
import json
import io
from pathlib import Path
import shutil
from contextlib import closing
import sqlite3
import subprocess
import tarfile
import time
from support import CLIFixture, ROOT, provider, query, ObservedHandler, assert_no_secrets


class WorkEnvironment(CLIFixture):
    def test_sigkill_recovery_fences_live_writer_and_retains_unconfirmed_bytes(self):
        policy = self.policy(timeout=120)
        worker = policy/'worker.mjs'
        worker.write_text(worker.read_text().replace('c.listen();', '''
c.onRequest('policy.start',async p=>{
 const base={protocol_version:'loom/1',schema_version:1};
 const payload_ref=await c.request('record.put',{...base,media_type:'application/json',data_base64:Buffer.from(JSON.stringify({script:'echo once >> surface/dispatch; (while :; do echo progress >> surface/heartbeat; sleep .03; done) & wait',timeout:120})).toString('base64')});
 return c.request('effect.request',{...base,request_key:'writer',kind:'tool.exec',environment:'work',payload_ref});
});c.listen();
'''))
        work = self.base/'work'
        self.call('create', work, '--harness', policy, '--definition', self.definition(sandbox=False))
        self.admit(work)
        self.configure(model_endpoint='http://127.0.0.1:1')
        child = subprocess.Popen(self.command('run', work), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
        try:
            deadline = time.monotonic()+20
            domain = None
            while time.monotonic()<deadline:
                with closing(sqlite3.connect(self.authority)) as db:
                    db.row_factory=sqlite3.Row
                    row=db.execute("SELECT * FROM execution_domains WHERE role='bash' AND state='retained'").fetchone()
                if row:
                    domain=dict(row)
                    heartbeat=Path(domain['staging'])/'surface/heartbeat'
                    if heartbeat.exists() and len(heartbeat.read_bytes())>=18:
                        break
                time.sleep(.03)
            else:
                self.fail('real Work writer did not start')
            before = heartbeat.read_bytes()
            epoch = query(work,'SELECT epoch FROM rounds')[0]['epoch']
            child.kill()
            child.communicate(timeout=10)
            self.assertEqual(child.returncode, -9)
            time.sleep(.12)
            self.assertGreater(len(heartbeat.read_bytes()), len(before), 'fault did not leave a live old writer to fence')
            self.call('run',work,ok=False)
            self.call('resume',work,ok=False)
            recovered=self.call('recover',work)
            self.assertGreater(query(work,'SELECT epoch FROM rounds')[0]['epoch'],epoch)
            self.assertEqual(query(work,'SELECT state FROM rounds')[0]['state'],'blocked')
            self.assertFalse(Path(domain['cgroup']).exists(), 'old cgroup survived confirmed recovery')
            self.assertFalse(Path(domain['staging']).exists(), 'recovery did not finish preserving and clearing staging')
            facts=query(work,"SELECT payload FROM events WHERE kind='execution.recovery'")
            retained=next(json.loads(row['payload']) for row in facts if json.loads(row['payload'])['role']=='bash')
            ref=retained['record_ref']
            with tarfile.open(fileobj=io.BytesIO((work/'.loom/records'/ref['sha256']).read_bytes())) as archive:
                self.assertEqual(archive.extractfile('surface/dispatch').read(),b'once\n')
                self.assertTrue(archive.extractfile('surface/heartbeat').read().startswith(before))
            self.assertFalse((work/'surface/heartbeat').exists(), 'unconfirmed bytes were silently committed')
            effects=query(work,'SELECT * FROM effects')
            self.assertEqual(len(effects),1)
            self.assertEqual(effects[0]['resolution'],'unresolved')
            self.assertEqual(len(query(work,'SELECT * FROM pending')),1)
            self.call('resume',work,ok=False)
            self.assertEqual(query(work,'SELECT * FROM effects'),effects)
            (self.base/'recovery-observations.json').write_text(json.dumps({'retained':retained,'recovered':recovered,'killed_domain':domain,'bytes_before_kill':len(before)},indent=2))
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)

    def test_bash_edits_reproject_and_candidate_does_not_replace_running_strategy(self):
        work = self.base / 'work'
        definition = self.definition(sandbox=False,harness_argv=["python3","-I","{harness}/worker.py"])
        definition.write_text(definition.read_text().replace('contextWindow=4096', 'contextWindow=65536'))
        self.call('create', work, '--harness', ROOT / 'harnesses/kernel', '--definition', definition)
        shutil.copyfile(ROOT / 'templates/default/surface/main.md', work / 'surface/main.md')
        private = self.base / 'private-host-secret'
        private.write_text('host-private-content')
        self.admit(work)
        script = '''python3 - <<'PY'
import os, pathlib, sqlite3, json
out={'uid':os.getuid(),'host_private':pathlib.Path(PRIVATE).exists()}
try: os.fstat(3); out['control_fd']=True
except OSError: out['control_fd']=False
try: os.setuid(100000);out['become_harness']=True
except OSError:out['become_harness']=False
with sqlite3.connect(os.environ['FACTS_DB']) as db:
 out['view']=db.execute('select schema_version,fact_watermark from view_meta').fetchone()
 out['record_paths']=[r[0] for r in db.execute('select record_path from facts')]
 try:db.execute('delete from facts');out['write_facts']=True
 except sqlite3.Error:out['write_facts']=False
out['records_readable']=all(pathlib.Path(p).is_file() for p in out['record_paths'])
p=pathlib.Path('/work/surface/main.md');p.write_text(p.read_text()+'\\nLOCAL_EDIT_VISIBLE_NEXT_PROJECTION\\n')
pathlib.Path('/work/harness/worker.py').write_text('raise RuntimeError("CANDIDATE_MUST_NOT_RUN")\\n')
pathlib.Path('/work/surface/observed.json').write_text(json.dumps(out))
print(json.dumps(out))
PY
printf 'nonzero exit evidence\\n' >&2
exit 7
'''.replace('PRIVATE',repr(str(private)))
        class ToolProvider(ObservedHandler):
            def openai(self,mode,number):
                if number==1:
                    self.chunk({'role':'assistant','tool_calls':[{'index':0,'id':'work_edit','type':'function','function':{'name':'bash','arguments':json.dumps({'environment':'work','script':script})}}]})
                    self.chunk(finish='tool_calls')
                    self.event('[DONE]')
                else:
                    super().openai(mode,number)
        with provider(work) as server:
            server.RequestHandlerClass=ToolProvider
            self.configure(server)
            result=self.call('run',work,timeout=30)
            self.assertEqual(result['state'],'handed_off')
            self.assertEqual(len(server.calls),2)
            self.assertIn('LOCAL_EDIT_VISIBLE_NEXT_PROJECTION',json.dumps(server.calls[1]['body']))
            self.assertNotIn('LOCAL_EDIT_VISIBLE_NEXT_PROJECTION',json.dumps(server.calls[0]['body']))
            self.assertIn('nonzero exit evidence',json.dumps(server.calls[1]['body']))
            self.save_provider(server)
        observed=json.loads((work/'surface/observed.json').read_text())
        self.assertEqual(observed['uid'],100001)
        for field in ['host_private','control_fd','become_harness','write_facts']:
            self.assertFalse(observed[field],field)
        self.assertTrue(observed['records_readable'])
        effects=query(work,"select * from effects where kind='tool.exec'")
        self.assertEqual(len(effects),1)
        self.assertEqual(effects[0]['resolution'],'native_result')
        result=json.loads(effects[0]['result'])
        self.assertEqual(result['exit_code'],7)
        self.assertTrue(result['tool_result']['isError'])
        tool_fact=json.loads(query(work,"select payload from events where kind='tool.result'")[0]['payload'])
        self.assertTrue(tool_fact['message']['isError'])
        self.assertEqual(tool_fact['exit_code'],7)
        self.assertEqual((work/'.loom/records'/result['stderr_ref']['sha256']).read_text(),'nonzero exit evidence\n')
        with closing(sqlite3.connect(self.authority)) as db:
            self.assertEqual(db.execute("select count(*) from execution_domains where state='retained'").fetchone()[0],0)
        self.assertGreater(assert_no_secrets(work,[b'host-private-content',b'go-acceptance-synthetic-key']),0)
