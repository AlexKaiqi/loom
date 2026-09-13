# Bounded original host-transport extension checks; real localhost HTTP, public dummy token only.
import argparse,hashlib,http.server,json,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from lore_provider import WireClient
from lore_provider.request import SHELL

def run(batch):
 out=ROOT/'validation/components/provider/evidence'/batch;out.mkdir(parents=True,exist_ok=False)
 source=out/'source';source.mkdir();inputs={}
 for p in sorted((ROOT/'lore_provider').glob('*.py')):
  data=p.read_bytes();(source/p.name).write_bytes(data);inputs[str(p)]=hashlib.sha256(data).hexdigest()
 (out/'check.py').write_bytes(Path(__file__).read_bytes())
 scope=dict(session_id='host-test-session',operation_id='host-test-operation',response_entry_id='original-response',**{k:dict(id=k,sha256='a'*64)for k in ('input_ref','harness_ref','capability_ref')})
 intent=dict(binding=scope,model='gpt-5.6-terra',max_completion_tokens=32,context=dict(systemPrompt='public transport fixture',messages=[dict(role='user',content='text only')],tools=[SHELL]))
 body=json.dumps(dict(id='public-response',object='chat.completion',created=0,model='gpt-5.6-terra',choices=[dict(index=0,message=dict(role='assistant',content='Complete fixture.'),finish_reason='stop')],usage=dict(prompt_tokens=3,completion_tokens=2,total_tokens=5))).encode()
 rows=[];records=[];delay=[0]
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   raw=self.rfile.read(int(self.headers['Content-Length']))
   records.append(dict(path=self.path,headers=dict(self.headers),body=raw.decode()))
   (out/'actual-http.json').write_text(json.dumps(records,indent=2))
   time.sleep(delay[0]);self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 server=http.server.HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 endpoint=dict(scheme='http',host='127.0.0.1',port=server.server_port);secret='public-fixture-token-not-a-secret';reads=[]
 def key():reads.append('read');return secret
 try:
  for name,credential,timeout,pause in [('legacy-no-auth',None,2,0),('trusted-auth',key,2,0),('explicit-longer-deadline',key,3,2.2)]:
   start=len(records);before=len(reads);delay[0]=pause;t=time.monotonic()
   try:
    client=WireClient(endpoint,scope,out/name,timeout=timeout,credential_provider=credential)
    value=client.complete(intent);elapsed=time.monotonic()-t
    assert value['accepted'] is True and len(records)==start+1,value
    actual=records[-1];expected=None if credential is None else 'Bearer '+secret
    assert actual['headers'].get('Authorization')==expected and actual['path']=='/v1/chat/completions'
    assert len(reads)-before==(credential is not None)
    assert all(secret.encode()not in p.read_bytes()for p in (out/name).rglob('*')if p.is_file())
    if pause:assert elapsed>=pause and elapsed<timeout
    rows.append(dict(case=name,pass_=True,elapsed=elapsed))
   except Exception as e:rows.append(dict(case=name,pass_=False,error=repr(e)))
  for name in ['invalid-binding-before-key','invalid-header-no-http','over-deadline-cap']:
   start=len(records);before=len(reads)
   try:
    if name=='over-deadline-cap':
     try:WireClient(endpoint,scope,out/name,timeout=61,credential_provider=key)
     except Exception as e:assert getattr(e,'reason',None)=='invalid_endpoint',repr(e)
     else:raise AssertionError('over-cap timeout accepted')
    elif name=='invalid-header-no-http':
     client=WireClient(endpoint,scope,out/name,credential_provider=lambda:'bad\r\nInjected: value')
     try:client.complete(intent)
     except Exception as e:assert getattr(e,'reason',None)=='invalid_credential',repr(e)
     else:raise AssertionError('invalid credential accepted')
    else:
     client=WireClient(endpoint,scope,out/name,credential_provider=key)
     value=client.complete({**intent,'binding':{**scope,'operation_id':'foreign'}})
     assert value.get('reason')=='invalid_request' and not value['accepted']
    assert len(records)==start and len(reads)==before
    rows.append(dict(case=name,pass_=True))
   except Exception as e:rows.append(dict(case=name,pass_=False,error=repr(e)))
 finally:
  server.shutdown();server.server_close();thread.join(3)
 unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in inputs.items())
 report=dict(status='PASS'if all(x['pass_']for x in rows)and unchanged and not thread.is_alive()else 'FAIL',rows=rows,actual_http=len(records),input_sha256=inputs,source_unchanged=unchanged,thread_stopped=not thread.is_alive(),scope='Real localhost public dummy credential only; no real key, proxy, Pi or S claim')
 (out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));return 0 if report['status']=='PASS'else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);raise SystemExit(run(p.parse_args().batch))
