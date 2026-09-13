"""R21 live call sequence. File manifest format belongs only to this authority fixture."""
import copy,hashlib,json,os,subprocess,sys
from pathlib import Path
from input_fixture import make_input,check_input_ref

def exercise(t,module):
 reg=t.register();wreg=t.register('w1',t.workspace,kind='workspace')
 selector={'namespace':'n1','source':'alice','start_sequence':1,'filters':{'names':['notice']},'page_size':16,'surface_ref':{'resource_id':'s1','revision':reg['revision'],'version_ref':t.refs['f1']},'previous_session_ref':None,'execution_targets':[{'resource_id':'w1','revision':wreg['revision'],'kind':'workspace'}]}
 request=t.req(id='input-invocation',resource_id='s1',resource_revision=reg['revision'],input_binding=selector,input_ref=None);request['kind']='invocation';t.store.accept('alice',request)
 t.assertIn('input-invocation',[x['id'] for x in t.store.pending()]);t.assertIsNone(t.store.query_input('alice','input-invocation'));t.assertIsNone(t.store.claim('no-input-worker',100))
 for field,value in [('source','bob'),('namespace','n2')]:
  forged=copy.deepcopy(request);forged['id']='forged-selector-'+field;forged['payload']['input_binding'][field]=value;t.expect_error('denied',t.store.accept,'alice',forged)
 plain=t.req(id='plain-no-input');t.store.accept('alice',plain);t.assertEqual(t.store.claim('plain-worker',100)['id'],'plain-no-input')
 ref=make_input(t.root/'input-original','input-invocation',selector);expected={'invocation_id':'input-invocation','binding':selector};t.assertTrue(check_input_ref(ref,expected,t.root))
 t.expect_error('denied',t.store.bind_input,'eve','input-invocation',selector,ref)
 t.expect_error('denied',t.store.bind_input,'alice','input-invocation',selector,ref)
 t.expect_error('not_found',t.store.query_input,'admin','unknown-input')
 t.expect_error('not_found',t.store.bind_input,'admin','missing-invocation',selector,ref)
 missing=copy.deepcopy(ref);missing['path']=str(t.root/'not-a-directory');t.assertFalse(check_input_ref(missing,expected,t.root))
 t.expect_error('reference_invalid',t.store.bind_input,'admin','input-invocation',selector,missing);t.assertEqual(t.sql('select count(*) from inputs')[0][0],0)
 wrong_selector=copy.deepcopy(selector);wrong_selector['filters']={'names':['other-valid-selection']};wrong_ref=make_input(t.root/'input-wrong-association','input-invocation',wrong_selector)
 t.assertTrue(check_input_ref(wrong_ref,None,t.root));t.assertFalse(check_input_ref(wrong_ref,expected,t.root));t.expect_error('reference_invalid',t.store.bind_input,'admin','input-invocation',selector,wrong_ref)
 t.assertEqual(t.sql('select count(*) from inputs')[0][0],0)
 t.store.bind_input('admin','input-invocation',selector,ref);t.store.bind_input('admin','input-invocation',selector,ref)
 original={'invocation_id':'input-invocation','binding':selector,'input_ref':ref};t.assertEqual(t.store.query_input('alice','input-invocation'),original)
 t.expect_error('denied',t.store.query_input,'eve','input-invocation');t.expect_error('denied',t.store.query_input,'bob','input-invocation')
 variants={'namespace':'n2','source':'bob','start_sequence':2,'filters':{'names':['changed']},'page_size':32,'surface_ref':{**selector['surface_ref'],'version_ref':t.refs['f_other']},'previous_session_ref':{'owner':'S','kind':'session','id':'prior-session'},'execution_targets':[{**selector['execution_targets'][0],'revision':wreg['revision']+1}]}
 for field,value in variants.items():
  changed=copy.deepcopy(selector);changed[field]=value;t.expect_error('conflict',t.store.bind_input,'admin','input-invocation',changed,ref)
 alternate=make_input(t.root/'input-alternate','input-invocation',selector,'different-valid-input');t.assertTrue(check_input_ref(alternate,expected,t.root));t.expect_error('conflict',t.store.bind_input,'admin','input-invocation',selector,alternate)
 raw=(t.root/'input-original/events.jsonl').read_bytes();(t.root/'input-original/events.jsonl').write_bytes(b'X'+raw[1:]);t.assertFalse(check_input_ref(ref,expected,t.root))
 t.expect_error('reference_invalid',t.store.query_input,'alice','input-invocation');t.assertEqual(t.sql('select count(*) from inputs')[0][0],1);t.assertIsNone(t.store.claim('corrupt-input-worker',100))
 (t.root/'input-original/events.jsonl').write_bytes(raw);t.assertEqual(t.store.query_input('alice','input-invocation'),original)
 claim=t.store.claim('ready-input-worker',100);t.assertEqual(claim['id'],'input-invocation');t.assertEqual(claim['mode'],'execute')
 t.assertEqual(t.store.query('alice','input-invocation')['payload'],request['payload']);t.assertEqual(t.sql('select invocation_id from inputs'),[('input-invocation',)])
 t.assertEqual(json.loads(t.sql('select binding_json from inputs')[0][0]),selector);t.assertEqual(json.loads(t.sql('select input_ref_json from inputs')[0][0]),ref)
 t.store.close();t.store=t.new_store();t.assertEqual(t.store.query_input('alice','input-invocation'),original)
 cfg={'module':module,'db':str(t.db),'authority':t.authority,'refs':t.refs,'refroot':str(t.refroot),'action':'query_input','principal':'alice','id':'input-invocation'};cp=t.root/'R21-query.config.json';cp.write_text(json.dumps(cfg,indent=2))
 env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(Path(__file__).resolve().parents[3])};p=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('process_worker.py')),str(cp)],env=env,capture_output=True,timeout=10)
 (t.root/'R21-query.stdout').write_bytes(p.stdout);(t.root/'R21-query.stderr').write_bytes(p.stderr);t.assertEqual(p.returncode,0,p.stderr);t.assertEqual(json.loads(p.stdout),original)
