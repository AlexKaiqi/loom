"""Finite real Pi / original wire mechanism probe, independent raw JSONL checks."""
from pathlib import Path
import copy,hashlib,importlib.util,json,os,select,signal,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(sys.argv[1]); OUT.mkdir()
sys.path.insert(0,str(ROOT));from lore_provider import WireClient
from lore_session.provider import ProviderBridge
sys.path.insert(0,str(ROOT/'validation/components/s'));from oracle import pi_jsonl
spec=importlib.util.spec_from_file_location('wire_collector',ROOT/'validation/components/provider/collector.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);Collector=mod.Collector
CASES={c['id']:c for c in json.loads((ROOT/'design/g3/provider/cases.json').read_text())['cases']}
NODE=ROOT.parent/'node/bin/node'; HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def require(ok,message):
 if not ok:raise AssertionError(message)
def source(work):
 files=list((work/'sessions').rglob('*.jsonl'));require(len(files)==1,'one original JSONL');return files[0]
def binding(work):return json.loads((work/'binding.json').read_text())
def pending(work,frame):
 original=source(work);require(Path(frame['original'])==original,'frame substituted original path');data=pi_jsonl(original.read_bytes());b=binding(work);require(data['values']['lore.wire.binding'][b['operation_id']]==b,'original binding mismatch');state=data['values']['pi.op.state'][b['operation_id']];require(state['at']=='assistant.effect_pending' and state['responseEntryId']==frame['response_entry_id'],'not original pending response');return {**b,'response_entry_id':state['responseEntryId']}

def main():
 credential_reads=[]
 def credential():credential_reads.append(1);return 'public-bridge-fixture-token'
 collector=Collector(OUT/'http');report={'scope':'LOCALHOST_WIRE_PUBLIC_PI_PREPARATION_NOT_S_OR_X','runs':[],'checks':[],'http_calls':0};started=time.monotonic();report['bridge_checks']=[];save(OUT/'assessment.json',report)
 def check(name,ok):
  report['checks'].append({'name':name,'pass':bool(ok)});save(OUT/'assessment.json',report);require(ok,name)
 def bytes_inventory(root):
  return {str(p):[p.stat().st_dev,p.stat().st_ino,sha(p)]for p in root.rglob('*')if p.is_file()}if root.exists()else {}
 def bridge_check(name,ok):
  report['bridge_checks'].append({'name':name,'pass':bool(ok)});save(OUT/'assessment.json',report);require(ok,name)
 def rejected(call):
  try:call()
  except Exception as e:return getattr(e,'reason',None)in ('conflict','invalid_request')
  return False
 def pre_controls(bridge,scope,frame,endpoint,model):
  old_http=len(collector.snapshot()['records']);old_keys=len(credential_reads)
  wrong_session=copy.deepcopy(frame);wrong_session['session_id']='another-session'
  wrong_op=copy.deepcopy(frame);wrong_op['operation_id']='another-operation'
  wrong_ref=copy.deepcopy(scope);wrong_ref['input_ref']['sha256']='f'*64
  wrong_tool=copy.deepcopy(frame);wrong_tool['payload']['tools'][0]['description']='Run an ordinary Shell/Python script at runtime (Surface) or workspace; only these targets exist.'
  bridge_check('wrong-session-op-compactref-description-before-credential',all([rejected(lambda:bridge.complete(scope,wrong_session)),rejected(lambda:bridge.complete(scope,wrong_op)),rejected(lambda:bridge.complete(wrong_ref,frame)),rejected(lambda:bridge.complete(scope,wrong_tool))])and len(credential_reads)==old_keys and len(collector.snapshot()['records'])==old_http)
  def fail_credential():raise RuntimeError('public prepared-before-wire fixture failure')
  incomplete=ProviderBridge(OUT/'prepared-without-wire',endpoint,model,credential_provider=fail_credential)
  try:incomplete.complete(scope,frame);raise AssertionError('fixture credential failure absent')
  except Exception as e:require(getattr(e,'reason',None)=='invalid_credential','expected credential failure after original prepared')
  before=bytes_inventory(OUT/'prepared-without-wire');again=ProviderBridge(OUT/'prepared-without-wire',endpoint,model,credential_provider=credential);a=again.complete(scope,frame);b=again.query(frame['effect_id'],scope)
  bridge_check('actual-prepared-without-wire-never-retries',a==b=={'status':'UNKNOWN','effect_id':frame['effect_id'],'fresh':False}and before==bytes_inventory(OUT/'prepared-without-wire')and len(credential_reads)==old_keys and len(collector.snapshot()['records'])==old_http)
 def post_controls(bridge,scope,frame,receipt):
  before=bytes_inventory(OUT/'provider-receipts');old_http=len(collector.snapshot()['records']);old_keys=len(credential_reads)
  repeated=bridge.complete(scope,frame);changed=copy.deepcopy(frame);changed['payload']['systemPrompt']+=' changed'
  source=copy.deepcopy(scope);source['source_result_ref']={'owner':'S','id':'another-original-source'}
  bridge_check('same-id-complete-full-parameter-conflicts-and-exact-query',repeated=={**receipt,'fresh':False}and bridge.query(frame['effect_id'],scope)==repeated and rejected(lambda:bridge.complete(scope,changed))and rejected(lambda:bridge.complete(source,frame))and before==bytes_inventory(OUT/'provider-receipts')and len(credential_reads)==old_keys and len(collector.snapshot()['records'])==old_http)
 def fresh_python_query(wire,label):
  original=bytes_inventory(OUT/'provider-receipts');calls=len(collector.snapshot()['records']);keys=len(credential_reads)
  payload={'root':str(OUT/'provider-receipts'),'endpoint':wire['endpoint'],'model_scope':wire['model_scope'],'binding':wire['bridge_scope'],'effect':wire['receipt']['effect_id']}
  code="import json,sys,os;from lore_session.provider import ProviderBridge;v=json.load(sys.stdin);b=ProviderBridge(v['root'],v['endpoint'],v['model_scope'],credential_provider=lambda:(_ for _ in ()).throw(RuntimeError('query must not read credential')));print(json.dumps({'pid':os.getpid(),'result':b.query(v['effect'],v['binding'])}))"
  child=subprocess.Popen([sys.executable,'-B','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1'})
  stdout,stderr=child.communicate(json.dumps(payload).encode(),timeout=5);(OUT/(label+'.python-query.stdout')).write_bytes(stdout);(OUT/(label+'.python-query.stderr')).write_bytes(stderr);reply=json.loads(stdout)
  bridge_check(label+'-fresh-python-query-original-wire-only',child.returncode==0 and reply['pid']==child.pid and reply['result']=={**wire['receipt'],'fresh':False} and original==bytes_inventory(OUT/'provider-receipts')and len(collector.snapshot()['records'])==calls and len(credential_reads)==keys)
 def run(label,work,mode,responses=(),halt=False):
  if mode!='query':
   work.mkdir();b={'session_id':label+'-session','operation_id':'op-1','input_ref':{'id':'fixed-input','sha256':'1'*64},'harness_ref':{'id':'wire-probe','sha256':'2'*64},'capability_ref':{'id':'fixture-only','sha256':'3'*64}};save(work/'binding.json',b)
  else:pi_jsonl(source(work).read_bytes()) # reject torn source before Pi can repair it
  record={'label':label,'mode':mode,'frames':[],'wires':[],'tools':[]};report['runs'].append(record);save(OUT/'assessment.json',report)
  audit=OUT/(label+'.node-imports.jsonl');argv=[str(NODE),'--import',str(HERE/'node-audit.mjs'),'--import',str(ROOT/'research/repos/pi/node_modules/tsx/dist/loader.mjs'),str(HERE/'probe.mts'),mode,str(work)]
  env={'PATH':str(NODE.parent)+':/usr/bin:/bin','HOME':str(work),'LANG':'C.UTF-8','TSX_TSCONFIG_PATH':str(ROOT/'tsconfig.json'),'LORE_NODE_AUDIT':str(audit),'TSX_DISABLE_CACHE':'1'}
  with (OUT/(label+'.stderr')).open('wb') as stderr:
   p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,cwd=work,env=env,start_new_session=True);record.update(pid=p.pid,argv=argv,actual_exe=str(Path('/proc')/str(p.pid)/'exe'));record['actual_exe_resolved']=str(Path(record['actual_exe']).resolve());require(Path(record['actual_exe_resolved'])==NODE,'actual Node must be copied binary');record['actual_exe_sha256']=sha(Path(record['actual_exe']));deadline=time.monotonic()+10;buf=b'';count=0
   try:
    while True:
     require(time.monotonic()-started<=45 and time.monotonic()<deadline,'preregistered deadline');ready=select.select([p.stdout],[],[],.05)[0]
     if ready:
      chunk=os.read(p.stdout.fileno(),65536)
      if not chunk:break
      buf+=chunk;require(len(buf)<=1048576,'frame limit')
      while b'\n' in buf:
       line,buf=buf.split(b'\n',1);frame=json.loads(line);record['frames'].append(frame)
       with (OUT/(label+'.stdout')).open('ab') as f:f.write(line+b'\n')
       if frame['type']=='provider.request':
        require(mode!='query' and count<len(responses),'unexpected provider call');scope=pending(work,frame);c=CASES[responses[count]];count+=1;raw=(ROOT/c['response']['body_path']).read_bytes();require(hashlib.sha256(raw).hexdigest()==c['response']['sha256'],'original response fixture source');collector.configure(c['response'],raw)
        # Real original wire client receives complete context; no expected injected into it.
        intent={'binding':scope,'model':'gpt-5.6-terra','max_completion_tokens':128,'context':frame['context']}
        session_scope={'namespace':'wire-pi-mechanism','surface_id':'fixture-surface','session_id':scope['session_id'],'session_generation':1}
        model_scope={'model':'gpt-5.6-terra','max_completion_tokens':128,'session_scope':session_scope,**{k:scope[k]for k in ['input_ref','harness_ref','capability_ref']}}
        full_scope={**scope,'session_scope':session_scope,'source_result_ref':None}
        effect='s-provider-'+hashlib.sha256(json.dumps([session_scope,scope['operation_id'],scope['response_entry_id']],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        node_frame={'type':'provider.request','session_id':scope['session_id'],'operation_id':scope['operation_id'],'effect_id':effect,'response_entry_id':scope['response_entry_id'],'payload':frame['context']}
        endpoint={k:collector.endpoint[k] for k in ('scheme','host','port')};bridge=ProviderBridge(OUT/'provider-receipts',endpoint,model_scope,credential_provider=credential)
        if label=='text'and count==1:pre_controls(bridge,full_scope,node_frame,endpoint,model_scope)
        receipt=bridge.complete(full_scope,node_frame);require(receipt['fresh'],'first actual HTTP must be fresh');wire=receipt['wire']
        if label=='text'and count==1:post_controls(bridge,full_scope,node_frame,receipt)
        report['http_calls']+=1;record['wires'].append({'fixture':c['id'],'scope':scope,'intent':intent,'result':wire,'bridge_scope':full_scope,'model_scope':model_scope,'endpoint':endpoint,'receipt':receipt});save(OUT/'assessment.json',report)
        require(wire['accepted']==c['expected']['accepted'],'wire acceptance differs from original fixture')
        if wire['accepted']:require(wire['normalized']==c['expected']['normalized'],'exact complete normalized wire mismatch')
        reply={'reply_to':frame['call_id']}
        if halt or not wire['accepted']:reply['halt']='wire_saved_Pi_pending' if halt else 'invalid_wire_pending'
        else:reply['message']=wire['normalized']['message']
        p.stdin.write(json.dumps(reply,ensure_ascii=False).encode()+b'\n');p.stdin.flush()
       elif frame['type']=='tool.request':
        require(mode!='query','query tool');native=pi_jsonl(source(work).read_bytes());st=native['values']['pi.op.state']['op-1'];calls=st['batch']['calls'];require(st['at']=='tools' and any(c['status']=='effect_pending' and c['resultEntryId']==frame['invocation_id'] for c in calls),'tool must match original pending resultEntryId');a=[e for e in native['entries'] if e.get('message',{}).get('role')=='assistant'][-1]['message'];tc=[c for c in a['content'] if c['type']=='toolCall'];require(len(tc)==1 and tc[0]['id']==frame['tool_call_id'] and tc[0]['arguments']==frame['args'],'original single native call')
        require(frame['args']=={'target':'workspace','script':'printf wire_fixture'},'only fixed harmless fixture shell authorized');command=['/bin/sh','-c',frame['args']['script']];t=subprocess.run(command,cwd=work,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,timeout=2);require(t.returncode==0 and t.stdout==b'wire_fixture','actual fixture stdout');(OUT/(label+'.tool-stdout')).write_bytes(t.stdout);record['tools'].append({'argv':command,'exit':t.returncode,'stdout_sha256':hashlib.sha256(t.stdout).hexdigest(),'invocation_id':frame['invocation_id'],'tool_call_id':frame['tool_call_id']});p.stdin.write(json.dumps({'reply_to':frame['call_id'],'stdout':t.stdout.decode()}).encode()+b'\n');p.stdin.flush()
       elif frame['type']=='probe.error':raise AssertionError(frame['error'])
       save(OUT/'assessment.json',report)
    require(not buf,'truncated control frame');p.wait(timeout=2);record['exit']=p.returncode;require(p.returncode==(17 if halt or (record['wires'] and not record['wires'][-1]['result']['accepted']) else 0),'actual Node exit');require(count==len(responses),'every configured provider fixture actually used')
   finally:
    if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
    record['reaped']=p.poll() is not None;p.stdin.close();p.stdout.close();save(OUT/'assessment.json',report)
  original=source(work);record['original_jsonl']=str(original);record['original_sha256']=sha(original);record['original']=pi_jsonl(original.read_bytes());return record
 try:
  schedule=[('text',['PW01-text']),('native-feedback',['PW02-native','PW16-cached-reasoning']),('two-tools',['PW03-two-tools']),('length',['PW04-length-text']),('fenced-text',['PW11-text-code-fence']),('short-transport',['PW08-short-body']),('service-error',['PW07-service-error']),('wire-saved-before-Pi',['PW01-text'])]
  for name,fixtures in schedule:
   try:
    row=run(name,OUT/name,'drive',fixtures,halt=name=='wire-saved-before-Pi');native=[e for e in row['original']['entries'] if e.get('message',{}).get('role')=='assistant'];successes=[w for w in row['wires'] if w['result']['accepted']]
    if name in ('short-transport','service-error','wire-saved-before-Pi'):
     check(name+'-original-pending-no-assistant',not native and row['original']['values']['pi.op.state']['op-1']['at']=='assistant.effect_pending' and not row['tools'])
    else:
     check(name+'-complete-original-native-message',len(native)==len(successes) and all(e['message']==w['result']['normalized']['message'] for e,w in zip(native,successes)))
     check(name+'-original-response-entry-ids',all(e['id']==w['scope']['response_entry_id'] for e,w in zip(native,successes)))
     check(name+'-actual-tool-count',len(row['tools'])==(1 if name=='native-feedback' else 0))
    if name=='native-feedback':
     actual=json.loads(Path(collector.snapshot()['records'][-1]['body_path']).read_bytes());check('tool-feedback-in-real-second-request',any(m.get('role')=='tool' and m.get('content')=='wire_fixture' and m.get('tool_call_id')=='call-native-1' for m in actual['messages']))
    if name in ('text','wire-saved-before-Pi'):
     before=source(OUT/name).read_bytes();wire_before=[Path(w['result']['artifacts']['response_path']).read_bytes() for w in row['wires']];http_before=len(collector.snapshot()['records']);q=run(name+'-query',OUT/name,'query');final=next(f for f in q['frames'] if f['type']=='result');check(name+'-fresh-query-zero-effects-exact-bytes',final['providerCalls']==final['toolCalls']==0 and final['pid']!=row['pid'] and source(OUT/name).read_bytes()==before and len(collector.snapshot()['records'])==http_before and wire_before==[Path(w['result']['artifacts']['response_path']).read_bytes() for w in row['wires']]);check(name+'-query-result', (final['result'] is None)==(name=='wire-saved-before-Pi'));fresh_python_query(row['wires'][0],name)
   except Exception as error:
    report.setdefault('case_errors',[]).append({'case':name,'error':repr(error)});save(OUT/'assessment.json',report)
  bridge_check('nine-only-fresh-credential-reads-no-candidate-persisted-token',len(credential_reads)==9 and all(b'public-bridge-fixture-token'not in p.read_bytes()for p in (OUT/'provider-receipts').rglob('*')if p.is_file()))
  records=collector.snapshot();check('all-nine-real-localhost-original-requests',len(records['records'])==report['http_calls']==9 and records['max_active']<=2 and all(r['request_complete'] and r['closed'] for r in records['records']));report['http']=records;report['status']='FAIL' if report.get('case_errors') else 'PASS_MECHANISM_PREPARATION_ONLY'
 except Exception as e:report['status']='FAIL';report['error']=repr(e)
 finally:collector.close();report['elapsed_seconds']=time.monotonic()-started;report['collector_exit']=collector.process.exitcode;save(OUT/'assessment.json',report)
 print(json.dumps({k:report.get(k) for k in ('status','error','http_calls','elapsed_seconds')}));return 0 if report['status']=='PASS_MECHANISM_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
