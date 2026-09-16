"""Fixed-response actual assembly only; original real M01 is a separate gate."""
import argparse,asyncio,copy,hashlib,http.server,json,os,sqlite3,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'validation/components/e'))
from support import Server,save,sha

def fact(path):
 p=Path(path);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))

def configuration(out,url,endpoint):
 from lore_runtime.startup_assets import CODE_FILES
 original=ROOT/'validation/session-plan-evidence/context-independent-001/workspace/original-host'
 dm=json.loads((original/'dependencies-manifest.json').read_text())
 principal,ns='operator','assembly'
 for d in ('surface','workspace'):(out/d).mkdir()
 (out/'surface/blocks').mkdir()
 (out/'surface/template.md').write_text('{{blocks/goal.md}}\n{{blocks/notes.md}}\n')
 (out/'surface/blocks/goal.md').write_text('Fixed wiring probe: compute numbers.json into report.json using workspace shell. Then update blocks/notes.md using runtime shell and stage one probe.ready notification with python3 emit.py. In the following input acknowledge the actual notification.\n')
 (out/'surface/blocks/notes.md').write_text('# Notes\n')
 (out/'surface/emit.py').write_bytes((ROOT/'lore_runtime/emit_cli.py').read_bytes())
 (out/'workspace/numbers.json').write_text('[2,3,5]\n')
 host=out/'host';authority={principal:dict(namespaces=[ns],roles=['admin','runtime','submit'])}
 archive=dict(context_tokens=4096,reserve_tokens=3968,tail_reserve_tokens=256,soft_tokens=2048)
 model=dict(id='deepseek-v4-flash',name='deepseek-v4-flash',api='lore-stdio',provider='lore-provider',reasoning=False,input=['text','image'],cost=dict(input=0,output=0,cacheRead=0,cacheWrite=0),contextWindow=archive['context_tokens'],maxTokens=2048)
 startup=dict(principal=principal,namespace=ns,sources={d:dict(path=str(out/d),resource_id='assembly-'+d) for d in ('surface','workspace')},code_sources={n:fact(ROOT/n) for n in CODE_FILES},profile_ref=fact(original/'profile.json'),request_template_ref=fact(original/'request-template.json'),deps_mount=dict(role='dependencies',source=dm['root'],target='/opt',read_only=True,manifest_ref=fact(original/'dependencies-manifest.json'),content_ref=dm['source_ref']),model=model,capability_limits=dict(max_steps=6,archive=archive))
 profile=dict(schema_version=1,namespaces=[ns],stream_max_bytes=8388608,message_limit_bytes=65536,page_size=16,authority=authority,runtime_principal=principal,input_root=str(host/'E-inputs'),stream_prefix='LORE_',subject_prefix='lore',storage='file',discard='new',max_age=0,replicas=1)
 cfg=dict(control_db=str(out/'R.sqlite'),files_dir=str(out/'F'),execution_dir=str(host/'X-state'),session_dir=str(out/'S'),nats_url=url,engine_endpoint='unix:///var/run/docker.sock',authority=authority,worker_id='assembly-worker',event_profile=profile)
 initial=dict(owner='S',namespace=ns,surface_id='assembly-surface',session_id='assembly-session',session_generation=1,confirmation_request_id=None)
 return dict(runtime=cfg,startup_root=str(host),startup=startup,provider=dict(root=str(out/'provider'),endpoint=endpoint,principal=principal,timeout=60),initial_session_ref=initial)

class Wire:
 def __init__(self,out):
  self.out,self.calls=out,[];owner=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    raw=self.rfile.read(int(self.headers['Content-Length']));index=len(owner.calls)
    assert index<3,'fixed wiring HTTP count exhausted'
    owner.calls.append(json.loads(raw));(out/('http-'+str(index)+'-request.body')).write_bytes(raw)
    scripts=[('workspace',"python3 -c 'import json; x=json.load(open(\"numbers.json\")); json.dump({\"sum\":sum(x)},open(\"report.json\",\"w\")); print(sum(x))'"),('runtime',"printf '# Notes\\n[Report](report.json)\\n' > blocks/notes.md; python3 emit.py probe.ready '{\"ready\":true}'")]
    if index<2:
     target,script=scripts[index];message=dict(role='assistant',content=None,tool_calls=[dict(id='call-'+str(index),type='function',function=dict(name='shell',arguments=json.dumps(dict(target=target,script=script))))]);finish='tool_calls'
    else:
     assert 'probe.ready' in raw.decode(),'next model request omitted original event'
     message=dict(role='assistant',content='Observed probe.ready from the next explicit event input.');finish='stop'
    body=json.dumps(dict(id='wire-'+str(index),object='chat.completion',created=0,model='deepseek-v4-flash',choices=[dict(index=0,message=message,finish_reason=finish)],usage=dict(prompt_tokens=(10,280,2980)[index],completion_tokens=20,total_tokens=(30,300,3000)[index]))).encode()
    (out/('http-'+str(index)+'-response.body')).write_bytes(body)
    self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  self.server=http.server.HTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
  self.endpoint=dict(scheme='http',host='127.0.0.1',port=self.server.server_port)
 def close(self):self.server.shutdown();self.thread.join(timeout=3);self.server.server_close()

async def run(out):
 from lore_runtime.bootstrap import assemble
 paths=[p for d in ('lore_runtime','lore_session','lore_execution','lore_files','lore_control','lore_events','lore_provider','harnesses') for p in (ROOT/d).rglob('*') if p.is_file() and p.suffix in ('.py','.mts','.json') and '__pycache__' not in str(p) and '/evidence/' not in str(p)]
 before={str(p):sha(p.read_bytes()) for p in paths};save(out/'source-before.json',before)
 server=Server(out/'nats');wire=Wire(out);rt=None;result=dict(status='FAIL',scope='Actual fixed HTTP assembly, NOT original real M01/historical-link acceptance')
 def checkpoint(label,value):
  with (out/'checkpoints.jsonl').open('a') as f:f.write(json.dumps(dict(label=label,value=value),default=str)+'\n')
 try:
  await server.start();cfg=configuration(out,server.url,wire.endpoint);save(out/'config.json',cfg)
  rt=assemble(cfg,credential_provider=lambda:'public-assembly-fixture',checkpoint=checkpoint)
  rt.session_service.checkpoint=checkpoint
  for spec in rt.registrations_spec:rt.register('operator',**spec)
  refs=rt.initial_refs;selector=dict(namespace='assembly',source='operator',start_sequence=1,filters={},page_size=16,**{k:refs[k] for k in ('surface_ref','previous_session_ref','execution_targets')})
  payload=dict(resource_id='assembly-surface',resource_revision=1,input_ref=None,input_binding=selector,**{k:refs[k] for k in ('harness_ref','capability_ref','session_ref','source_result_ref')})
  request=dict(id='assembly-start',namespace='assembly',kind='invocation',payload=payload)
  rt.start('operator',request);rt.query('operator','assembly-start')
  assert not wire.calls and not list((out/'host/X-state').glob('*/record.json')),'start/query dispatched effects'
  await rt.open();deadline=time.monotonic()+300
  actual=await rt.drive_until('operator','assembly-start',deadline_monotonic=deadline)
  save(out/'runtime-reply.json',actual)
  rows=[dict(r) for r in rt.control.db.execute('SELECT * FROM requests ORDER BY seq')];save(out/'original-R-rows.json',rows)
  result.update(phases=[(r['id'],r['phase']) for r in rows],http_calls=len(wire.calls),elapsed_seconds=300-(deadline-time.monotonic()))
  assert all(r['phase']=='settled' for r in rows if r['kind']=='invocation'),'original Runtime did not settle chain'
  assert len(wire.calls)==3,'missing actual fixed model transport'
  assert json.loads((out/'workspace/report.json').read_text())=={'sum':10},'actual tool report differs'
  assert 'Report' in (out/'surface/blocks/notes.md').read_text(),'actual second-domain tool absent'
  events=[r for r in rows if r['kind']=='event'];assert len(events)==1 and events[0]['phase']=='confirmed','actual E delivery absent'
  nc=await server.connect()
  try:
   js=nc.jetstream();info=await js.stream_info('LORE_assembly');messages=[await js.get_msg('LORE_assembly',seq=i) for i in range(1,info.state.last_seq+1)]
   save(out/'original-nats.json',[dict(sequence=m.seq,subject=m.subject,body=m.data.decode()) for m in messages])
   assert any(json.loads(m.data)['name']=='probe.ready' for m in messages),'original NATS message absent'
  finally:await nc.close()
  records=[json.loads(p.read_text()) for p in (out/'host/X-state').glob('*/record.json')]
  assert records and all(r.get('released') for r in records),'original X responsibility not released'
  absence=[]
  for r in records:
   b=r['binding'];cid=rt.execution.engine.inspect(b['container_id']);volume=rt.execution.engine.call('GET','/volumes/'+b['volume_id'],missing=True)
   absence.append(dict(execution_id=b['execution_id'],container_absent=cid is None,volume_absent=volume is None))
  save(out/'actual-engine-absence.json',absence);assert all(x['container_absent'] and x['volume_absent'] for x in absence),'actual Engine objects remain'
  result['status']='PASS_FIXED_ASSEMBLY_ONLY'
 except Exception as exc:result.update(error=repr(exc),traceback=traceback.format_exc())
 finally:
  if rt is not None:
   try:await rt.close()
   except Exception as exc:result['close_error']=repr(exc)
  wire.close();server.close()
 result['source_unchanged']=before=={str(p):sha(p.read_bytes()) for p in paths}
 save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS_FIXED_ASSEMBLY_ONLY' and result['source_unchanged'] else 1

def main():
 p=argparse.ArgumentParser();p.add_argument('--batch');a=p.parse_args()
 if not a.batch:print(json.dumps(dict(status='MISSING',executed=0,missing='fixed actual owner assembly')));return 2
 # 2026-09-14: F capture windows require xattr support and X bind-mounts readonly
 # sources from daemon-visible paths; honor a volume-backed evidence root mounted
 # at its daemon-visible path (amendment-platform-revision-2026-09-14).
 out_root=Path(os.environ['LORE_RUNTIME_OUT']) if os.environ.get('LORE_RUNTIME_OUT') else ROOT/'validation/runtime-assembly-evidence'
 out=out_root/a.batch;out.mkdir(parents=True,exist_ok=False)
 return asyncio.run(run(out))
if __name__=='__main__':raise SystemExit(main())
