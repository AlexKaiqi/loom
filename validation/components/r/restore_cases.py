"""R22 live sequence. Controlled F layout fixture is not an atomic exchange/X-stop proof."""
import copy,json,os,signal,subprocess,sys,time
from pathlib import Path
from restore_fixture import add_ref,check,root_record,tree_digest

def child(t,module,label,action,**extra):
 cfg={'module':module,'db':str(t.db),'authority':t.authority,'refs':t.refs,'refroot':str(t.refroot),'action':action,**extra}
 cp=t.root/(label+'.config.json');cp.write_text(json.dumps(cfg,indent=2))
 env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(Path(__file__).resolve().parents[3]),'PYTHONDONTWRITEBYTECODE':'1'}
 stdout=(t.root/(label+'.stdout')).open('wb');stderr=(t.root/(label+'.stderr')).open('wb')
 p=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('process_worker.py')),str(cp)],env=env,stdout=stdout,stderr=stderr,close_fds=True);stdout.close();stderr.close();return p

def query_child(t,module,label,id):
 p=child(t,module,label,'query',principal='admin',id=id);t.assertEqual(p.wait(timeout=10),0,(t.root/(label+'.stderr')).read_text());return json.loads((t.root/(label+'.stdout')).read_text())

def exercise(t,module):
 old_checker=t.checker
 def checker(ref,purpose,expected=None):
  result=check(ref,purpose,expected,t.refs,t.refroot)
  return old_checker(ref,purpose,expected) if result is None else result
 t.checker=checker;t.store.close();t.store=t.new_store()
 t.result_ready();old_responsibility=t.store.query('alice','op1')
 registrations={'surface':t.register(),'workspace':t.register('w1',t.workspace,kind='workspace')};paths={'surface':t.surface,'workspace':t.workspace};ids={'surface':'s1','workspace':'w1'}
 domains={}
 for domain in ['surface','workspace']:
  rid=ids[domain];(paths[domain]/'content.txt').write_text('current '+domain)
  base=add_ref(t,'rp-base-'+domain,'file_version','F',resource_id=rid,domain=domain)
  version=add_ref(t,'rp-history-'+domain,'file_version','F',resource_id=rid,domain=domain)
  domains[domain]={'action':'restore','resource_id':rid,'binding_revision':registrations[domain]['revision'],'base_ref':base,'version_ref':version,'installation':{'request_id':'rp-install-'+domain,'execution_id':'rp-exec-'+domain,'generation':'rp-gen-'+domain}}
 session=add_ref(t,'rp-session','session','S',operation_id='op1',boundary='tool_feedback_saved',source_result_ref=t.refs['r1'])
 events=add_ref(t,'rp-events','event_cursor','E',namespace='n1',start_sequence=9)
 effect=add_ref(t,'rp-effect','effect','X',namespace='n1',execution_id='earlier-external-effect',count=1)
 environment=add_ref(t,'rp-environment','environment','F',profile='fixed-r-fixture')
 plan={'schema':'lore-restore-plan/v1','domains':domains,'session':{'session_ref':session,'operation_id':'op1','boundary':'tool_feedback_saved','source_result_ref':t.refs['r1']},'event_cursor':{'namespace':'n1','start_sequence':9,'source_ref':events},'pending_refs':[{'owner':'R','id':'op1'}],'effect_refs':[effect],'harness_ref':t.refs['h1'],'environment_ref':environment}
 request={'id':'rp-plan','namespace':'n1','kind':'restore_plan','payload':plan}
 old_bytes={p.name:p.read_bytes() for p in t.refroot.iterdir()};old_roots={k:root_record(v) for k,v in paths.items()}
 # Failures before acceptance must not create a restore responsibility.
 t.expect_error('denied',t.store.accept,'alice',request);t.expect_error('denied',t.store.accept,'eve',request)
 for label,mutate,code in [
  ('missing-domain',lambda p:p['domains'].pop('workspace'),'invalid'),
  ('wrong-version-domain',lambda p:p['domains']['surface'].update(version_ref=domains['workspace']['version_ref']),'reference_invalid'),
  ('missing-session',lambda p:p['session']['session_ref'].update(id='rp-absent'),'reference_invalid'),
  ('wrong-cursor',lambda p:p['event_cursor'].update(start_sequence=10),'reference_invalid'),
  ('missing-pending',lambda p:p.update(pending_refs=[{'owner':'R','id':'not-accepted'}]),'not_found')]:
  bad=copy.deepcopy(request);bad['id']='rp-bad-'+label;mutate(bad['payload']);t.expect_error(code,t.store.accept,'admin',bad)
 t.assertEqual(t.sql("select count(*) from requests where kind='restore_plan'")[0][0],0)
 # Actual committed-accept/lost-ACK cut, then a different process reads original DB.
 t.store.close();ready=t.root/'rp-accept.ready.json';p=child(t,module,'rp-accept-cut','accept',principal='admin',request=request,cut='after_commit_before_reply',cut_id=request['id'],ready=str(ready))
 try:
  deadline=time.monotonic()+10
  while not ready.exists():
   t.assertIsNone(p.poll(),'child exited before registered cut');t.assertLess(time.monotonic(),deadline,'actual cut timeout');time.sleep(.01)
  observed=json.loads(ready.read_text());t.assertEqual(observed['pid'],p.pid);t.assertEqual(observed['record_id'],request['id']);t.assertEqual(observed['label'],'after_commit_before_reply')
  p.send_signal(signal.SIGKILL);t.assertEqual(p.wait(timeout=5),-signal.SIGKILL)
 finally:
  if p.poll() is None:p.kill();p.wait(timeout=5)
 recovered=query_child(t,module,'rp-query-after-ack-loss',request['id']);t.assertEqual(recovered['payload'],plan);t.assertEqual(recovered['phase'],'accepted')
 t.assertEqual(recovered['restore'],{'installations':{},'remaining_install_ids':['rp-install-surface','rp-install-workspace'],'kept':{}})
 t.store=t.new_store();t.store.accept('admin',copy.deepcopy(request));t.assertEqual(t.sql("select count(*) from requests where id='rp-plan'")[0][0],1)
 t.assertIn('rp-plan',[x['id'] for x in t.store.pending()]);claimed=t.store.claim('restore-must-not-drive-harness',100);t.assertTrue(claimed is None or claimed['id']!='rp-plan')
 variants=[lambda p:p['domains']['workspace'].update(action='keep',version_ref=p['domains']['workspace']['base_ref'],installation=None),lambda p:p['session'].update(boundary='answer_saved'),lambda p:p['event_cursor'].update(start_sequence=10),lambda p:p.update(pending_refs=[]),lambda p:p.update(effect_refs=[]),lambda p:p.update(harness_ref=t.refs['h2']),lambda p:p.update(environment_ref=t.refs['f1']),lambda p:p['domains']['surface']['installation'].update(generation='other-generation')]
 for mutate in variants:
  changed=copy.deepcopy(request);mutate(changed['payload']);t.expect_error('conflict',t.store.accept,'admin',changed)
 t.assertEqual(old_roots,{k:root_record(v) for k,v in paths.items()})
 receipts={};staged_refs={}
 for domain in ['surface','workspace']:
  entry=domains[domain];inst=entry['installation'];rid=entry['resource_id'];t.store.acquire(rid,inst['execution_id'],entry['base_ref'])
  stage=t.root/('rp-stage-'+domain);stage.mkdir();(stage/'content.txt').write_text('historical '+domain)
  fields={'restore_plan_id':'rp-plan','request_id':inst['request_id'],'resource_id':rid,'domain':domain,'execution_id':inst['execution_id'],'generation':inst['generation'],'base_ref':entry['base_ref'],'version_ref':entry['version_ref']}
  stop_fields={k:fields[k] for k in ['resource_id','execution_id','generation','base_ref']};stop=add_ref(t,'rp-stop-'+domain,'stopped','X',**stop_fields)
  staged=add_ref(t,'rp-staged-'+domain,'staged','F',**fields,root=root_record(stage),tree_sha256=tree_digest(stage),stopped_ref=stop)
  staged_refs[domain]=staged
  args=['admin',inst['request_id'],rid,inst['execution_id'],entry['binding_revision'],entry['base_ref'],staged]
  if domain=='surface':
   t.expect_error('not_found',t.store.prepare_install,*args,restore_plan_id='absent-plan');t.expect_error('conflict',t.store.prepare_install,*args)
   wrong_stop=add_ref(t,'rp-wrong-generation-stop','stopped','X',**{**stop_fields,'generation':'other-actual-generation'});t.assertTrue(t.checker(wrong_stop,'stopped'))
   wrong_stage=add_ref(t,'rp-wrong-generation-stage','staged','F',**fields,root=root_record(stage),tree_sha256=tree_digest(stage),stopped_ref=wrong_stop)
   t.assertTrue(t.checker(wrong_stage,'staged'));t.expect_error('reference_invalid',t.store.prepare_install,*args[:-1],wrong_stage,restore_plan_id='rp-plan')
  t.store.prepare_install(*args,restore_plan_id='rp-plan');t.store.prepare_install(*args,restore_plan_id='rp-plan')
  t.expect_error('pending_reconcile',t.store.resolve,'admin','n1',rid,'write')
  retired=t.root/('rp-retired-'+domain);paths[domain].rename(retired);stage.rename(paths[domain])
  # Controlled actual two-rename layout is only a fixture for R authority linkage.
  receipt_fields={**fields,'status':'installed_pending_confirmation','current':root_record(paths[domain]),'retired':root_record(retired),'tree_sha256':tree_digest(paths[domain]),'stopped_ref':stop}
  receipt=add_ref(t,'rp-receipt-'+domain,'installation','F',**receipt_fields);t.assertTrue(t.checker(receipt,'installation',fields))
  if domain=='surface':
   wrong=add_ref(t,'rp-wrong-generation-receipt','installation','F',**{**receipt_fields,'generation':'other-actual-generation'});t.assertTrue(t.checker(wrong,'installation'));t.expect_error('reference_invalid',t.store.confirm_install,inst['request_id'],wrong)
   t.assertEqual(t.store.query('admin','rp-plan')['restore']['installations'],{})
  t.store.confirm_install(inst['request_id'],receipt);t.store.confirm_install(inst['request_id'],receipt);receipts[domain]=receipt
  expected={'installations':dict(receipts),'remaining_install_ids':([] if domain=='workspace' else ['rp-install-workspace']),'kept':{}}
  current=t.store.query('admin','rp-plan');t.assertEqual(current['restore'],expected);t.assertEqual(current['payload'],plan)
  t.assertEqual(current['phase'],'confirmed' if domain=='workspace' else 'accepted')
  t.assertEqual(t.sql('select restore_plan_id from installations where request_id=?',(inst['request_id'],)),[('rp-plan',)])
  t.assertEqual(json.loads(t.sql('select installation_ref_json from installations where request_id=?',(inst['request_id'],))[0][0]),receipt)
  t.store.close();t.assertEqual(query_child(t,module,'rp-query-after-'+domain,'rp-plan')['restore'],expected);t.store=t.new_store()
  t.assertEqual('rp-plan' in [x['id'] for x in t.store.pending()],domain!='workspace')
 # Each keep variant fixes the other version and does not invent its installation.
 for kept in ['surface','workspace']:
  one=copy.deepcopy(request);one['id']='rp-keep-'+kept
  for domain in ['surface','workspace']:
   e=one['payload']['domains'][domain];e['binding_revision']=t.store.resolve('admin','n1',e['resource_id'],'read')['revision'];e['base_ref']=domains[domain]['version_ref']
   if domain==kept:e.update(action='keep',version_ref=e['base_ref'],installation=None)
   else:e['installation']['request_id']='rp-keep-'+kept+'-install'
  t.store.accept('admin',one);q=t.store.query('admin',one['id']);t.assertEqual(q['restore']['kept'],{kept:one['payload']['domains'][kept]['version_ref']});t.assertEqual(len(q['restore']['remaining_install_ids']),1);t.assertEqual(q['phase'],'accepted')
  e=one['payload']['domains'][kept];before={k:root_record(v) for k,v in paths.items()};t.expect_error('invalid',t.store.prepare_install,'admin','rp-illegal-keep-'+kept,e['resource_id'],domains[kept]['installation']['execution_id'],e['binding_revision'],e['base_ref'],staged_refs[kept],restore_plan_id=one['id']);t.assertEqual(before,{k:root_record(v) for k,v in paths.items()})
  bad=copy.deepcopy(one);bad['id']+='-bad';bad['payload']['domains'][kept]['version_ref']=domains[kept]['base_ref'];t.expect_error('invalid',t.store.accept,'admin',bad)
 t.assertEqual(t.store.query('alice','op1')['payload'],old_responsibility['payload']);t.assertEqual(t.store.query('alice','op1')['result_ref'],old_responsibility['result_ref']);t.assertIn('op1',[x['id'] for x in t.store.pending()])
 for name,raw in old_bytes.items():t.assertEqual((t.refroot/name).read_bytes(),raw)
 (t.root/'R22-final-original-facts.json').write_text(json.dumps({'plan':request,'actual_installations':receipts,'original_reference_ids':sorted(old_bytes),'original_roots':old_roots},indent=2))
