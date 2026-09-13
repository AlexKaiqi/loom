"""Finite real Pi / original wire mechanism probe, independent raw JSONL checks."""
from pathlib import Path
import copy,hashlib,importlib.util,json,os,select,signal,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(sys.argv[1]); OUT.mkdir()
sys.path.insert(0,str(ROOT));from lore_provider import WireClient
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
 collector=Collector(OUT/'http');report={'scope':'LOCALHOST_WIRE_PUBLIC_PI_PREPARATION_NOT_S_OR_X','runs':[],'checks':[],'http_calls':0};started=time.monotonic();save(OUT/'assessment.json',report)
 def check(name,ok):
  report['checks'].append({'name':name,'pass':bool(ok)});save(OUT/'assessment.json',report);require(ok,name)
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
        intent={'binding':scope,'model':'gpt-5.6-terra','max_completion_tokens':128,'context':frame['context']};wire=WireClient({k:collector.endpoint[k] for k in ('scheme','host','port')},scope,OUT/(label+'-wire-'+str(count))).complete(intent);report['http_calls']+=1;record['wires'].append({'fixture':c['id'],'scope':scope,'intent':intent,'result':wire});save(OUT/'assessment.json',report)
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
     before=source(OUT/name).read_bytes();wire_before=[Path(w['result']['artifacts']['response_path']).read_bytes() for w in row['wires']];http_before=len(collector.snapshot()['records']);q=run(name+'-query',OUT/name,'query');final=next(f for f in q['frames'] if f['type']=='result');check(name+'-fresh-query-zero-effects-exact-bytes',final['providerCalls']==final['toolCalls']==0 and final['pid']!=row['pid'] and source(OUT/name).read_bytes()==before and len(collector.snapshot()['records'])==http_before and wire_before==[Path(w['result']['artifacts']['response_path']).read_bytes() for w in row['wires']]);check(name+'-query-result', (final['result'] is None)==(name=='wire-saved-before-Pi'))
   except Exception as error:
    report.setdefault('case_errors',[]).append({'case':name,'error':repr(error)});save(OUT/'assessment.json',report)
  records=collector.snapshot();check('all-nine-real-localhost-original-requests',len(records['records'])==report['http_calls']==9 and records['max_active']<=2 and all(r['request_complete'] and r['closed'] for r in records['records']));report['http']=records;report['status']='FAIL' if report.get('case_errors') else 'PASS_MECHANISM_PREPARATION_ONLY'
 except Exception as e:report['status']='FAIL';report['error']=repr(e)
 finally:collector.close();report['elapsed_seconds']=time.monotonic()-started;report['collector_exit']=collector.process.exitcode;save(OUT/'assessment.json',report)
 print(json.dumps({k:report.get(k) for k in ('status','error','http_calls','elapsed_seconds')}));return 0 if report['status']=='PASS_MECHANISM_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
