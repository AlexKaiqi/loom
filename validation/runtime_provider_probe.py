"""Actual R + ProviderBridge, two finite localhost responses; no Engine/real keys."""
import argparse,copy,hashlib,http.server,importlib,json,os,shutil,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def need(v,m):
 if not v:raise AssertionError(m)
def rejected(fn):
 try:fn()
 except Exception as e:return getattr(e,'code',getattr(e,'reason',type(e).__name__))
 raise AssertionError('expected rejection')
def worker(out):
 sys.path.insert(0,str(ROOT));from lore_control import ControlStore
 from lore_provider.request import SHELL
 from lore_session.provider import ProviderBridge
 from lore_runtime.session_plan_files import compact
 Owner=importlib.import_module('lore_runtime.provider_owner').ProviderOwner
 href={'owner':'F','sha256':'a'*64};cap={'owner':'F','sha256':'b'*64}
 c=ControlStore(out/'R.sqlite',{'runtime':{'namespaces':['n'],'roles':['runtime','submit','admin']}},reference_checker=lambda ref,purpose,expected:purpose=='harness' and ref==href)
 calls=[];key_reads=[];callbacks=[];rows=[];owners=[];start=time.monotonic()
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_POST(self):
   raw=self.rfile.read(int(self.headers['Content-Length']));index=len(calls);need(index<2,'HTTP request cap')
   with c._lock:
    matches=[dict(row) for row in c.db.execute("SELECT * FROM requests WHERE kind='provider_transport'") if json.loads(row['payload_json']).get('request_sha256')==sha(raw)]
   need(len(matches)==1 and matches[0]['phase']=='issued','HTTP entered before original R dispatch')
   body=json.dumps(dict(id='response-'+str(index),object='chat.completion',created=0,model='gpt-5.6-terra',choices=[dict(index=0,message=dict(role='assistant',content='original response'),finish_reason='stop')],usage=dict(prompt_tokens=3 if index==0 else 10000,completion_tokens=2,total_tokens=5 if index==0 else 10002))).encode()
   (out/('http-'+str(index)+'-request.body')).write_bytes(raw);(out/('http-'+str(index)+'-response.body')).write_bytes(body)
   calls.append(dict(request_sha256=sha(raw),response_sha256=sha(body),R_request_id=matches[0]['id'],phase=matches[0]['phase'],authorization_correct=self.headers.get('Authorization')=='Bearer public-owner-fixture'))
   self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 server=http.server.HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start()
 endpoint=dict(scheme='http',host='127.0.0.1',port=server.server_port);root=out/'provider'
 budget=dict(max_requests=1,max_input_tokens=1024,max_output_tokens_per_request=32,max_request_body_bytes=1024,max_seconds=15)
 def key():key_reads.append(True);return 'public-owner-fixture'
 def owner(limits=None,deadline=None):
  value=Owner(c,root,endpoint,principal='runtime',budget=limits or budget,credential_provider=key,timeout=2,deadline_provider=deadline);owners.append(value);return value
 def reference(ref,purpose,expected):
  before=(c.db.in_transaction,c.db.total_changes)
  result=any(o.control_reference(ref,purpose,expected) for o in owners)
  after=(c.db.in_transaction,c.db.total_changes);callbacks.append(dict(before=before,after=after,purpose=purpose))
  need(before==after,'reference callback writes or changes transaction');return result or (purpose=='harness' and ref==href)
 c.reference_checker=reference
 def intent(name,response='response'):
  op='op-'+name
  if c.db.execute('SELECT 1 FROM requests WHERE id=?',(op,)).fetchone() is None:
   c.accept('runtime',dict(id=op,namespace='n',kind='invocation',payload=dict(harness_ref=href,capability_ref=cap,source_result_ref=None)))
   claimed=c.claim('worker-'+name,time.monotonic());need(claimed['id']==op,'fixture fair claim order')
  scope=dict(session_id=name,operation_id=op,response_entry_id=response,session_scope=dict(namespace='n',surface_id='surface',session_id=name,session_generation=1),harness_ref=compact(href),capability_ref=compact(cap),input_ref=dict(id='input-'+name,sha256='c'*64),source_result_ref=None)
  effect='s-provider-'+sha(json.dumps([scope['session_scope'],op,response],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
  frame=dict(type='provider.request',session_id=name,operation_id=op,response_entry_id=response,effect_id=effect,payload=dict(systemPrompt='finite original provider-owner fixture',messages=[dict(role='user',content=op)],tools=[SHELL]))
  return scope,frame
 def record(name,fn):
  try:detail=fn();rows.append(dict(id=name,status='PASS',detail=detail))
  except Exception as ex:rows.append(dict(id=name,status='FAIL',error=repr(ex)));raise
 try:
  a=owner();b=owner(dict(budget,max_requests=2));sa,fa=intent('A');sb,fb=intent('B')
  def invalid():
   before=(c.db.total_changes,len(calls),len(key_reads));bad=copy.deepcopy(fa);bad['operation_id']='foreign';reason=rejected(lambda:a.complete(sa,bad));need(before==(c.db.total_changes,len(calls),len(key_reads)),'invalid intent made an effect');return reason
  record('PO01',invalid)
  def cut():
   original=ProviderBridge.complete
   def interrupted(*args):raise RuntimeError('fixture cut after original R dispatch before HTTP')
   ProviderBridge.complete=interrupted
   try:rejected(lambda:b.complete(sb,fb))
   finally:ProviderBridge.complete=original
   need(c.query('runtime',fb['effect_id'])['phase']=='issued' and not calls,'cut did not leave original issued')
   before=c.db.total_changes;result=b.query(fb['effect_id'],sb);need(result['status']=='UNKNOWN' and c.db.total_changes==before and not calls,'unknown query wrote/replayed');return result
  record('PO02',cut)
  def complete():
   value=a.complete(sa,fa);need(value['fresh'] is True and value['status']=='RECEIVED' and value['wire']['accepted'] and len(calls)==1,'other Session unknown blocks or real response lost');need(c.query('runtime',fa['effect_id'])['phase']=='confirmed','transport receipt not confirmed');return value['receipt_ref']
  record('PO03',complete)
  def retry():
   fresh=owner();before=(len(calls),len(key_reads));value=fresh.complete(sa,fa);changes=c.db.total_changes;raw={str(p):(sha(p.read_bytes()),p.stat().st_ino) for p in root.rglob('*') if p.is_file()};again=fresh.query(fa['effect_id'],sa)
   need(value==again and value['fresh'] is False and before==(len(calls),len(key_reads)) and changes==c.db.total_changes and raw=={str(p):(sha(p.read_bytes()),p.stat().st_ino) for p in root.rglob('*') if p.is_file()},'repeat/query rewrote or replayed');return value['status']
  record('PO04',retry)
  def conflicts():
   before=(c.db.total_changes,len(calls),len(key_reads));changed=copy.deepcopy(fa);changed['payload']['systemPrompt']='different full request';rejected(lambda:a.complete(sa,changed));ref=c.query('runtime',fa['effect_id'])['receipt_ref'];expected={k:ref[k] for k in ['request_id','namespace','source','delivery_owner','request_digest']}
   for key in ['namespace','request_digest','sha256']:
    bad=copy.deepcopy(ref);bad[key]='different';need(not a.control_reference(bad,'receipt',expected),'wrong original wrapper admitted')
   need(before==(c.db.total_changes,len(calls),len(key_reads)),'conflict changed state');return 'full frame and wrapper rejected'
  record('PO05',conflicts)
  def preflight():
   before=(len(calls),len(key_reads));sa2,fa2=intent('A','next');rejected(lambda:a.complete(sa2,fa2));sb2,fb2=intent('B','next');rejected(lambda:b.complete(sb2,fb2));sd,fd=intent('D');expired=owner(deadline=lambda scope:time.monotonic()-1);rejected(lambda:expired.complete(sd,fd));large=copy.deepcopy(fd);large['payload']['systemPrompt']='x'*1500;rejected(lambda:a.complete(sd,large));need(before==(len(calls),len(key_reads)),'preflight made HTTP');return 'count, unknown, deadline, encoded body refused'
  record('PO06',preflight)
  def overflow():
   sc,fc=intent('C');limits=dict(budget,max_requests=2);over=owner(limits);reason=rejected(lambda:over.complete(sc,fc));need(reason=='budget_exceeded' and len(calls)==2,'actual usage overflow not recognized')
   before=c.db.total_changes;value=over.query(fc['effect_id'],sc);need(value['status']=='RECEIVED' and value['wire']['normalized']['wire']['raw_usage']['prompt_tokens']==10000 and c.db.total_changes==before,'actual excessive usage not retained')
   sc2,fc2=intent('C','next');rejected(lambda:over.complete(sc2,fc2));need(len(calls)==2,'continued after actual usage exceeded');return value['receipt_ref']
  record('PO07',overflow)
 except Exception:pass
 finally:
  server.shutdown();server.server_close();thread.join(2);save(out/'http.json',calls);save(out/'callbacks.json',callbacks);(out/'R.sql').write_text('\n'.join(c.db.iterdump()));c.close()
 result=dict(status='PASS' if len(rows)==7 and all(x['status']=='PASS' for x in rows) and len(calls)==2 and not thread.is_alive() and time.monotonic()-start<=15 else 'FAIL',cases=rows,HTTP=len(calls),key_reads=len(key_reads),thread_stopped=not thread.is_alive(),seconds=time.monotonic()-start,scope='real R/ProviderBridge localhost only; S pending authority is explicit fixture')
 save(out/'actual.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 1

def main():
 p=argparse.ArgumentParser();p.add_argument('--batch');p.add_argument('--worker',type=Path);a=p.parse_args()
 if a.worker:return worker(a.worker)
 assert a.batch and Path(a.batch).name==a.batch;out=ROOT/'validation/runtime-provider-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
 target=ROOT/'lore_runtime/provider_owner.py'
 if not target.exists():save(out/'result.json',dict(status='MISSING',HTTP=0,cases=[]));print('MISSING/0');return 2
 workspace=out/'workspace';files=[Path(__file__),target,ROOT/'lore_runtime/session_plan_files.py',ROOT/'design/g3/system/provider-owner.md',ROOT/'lore_execution/profile.json']
 for folder in ['lore_control','lore_session','lore_provider','lore_files','lore_execution']:files.extend(sorted((ROOT/folder).glob('*.py')))
 sources=[]
 for source in files:
  dest=workspace/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);sources.append(dict(original=str(source),copy=str(dest),sha256=sha(source.read_bytes())))
 save(out/'sources.json',sources);actual=out/'actual';actual.mkdir()
 cmd=[sys.executable,'-B',str(workspace/Path(__file__).relative_to(ROOT)),'--worker',str(actual)];process=subprocess.run(cmd,cwd=workspace,env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1'),capture_output=True,timeout=20)
 (out/'stdout').write_bytes(process.stdout);(out/'stderr').write_bytes(process.stderr);same=all(sha(Path(v['original']).read_bytes())==v['sha256']==sha(Path(v['copy']).read_bytes()) for v in sources)
 result=dict(status='PASS' if process.returncode==0 and same else 'FAIL',exit_code=process.returncode,source_unchanged=same,source_count=len(sources),sources_sha256=sha((out/'sources.json').read_bytes()));save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
