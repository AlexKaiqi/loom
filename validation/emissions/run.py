"""Five bounded original R/E/NATS seam groups, independent of candidate status reports."""
import argparse,asyncio,copy,hashlib,importlib,json,os,shutil,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'validation/components/e')]
from fixtures import Source,archive,line,encode,sha,save,PATH,D
from fixture import Fixture
from support import subject,BINARY,BINARY_SHA
import nats
os.environ.update(LORE_EVENT_MODULE='lore_events',LORE_CONTROL_MODULE='lore_control',LORE_R_GATE=str(ROOT/'design/g4/r-gate.json'))

def pubs(f):return [x for x in f.proxy.audit if x.get('direction')=='publish']
def counts(f):return len(pubs(f)),f.sql("SELECT COUNT(*) FROM requests WHERE kind='event'")[0][0]
def frozen_input(ref):return {p.name:p.read_bytes() for p in Path(ref['path']).iterdir()}
def rejection(exc,codes):
 assert getattr(exc,'code',None) in codes,(type(exc).__name__,str(exc),codes)
 return dict(code=exc.code,message=str(exc))
async def bad(call,codes):
 try:await call()
 except Exception as exc:return rejection(exc,codes)
 raise AssertionError('candidate accepted related invalid source/data')
async def submit(cls,f,source):return await cls(f.service,source.resolve).publish(source.effect,source.binding,source.pub)
def capture(out):
 paths=[HERE/'run.py',HERE/'fixtures.py',HERE/'protocol.json',ROOT/'design/g3/system/emit.md',ROOT/'design/g4/r-gate.json']
 for module in ('lore_runtime/emissions.py','lore_runtime/emit_cli.py'): 
  if (ROOT/module).exists():paths.append(ROOT/module)
 for folder in ('lore_control','lore_events','lore_files','validation/components/e'):
  paths.extend((ROOT/folder).glob('*.py'))
 paths.extend(Path(nats.__file__).parent.rglob('*.py'))
 before={str(p):sha(p.read_bytes()) for p in sorted(set(paths))}
 save(out/'fixed-server.json',dict(path=str(BINARY),sha256=sha(BINARY.read_bytes()),expected_sha256=BINARY_SHA))
 for p in paths:
  dst=out/'source'/p.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
 save(out/'source-before.json',before);return before

async def local(cls,cli,f,out):
 root=out/'local';root.mkdir();(root/'goal.txt').write_bytes(b'preserve goal')
 result=cli.emit_local(root,'surface.registered',{'text':'雪'})
 raw=(root/PATH).read_bytes();assert result=={'status':'LOCAL_STAGED','id':1}
 assert raw==line(1,'surface.registered',{'text':'雪'})
 assert sorted(str(p.relative_to(root)) for p in root.rglob('*'))==['.lore',PATH,'goal.txt']
 assert counts(f)==(0,0)
 second=cli.emit_local(root,'done',None);assert second=={'status':'LOCAL_STAGED','id':2}
 before=(root/PATH).read_bytes()
 errors=[]
 for name,payload in [('',{}),('x',{'origin':'runtime'}),('x',float('nan'))]:
  try:cli.emit_local(root,name,payload)
  except (ValueError,OSError) as exc:errors.append(str(exc))
  else:raise AssertionError('CLI accepted bad data')
 assert (root/PATH).read_bytes()==before and len(errors)==3
 # The exact file is also usable as ordinary python -c source, without package imports.
 code=Path(cli.__file__).read_text();process=subprocess.run([sys.executable,'-c',code,'--root',str(root),'cli',json.dumps({'ok':True})],capture_output=True,timeout=5)
 save(out/'cli-process.json',dict(argv_kind='exact standalone helper source',returncode=process.returncode,stdout=process.stdout.decode(),stderr=process.stderr.decode()))
 assert process.returncode==0 and json.loads(process.stdout)=={'status':'LOCAL_STAGED','id':3}
 ref=archive(out/'local-complete.tar',(root/PATH).read_bytes());assert Path(ref['path']).read_bytes().find((root/PATH).read_bytes())>=0
 return dict(local_result=result,errors=errors,full_archive_ref=ref)

async def delta(cls,cli,f,out):
 f.reserve('before');old=await f.prepare('before');oldbytes=frozen_input(old);span=json.loads(oldbytes['manifest.json'])['range']
 assert oldbytes['events.jsonl']==b''
 source=Source(out,'delta',line(1,'historical',{'not':'resent'}),line(1,'historical',{'not':'resent'})+line(2,'surface.registered',{'text':'通知 雪'}))
 first=await submit(cls,f,source);rows=await f.rows();expected=source.expected_raw(2,'surface.registered',{'text':'通知 雪'})
 assert len(first)==1 and first[0]['status']=='CONFIRMED' and len(rows)==1 and rows[0]['data']==expected
 assert rows[0]['sequence']==1 and pubs(f)[0]['binding']['request_id']==source.expected_id(2)
 count=counts(f);again=await submit(cls,f,source);assert again==first and counts(f)==count
 assert frozen_input(await f.service.lookup_input('alice','before'))==oldbytes
 nextseq=span['next_sequence'];f.reserve('after',start=nextseq);new=await f.prepare('after',start=nextseq)
 assert frozen_input(new)['events.jsonl']==expected+b'\n' and frozen_input(old)==oldbytes
 no=Source(out,'no-delta',line(1,'same',None),line(1,'same',None));assert await submit(cls,f,no)==[] and counts(f)==count
 save(out/'delta-original.json',dict(first=first,repeat=again,old=old,new=new,expected_event=expected.decode(),source=source.source))
 return dict(original_id=source.expected_id(2),new_input_ref=new,old_input_unchanged=True,publishes=len(pubs(f)))

async def invalid(cls,cli,f,out):
 errors={};n=0
 mutations=[('task','denied',lambda s:s.source.update(domain='task')),('grant','denied',lambda s:s.source.update(emit_allowed=False)),('namespace','reference_invalid',lambda s:s.source.update(namespace='n2')),('binding','reference_invalid',lambda s:s.source['binding'].update(operation_id='other')),('effect','reference_invalid',lambda s:s.source.update(effect_id='wrong')),('frame','reference_invalid',lambda s:s.source['frame'].update(invocation_id='wrong')),('source-hash','reference_invalid',lambda s:s.source['output_archive_ref'].update(sha256='0'*64)),('checkpoint-generation','reference_invalid',lambda s:s.source['output_archive_ref'].update(object_generation=2)),('publication','reference_invalid',lambda s:s.source['publication_ref']['release'].update(released=False))]
 for name,code,change in mutations:
  n+=1;s=Source(out,'invalid-'+str(n),b'',line(1));s.binding=D(s.binding);s.pub=D(s.pub);s.source=D(s.source);change(s)
  count=counts(f);errors[name]=await bad(lambda:submit(cls,f,s),{code});assert counts(f)==count
 original=line(1,'old',None)
 invalid_data=[('rewrite',original,line(1,'new',None)+line(2),'file'),('delete',original,None,'file'),('torn',b'',line(1)[:-1],'file'),('duplicate',b'',b'{"id":1,"id":1,"name":"x","payload":null}\n','file'),('reserved',b'',line(1,'x',{'origin':'runtime'}),'file'),('ordinal',b'',line(2),'file'),('invalid-second-unicode',b'',line(1)+b'{"id":2,"name":"\\ud800","payload":null}\n','file'),('row-extra',b'',b'{"id":1,"name":"x","payload":null,"origin":"runtime"}\n','file'),('symlink',b'',b'ignored','symlink'),('hardlink',b'',b'ignored','hardlink'),('line-size',b'',line(1,'x','x'*8192),'file'),('total-size',b'',b''.join(line(i,'x','x'*1200) for i in range(1,65)),'file'),('count',b'',b''.join(line(i) for i in range(1,66)),'file'),('new-count',b'',b''.join(line(i) for i in range(1,10)),'file')]
 for name,base,output,kind in invalid_data:
  n+=1;s=Source(out,'invalid-'+str(n),base,output,kind);count=counts(f)
  errors[name]=await bad(lambda:submit(cls,f,s),{'invalid','reference_invalid'});assert counts(f)==count
 # Source fixture remains internally valid, so this must reach actual R same-ID conflict.
 a=Source(out,'same-content-id',b'',line(1,'x','first'));await submit(cls,f,a);count=counts(f)
 old=D(a.source);newref=archive(a.root/'changed-output.tar',line(1,'x','different'))
 a.source['output_archive_ref'].update(path=newref['path'],size=newref['bytes'],sha256=newref['sha256'])
 for key in ('F_query','installation_ref'):a.pub[key]['version_ref']['archive_sha256']=newref['sha256']
 a.source['publication_ref']=a.pub
 errors['same-ID-content']=await bad(lambda:submit(cls,f,a),{'conflict'});assert counts(f)==count
 save(out/'invalid-observations.json',errors);return dict(related_rejections=len(errors),codes=errors)

async def cuts(cls,cli,f,out):
 dropped=Source(out,'lost-ack',b'',line(1,'ack','lost'));f.proxy.drop_next_ack=True
 count=counts(f);first=await submit(cls,f,dropped);assert first[0]['status']=='UNKNOWN'
 assert f.proxy.dropped.is_set() and len(pubs(f))==count[0]+1
 again=await submit(cls,f,dropped);assert again[0]['status']=='CONFIRMED' and len(pubs(f))==count[0]+1
 class Cut(Exception):pass
 async def checkpoint(label,binding):
  assert label=='after_dispatch_before_publish';raise Cut('declared cut after original R mark before PUB')
 paused=Source(out,'issued-cut',b'',line(1,'cut',None));f.service.checkpoint=checkpoint;count=counts(f)
 try:await submit(cls,f,paused)
 except Cut:pass
 else:raise AssertionError('real R dispatch cut not reached')
 f.service.checkpoint=None
 row=f.stores[0].query('runtime',paused.expected_id(1));assert row['phase']=='issued'
 resumed=await submit(cls,f,paused);assert resumed[0]['status']=='UNKNOWN' and len(pubs(f))==count[0]
 accepted=Source(out,'accepted-cut',b'',line(1,'accepted',None));id=accepted.expected_id(1);raw=accepted.expected_raw(1,'accepted',None)
 f.stores[0].accept('alice',dict(id=id,namespace='n1',kind='event',payload=dict(subject=subject('n1',id),event_sha256=sha(raw),event_bytes=len(raw))))
 assert (await f.service.query('alice',id))['status']=='ACCEPTED';count=counts(f)
 done=await submit(cls,f,accepted);assert done[0]['status']=='CONFIRMED' and len(pubs(f))==count[0]+1
 save(out/'delivery-cuts.json',dict(lost_ack=first,queried=again,issued_row=row,issued_result=resumed,accepted_result=done))
 return dict(lost_ack_original_confirmed=True,issued_never_republished=True,accepted_dispatched_once=True)

async def negative(cls,cli,f,out):
 source=Source(out,'capacity',b'',line(1,'capacity','z'*1500));before=counts(f);first=await submit(cls,f,source)
 assert first[0]['status']=='REJECTED' and len(pubs(f))==before[0]+1 and await f.rows()==[]
 again=await submit(cls,f,source);assert again==first and len(pubs(f))==before[0]+1
 actual=[x for x in f.proxy.audit if x.get('direction')=='puback'];assert len(actual)==1
 import base64
 raw=json.loads(base64.b64decode(actual[0]['body_base64']));assert raw['error']['code']==503 or raw['error']['code']==400 or raw['error']['code']==500
 save(out/'negative-actual.json',dict(first=first,repeat=again,puback=actual[0],error=raw))
 return dict(original_negative=first,stored_messages=0,publishes=1)

async def execute(cls,cli,out,result):
 groups=[local,delta,invalid,cuts];f=Fixture(out/'actual-normal')
 try:
  await f.start()
  for index,fn in enumerate(groups):
   record=dict(id=result['case_ids'][index]);result['tests_run']+=1
   try:record.update(status='PASS',observation=await asyncio.wait_for(fn(cls,cli,f,out),12))
   except Exception as exc:record.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
   result['cases'].append(record)
 finally:await f.close()
 f=Fixture(out/'actual-negative',max_bytes=1024)
 try:
  await f.start();result['tests_run']+=1;record=dict(id=result['case_ids'][4])
  try:record.update(status='PASS',observation=await asyncio.wait_for(negative(cls,cli,f,out),12))
  except Exception as exc:record.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
  result['cases'].append(record)
 finally:await f.close()
 result['cleanup']=[json.loads(p.read_text()) for p in out.glob('actual-*/cleanup.json')]
 assert len(result['cleanup'])==2 and all(x=={'errors':[],'nats_reaped':True} for x in result['cleanup'])
 assert sum(len(json.loads((p/'wire-audit.json').read_text())) for p in out.glob('actual-*'))<100

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--batch',required=True);parser.add_argument('--module',default='lore_runtime.emissions');args=parser.parse_args()
 out=HERE/'evidence'/args.batch;out.mkdir(parents=True,exist_ok=False)
 protocol=json.loads((HERE/'protocol.json').read_text());result=dict(status='FAIL',case_ids=[x['id'] for x in protocol['cases']],tests_run=0,cases=[],scope=protocol['scope'],skipped=[])
 before=capture(out);start=time.monotonic()
 try:
  try:
   mod=importlib.import_module(args.module);cls=getattr(mod,'EmitService');cli=importlib.import_module('lore_runtime.emit_cli')
  except (ModuleNotFoundError,AttributeError) as exc:result.update(status='MISSING',error=str(exc));raise SystemExit(2)
  asyncio.run(asyncio.wait_for(execute(cls,cli,out,result),protocol['budget']['total_seconds']))
  result['status']='PASS' if result['tests_run']==5 and all(c['status']=='PASS' for c in result['cases']) else 'FAIL'
 except SystemExit:pass
 except Exception as exc:result.update(error=repr(exc),traceback=traceback.format_exc())
 finally:
  result['elapsed_seconds']=time.monotonic()-start
  result['source_unchanged']=all(Path(p).exists() and sha(Path(p).read_bytes())==h for p,h in before.items())
  result['loaded_sources']={str(Path(m.__file__).resolve()):sha(Path(m.__file__).read_bytes()) for name,m in sys.modules.items() if name.startswith(('lore_runtime.emissions','lore_runtime.emit_cli','lore_control','lore_events','lore_files','nats')) and getattr(m,'__file__',None) and str(m.__file__).endswith('.py')}
  if not result['source_unchanged']:result['status']='FAIL'
  save(out/'result.json',result);print(json.dumps({k:result[k] for k in ['status','tests_run','elapsed_seconds','source_unchanged']}))
 sys.exit(0 if result['status']=='PASS' else 2 if result['status']=='MISSING' else 1)
