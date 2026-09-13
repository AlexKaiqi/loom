"""Finite external-observer controls; no X product or Docker execution."""
from pathlib import Path
import base64,copy,hashlib,json,os,sys,time,unittest
from unittest.mock import patch
import run as driver
from collector import Collector
from fixtures import script_bytes,SCRIPTS,create
from oracle import EvidenceError
from runtime_observations import memory_limit_facts,ready_value,source_event,await_fixture_stdio
from source_closure import AUDIT,inventory
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(sys.argv.pop(1));OUT.mkdir(exist_ok=False,parents=True)
PRIOR=ROOT/'design/g4/x-validation-repair-001/prior'
OLD=ROOT/'validation/components/x/evidence/author-full-001/workspace/validation/components/x/evidence/actual'
class Controls(unittest.TestCase):
 def test_original_28_97_all_expected_preserved(self):
  old=json.loads((PRIOR/'design/g3/x/cases.json').read_text());new=json.loads((ROOT/'design/g3/x/cases.json').read_text())
  self.assertEqual(len(old['cases']),28);self.assertEqual(inventory(old['cases']),inventory(new['cases']));self.assertEqual(len(inventory(new['cases'])),97)
  additions={}
  for a,b in zip(old['cases'],new['cases']):
   self.assertEqual({k:v for k,v in a.items() if k not in ('actions','expected')},{k:v for k,v in b.items() if k not in ('actions','expected')})
   self.assertEqual(b['expected'][:len(a['expected'])],a['expected']);additions[a['id']]=b['expected'][len(a['expected']):]
   oldactions=[x for x in a['actions'] if not (a['id'] in ('X015','X026') and x['op']=='delay')]
   if a['id']=='X019':continue # root-approved peer-budget protocol changes execute to CREATED and moves full collect after peer stop
   j=0
   for action in b['actions']:
    if j<len(oldactions) and action==oldactions[j]:j+=1
   self.assertEqual(j,len(oldactions),'old action lost '+a['id'])
  (OUT/'original-preservation.json').write_text(json.dumps({'original_inventory':inventory(old['cases']),'additive_expected':additions},indent=2)+'\n')
 def test_every_finite_exit_has_real_engine_assertion(self):
  cases=json.loads((ROOT/'design/g3/x/cases.json').read_text())['cases'];seen=0
  for c in cases:
   if c['id'] in ('X013','X023'):continue # resource/limit termination is not natural exit zero
   for i,a in enumerate(c['actions']):
    if a['op']=='invoke' and a['args']['method']=='await_exit':
     nxt=c['actions'][i+1];self.assertIn(nxt['op'],('collect','observe_peer_completion'));tag=nxt['args']['tag'];self.assertIn({'path':tag+'.physical.exec.Running','comparison':'eq','value':False},c['expected']);self.assertIn({'path':tag+'.physical.exec.ExitCode','comparison':'eq','value':0},c['expected']);seen+=1
  self.assertEqual(seen,18)
 def test_all_generated_scripts_compile(self):
  for name in SCRIPTS:compile(script_bytes(name,{'domain':'task','quota_mode':'bytes'}),name,'exec')
 def test_peer_has_exact_network(self):
  o=Collector.__new__(Collector)
  for name in ('none','original-internal-peer'):
   args=o.options(network=name);self.assertEqual(args.count('--network'),1);self.assertEqual(args[args.index('--network')+1],name)
 def test_original_oom_raw_was_not_failcnt(self):
  samples=json.loads((OLD/'X023-0/active.json').read_text())['physical']['resource_samples'];fact=memory_limit_facts(samples)
  self.assertTrue(fact['observed']);self.assertTrue(any(x['counter']=='oom_kill' and x['count']==1 for x in fact['observations']));self.assertFalse(any(x['counter']=='failcnt' and x['count']>0 for x in fact['observations']));(OUT/'raw-oom-reassessment.json').write_text(json.dumps(fact,indent=2)+'\n')
 def test_zero_counters_not_limit(self):self.assertFalse(memory_limit_facts([{'/cg/memory.failcnt':'0\n','/cg/memory.oom_control':'oom_kill_disable 0\nunder_oom 0\noom_kill 0\n'}])['observed'])
 def test_missing_counters_rejected(self):
  for data in ([],[{}],[{'candidate_reason':'memory'}]):
   with self.assertRaises(EvidenceError):memory_limit_facts(data)
 def test_malformed_counters_rejected(self):
  for data in ([{'memory.failcnt':'-1'}],[{'memory.oom_control':'oom_kill unknown'}],[{'memory.events':'oom_kill 1\noom_kill 1'}]):
   with self.assertRaises(EvidenceError):memory_limit_facts(data)
 def test_ready_exact_frame(self):self.assertEqual(ready_value(b'{"lore_fixture_ready":"heartbeat","value":1}','heartbeat'),1)
 def test_wrong_ready_frames_rejected(self):
  for line in (b'not-json',b'{"lore_fixture_ready":"wrong","value":1}',b'{"lore_fixture_ready":"heartbeat","value":true}',b'{"lore_fixture_ready":"heartbeat","value":1,"extra":0}'):
   with self.assertRaises(EvidenceError):ready_value(line,'heartbeat')
 def call_ready(self,chunks,engine=None,frames=None,arg=None):
  class Channel:
   def call(self,method,args,timeout):
    self_outer.assertEqual(method,'channel_read');self_outer.assertGreater(timeout,0);self_outer.assertLessEqual(timeout,3)
    raw=chunks.pop(0) if chunks else b'';return {'channel':{'data_base64':base64.b64encode(raw).decode(),'eof':not chunks and not raw}}
  class Observe:
   def exec_inspect(self,eid):self_outer.assertEqual(eid,'original-exec');return engine if engine is not None else {'ContainerID':'original-container','Running':True}
  self_outer=self;fx={'request':{},'authority':{},'state':OUT,'cache':OUT};binding={'exec_id':'original-exec','container_id':'original-container'}
  return await_fixture_stdio(Channel(),Observe(),fx,binding,arg or {'marker':'heartbeat','minimum':1},frames or {},time.monotonic()+3)
 def test_fragmented_real_ready(self):self.assertEqual(self.call_ready([b'{"lore_fixture_ready":"heart',b'beat","value":2}\n'])['value'],2)
 def test_ready_stale_skipped_until_original_archive_growth(self):
  r=self.call_ready([b'{"lore_fixture_ready":"heartbeat","value":2}\n',b'{"lore_fixture_ready":"heartbeat","value":4}\n'],frames={'first':{'count':3}},arg={'marker':'heartbeat','greater_than_ref':'first.count'});self.assertEqual((r['threshold'],r['value']),(3,4))
 def test_missing_eof_and_stale_ready_rejected(self):
  for data in ([],[b'{"lore_fixture_ready":"heartbeat","value":0}\n']):
   with self.assertRaises(EvidenceError):self.call_ready(data)
 def test_ready_raw_cap_rejected(self):
  with self.assertRaises(EvidenceError):self.call_ready([b'x'*4097])
 def test_ready_wrong_actual_execution_rejected(self):
  for engine in ({'ContainerID':'other','Running':True},{'ContainerID':'original-container','Running':False}):
   with self.assertRaises(EvidenceError):self.call_ready([b'{"lore_fixture_ready":"heartbeat","value":1}\n'],engine=engine)
 def test_missing_partial_wrong_source_records_rejected(self):
  entry=OUT/'original-entry.py';entry.write_text('pass\n');log=OUT/'source-records.jsonl';event={'kind':'exec','pid':123,'filename':str(entry),'sha256':hashlib.sha256(entry.read_bytes()).hexdigest()}
  self.assertIsNone(source_event(log,123,entry));log.write_text(json.dumps(event));self.assertIsNone(source_event(log,123,entry))
  log.write_text(json.dumps(event)+'\n');self.assertIsNone(source_event(log,124,entry));self.assertEqual(source_event(log,123,entry),event)
  log.write_text(json.dumps({**event,'sha256':'0'*64})+'\n')
  with self.assertRaises(EvidenceError):source_event(log,123,entry)
 def test_actual_adapter_start_exec_sync_and_missing_audit(self):
  ws=OUT/'start-workspace';ws.mkdir();(ws/'sitecustomize.py').write_text(AUDIT);(ws/'entry.py').write_text('import time\nwhile True: time.sleep(1)\n');case=json.loads((ROOT/'design/g3/x/cases.json').read_text())['cases'][0]
  with patch.object(driver,'ROOT',ws),patch.dict(os.environ,{'LORE_X_REQUIRE_SOURCE_AUDIT':'1'}):
   fx=create(OUT/'start-fixture',case,{'domain':'task'});dest=OUT/'start-output';dest.mkdir();adapter=driver.Adapter([sys.executable,'-B','-m','entry'],fx,dest)
   try:
    first=adapter.p.pid;adapter.stop();adapter.start();second=adapter.p.pid
    self.assertNotEqual(first,second);events=[json.loads(x) for x in (dest/'adapter-source-starts.jsonl').read_text().splitlines()];self.assertEqual([x['pid'] for x in events],[first,second]);self.assertTrue(all(x['event']['sha256']==hashlib.sha256((ws/'entry.py').read_bytes()).hexdigest() for x in events))
   finally:adapter.stop()
   badfx=create(OUT/'noaudit-fixture',case,{'domain':'task'});baddest=OUT/'noaudit-output';baddest.mkdir()
   with self.assertRaises(EvidenceError):driver.Adapter([sys.executable,'-B','-S','-m','entry'],badfx,baddest)
   pid=json.loads((baddest/'adapter-processes.jsonl').read_text())['pid']
   with self.assertRaises(ProcessLookupError):os.kill(pid,0)
if __name__=='__main__':unittest.main(verbosity=2)
