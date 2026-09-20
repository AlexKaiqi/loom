"""Real model bridge + named Targets + real remote OpenSandbox + private copies."""
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
from support import CLIFixture, ROOT, provider, query, ObservedHandler

class Targets(CLIFixture):
    def test_harness_can_reuse_allocation_without_a_model_loop(self):
        endpoint=os.environ.get('LOOM_SANDBOX_ENDPOINT')
        keyfile=os.environ.get('LOOM_SANDBOX_KEY_FILE')
        if not endpoint or not keyfile:
            self.skipTest('real OpenSandbox endpoint and private key file required')
        self.env['LOOM_TEST_SANDBOX_KEY']=Path(keyfile).read_text().strip()
        policy=self.policy(timeout=180)
        worker=policy/'worker.mjs'
        worker.write_text(worker.read_text().replace('c.listen();',"""
c.onRequest('policy.start',async p=>{
 const base={protocol_version:'loom/1',schema_version:1};
 await c.request('allocation.acquire',{...base,request_key:'resource',target:'default'});
 for(let n=1;n<=2;n++){
  const payload_ref=await c.request('record.put',{...base,media_type:'application/json',data_base64:Buffer.from(JSON.stringify({script:'echo '+n+' >> app/steps',timeout:20})).toString('base64')});
  const accepted=await c.request('effect.request',{...base,request_key:'step-'+n,kind:'tool.exec',environment:'sandbox',target:'default',payload_ref});
  const effect=await c.request('effect.inspect',{...base,id:accepted.effect_id});
  if(effect.status!=='completed')throw new Error('execution not confirmed');
 }
 const basis=await c.request('view.open',{...base,scope:'checkpoint'});
 return c.handoff(basis);
});c.listen();
"""))
        work=self.base/'work';source=self.base/'source';source.mkdir()
        self.call('create',work,'--harness',policy,'--definition',self.definition(userspace=True))
        self.call('grant-resource',work,'app',source);self.admit(work)
        with provider(work) as server:
            self.configure(server,sandbox_endpoint=endpoint)
            result=self.call('run',work,timeout=180)
            self.assertEqual(result['state'],'handed_off')
            self.assertEqual(server.calls,[])
        allocations=query(work,'SELECT * FROM allocations')
        self.assertEqual(len(allocations),1)
        self.assertEqual(allocations[0]['release_state'],'confirmed')
        effects=query(work,'SELECT * FROM effects ORDER BY rowid')
        self.assertEqual([e['kind'] for e in effects],['allocation.acquire','tool.exec','tool.exec'])
        for effect in effects[1:]:
            self.assertEqual(json.loads(effect['request'])['allocation_id'],allocations[0]['id'])
            self.assertEqual(json.loads(effect['result'])['receipt']['sandbox_id'],allocations[0]['sandbox_id'])
        restored=self.base/'restored'
        self.call('restore-resource',work,'app',restored,'--target','default')
        self.assertEqual((restored/'steps').read_text(),'1\n2\n')
        self.assertFalse((source/'steps').exists())

    def test_two_named_targets_have_independent_versions_and_readonly_resources(self):
        endpoint=os.environ.get('LOOM_SANDBOX_ENDPOINT')
        keyfile=os.environ.get('LOOM_SANDBOX_KEY_FILE')
        if not endpoint or not keyfile:
            self.skipTest('real OpenSandbox endpoint and private key file required')
        self.env['LOOM_TEST_SANDBOX_KEY']=Path(keyfile).read_text().strip()
        definition=self.definition(userspace=True,harness_argv=['python3','-I','{harness}/worker.py'])
        definition.write_text(definition.read_text().replace('contextWindow=4096','contextWindow=65536').replace('userspaces=["app"]','userspaces=["app","reference"]')+'''\n[userspaces.reference]
resource="shared-reference"
access="read"
[targets.backend]
profile="code"
userspaces=["app","reference"]
''')
        work=self.base/'work'
        self.call('create',work,'--harness',ROOT/'harnesses/kernel','--definition',definition)
        shutil.copyfile(ROOT/'templates/default/surface/main.md',work/'surface/main.md')
        project=self.base/'project';project.mkdir();(project/'state').write_text('initial')
        reference=self.base/'reference';reference.mkdir();(reference/'value').write_text('fixed')
        self.call('grant-resource',work,'app',project)
        self.call('grant-resource',work,'reference',reference)
        self.admit(work)
        class NamedTargetProvider(ObservedHandler):
            def openai(self,mode,number):
                if number<=2:
                    target='default' if number==1 else 'backend'
                    script="""python - <<'PY'
from pathlib import Path
assert Path('app/state').read_text()=='initial'
assert Path('reference/value').read_text()=='fixed'
try:Path('reference/value').write_text('unauthorized')
except OSError:pass
else:raise AssertionError('read resource writable')
Path('app/state').write_text(TARGET)
print('written '+TARGET)
PY
""".replace('TARGET',repr(target))
                    if number==2:
                        (project/'state').write_text('human shared update')
                    self.chunk({'role':'assistant','tool_calls':[{'index':0,'id':'target_'+str(number),'type':'function','function':{'name':'bash','arguments':json.dumps({'environment':'sandbox','target':target,'script':script})}}]})
                    self.chunk(finish='tool_calls');self.event('[DONE]')
                else:
                    super().openai(mode,number)
        with provider(work) as server:
            server.RequestHandlerClass=NamedTargetProvider
            self.configure(server,sandbox_endpoint=endpoint)
            result=self.call('run',work,timeout=120)
            self.assertEqual(result['state'],'handed_off')
            self.assertEqual(len(server.calls),3)
            self.save_provider(server)
        self.assertEqual((project/'state').read_text(),'human shared update')
        self.assertEqual((reference/'value').read_text(),'fixed')
        copies=query(work,"select * from resource_copies where alias='app' order by target")
        self.assertEqual(len(copies),2)
        self.assertNotEqual(copies[0]['id'],copies[1]['id'])
        for copy in copies:
            ref=json.loads(copy['content_ref'])
            with tarfile.open(fileobj=io.BytesIO((work/'.loom/records'/ref['sha256']).read_bytes())) as archive:
                self.assertEqual(archive.extractfile('state').read().decode(),copy['target'])
        allocations=query(work,'select * from allocations order by rowid')
        self.assertEqual(len(allocations),2)
        self.assertNotEqual(allocations[0]['sandbox_id'],allocations[1]['sandbox_id'])
        self.assertTrue(all(a['release_state']=='confirmed' for a in allocations))
        readiness = query(work, "SELECT payload FROM events WHERE kind='target.ready' ORDER BY seq")
        self.assertEqual(len(readiness), 2)
        for row, allocation in zip(readiness, allocations):
            ready = json.loads(row['payload'])
            self.assertEqual(ready['allocation_id'], allocation['id'])
            self.assertEqual(ready['sandbox_id'], allocation['sandbox_id'])
            self.assertEqual(ready['readiness']['platform'], 'linux')
            self.assertEqual(ready['readiness']['uid'], 65534)
            self.assertEqual(ready['readiness']['network'], 'denied')
            self.assertEqual(ready['readiness']['readonly_paths'], ['reference'])
            probe = next(a for a in ready['artifacts'] if a['name'] == 'readiness.json')
            ref = probe['record_ref']
            raw = (work/'.loom/records'/ref['sha256']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
            self.assertEqual(json.loads(raw)['ExitCode'], 0)
        for allocation in allocations:
            binding=json.loads(allocation['binding'])
            self.assertEqual(binding['target'],allocation['target'])
            ref=binding['userspace_bindings_ref']
            manifest=json.loads((work/'.loom/records'/ref['sha256']).read_text())
            self.assertEqual([(b['alias'],b['access']) for b in manifest['bindings']],[('app','write'),('reference','read')])
