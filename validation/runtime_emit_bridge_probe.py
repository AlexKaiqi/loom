"""Finite independent RA03 and authority route checks; no Engine construction."""
import argparse,asyncio,copy,hashlib,importlib,json,os,shutil,subprocess,sys,threading,time,traceback
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'validation/components/e')]
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def load(p):return json.loads(Path(p).read_bytes())
def need(v,m):
 if not v:raise AssertionError(m)
def rejected(fn,code='invalid'):
 try:fn()
 except Exception as e:
  need(getattr(e,'code',None)==code,'unexpected rejection '+repr(e));return dict(code=e.code,message=str(e))
 raise AssertionError('required rejection missing')
def tree(p):
 p=Path(p);return {str(x.relative_to(p)):sha(x.read_bytes()) for x in p.rglob('*') if x.is_file()} if p.exists() else {}
def routing(out):
 from lore_runtime.bootstrap import _References
 class Owner:
  def __init__(self,name):self.name=name;self.answer=True;self.calls=[];self.throws=False
  def __getattr__(self,method):
   def call(*args):
    self.calls.append(dict(method=method,args=args))
    if self.throws:raise ValueError('specialized authority refused by exception')
    return self.answer
   return call
 host=Owner('host');tools=Owner('tools');pub=Owner('publication');provider=Owner('provider');r=_References(host)
 r.tools,r.publication,r.provider=tools,pub,provider
 routes=[]
 for purpose in ('import_archive','install','materialize'):
  ctx={'request_id':'tool-materialize-original'}
  routes.append(('authorization:'+purpose,tools,'tools',lambda p=purpose:r.authorization({'original':True},p,ctx)))
 routes += [('file:source',tools,'tools',lambda:r.file_reference({},'source',{}))]
 for purpose in ('intent','stop'):routes.append(('file:'+purpose,pub,'publication',lambda p=purpose:r.file_reference({},p,{})))
 routes += [('stop',tools,'tools',lambda:r.stopped({},'stop',{})),('receipt:provider',provider,'provider',lambda:r.control_reference({'delivery_owner':'provider'},'receipt',{})),('receipt:tool',tools,'tools',lambda:r.control_reference({'facility_ref':{'kind':'ordinary_tool'}},'receipt',{}))]
 for purpose in ('staged','stopped','installation','published'):routes.append(('control:'+purpose,pub,'publication',lambda p=purpose:r.control_reference({},p,{})))
 result=[]
 for label,owner,attr,fn in routes:
  h=len(host.calls);n=len(owner.calls);owner.answer=False
  need(fn() is False,label+' refusal fell through');need(len(host.calls)==h and len(owner.calls)==n+1,label+' wrong refusal owner')
  owner.answer=True;need(fn() is True,label+' specialized positive missing');need(len(host.calls)==h,label+' positive fell through')
  setattr(r,attr,None);need(fn() is False,label+' missing owner accepted');need(len(host.calls)==h,label+' missing owner fallback');setattr(r,attr,owner)
  owner.throws=True
  try:result_value=fn();need(result_value is False,label+' exception accepted')
  except ValueError:pass
  finally:owner.throws=False
  need(len(host.calls)==h,label+' exception fell through');result.append(dict(route=label,refusal=True,positive=True,missing=True,exception_no_fallback=True))
 h=len(host.calls);need(r.control_reference({'facility_ref':{'kind':'unknown'}},'receipt',{}) is False,'unknown receipt accepted');need(len(host.calls)==h,'unknown receipt fallback')
 need(r.authorization({},'capture',{}) is True and r.file_reference({},'read',{}) is True and r.control_reference({},'harness',{}) is True,'ordinary host routing lost')
 save(out/'routes.json',dict(routes=result,host_calls=host.calls,tools=tools.calls,publication=pub.calls,provider=provider.calls));return dict(specialized_routes=len(result),unknown_receipt_rejected=True,generic_host_positive=True)

async def physical(out):
 import support
 origin=Path(os.environ['LORE_PROBE_ORIGIN'])
 support.BINARY=origin/'research/.cache/nats-server/nats-server';support.PYTHON=origin/'research/.venvs/runtime-research/bin/python'
 from fixture import Fixture
 from validation.emissions.fixtures import Source,line
 from lore_runtime.runtime import Runtime
 from lore_runtime.emissions import EmitService
 from lore_runtime.event_reader import JetStreamReader
 from lore_execution.journal import Journal
 from lore_runtime.file_thread import RuntimeFiles
 f=Fixture(out/'actual');rt=None;results=[]
 try:
  await f.start();loop=asyncio.get_running_loop();main_thread=threading.get_ident();client=f.service.nc
  rt=object.__new__(Runtime);rt.events=f.service;rt.control=f.stores[0];rt.reader=JetStreamReader(f.server.url)
  rt.files=RuntimeFiles(out/'F',lambda *args:False,lambda *args:False,control=rt.control)
  rt.execution=SimpleNamespace(journal=Journal(out/'journal'));rt.opened=False;rt.closed=False;rt.event_loop=None
  source=Source(out,'worker-source',b'',line(1,'from-worker',{'text':'原事件'}));rt.emissions=EmitService(f.service,source.resolve)
  observations=[];real_publish=rt.emissions.publish
  async def observed_publish(*args):
   observations.append(dict(loop=id(asyncio.get_running_loop()),thread=threading.get_ident(),args=copy.deepcopy(args)))
   return await real_publish(*args)
  rt.emissions.publish=observed_publish
  def count():return dict(pub=len([x for x in f.proxy.audit if x.get('direction')=='publish']),requests=f.sql('SELECT id,phase FROM requests ORDER BY id'),resolves=len(source.calls),inputs=tree(f.root/'inputs'),journal=tree(out/'journal'),files=tree(out/'F'))
  before=count();unopened=await asyncio.to_thread(rejected,lambda:rt._emit_from_worker(source.effect,source.binding,source.pub));need(count()==before,'unopened emitted or wrote')
  await rt.open();need(rt.event_loop is loop and rt.events.nc is client,'open changed original loop/E client')
  need(rt.files._runtime_loop is loop and rt.files._runtime_control is rt.control,'F binding differs from original main loop/R owner')
  before=count();mainloop=rejected(lambda:rt._emit_from_worker(source.effect,source.binding,source.pub));need(count()==before,'main loop emitted or wrote')
  f.reserve('bridge-before');old=await f.prepare('bridge-before');oldbytes=tree(old['path']);need((Path(old['path'])/'events.jsonl').read_bytes()==b'','old input not empty')
  workers=[]
  def call_worker():workers.append(threading.get_ident());return rt._emit_from_worker(source.effect,source.binding,source.pub)
  first=await asyncio.to_thread(call_worker);rows=await f.rows();expected=source.expected_raw(1,'from-worker',{'text':'原事件'})
  need(first[0]['status']=='CONFIRMED' and len(first)==1,'worker not confirmed');need(len(rows)==1 and rows[0]['data']==expected,'independent NATS original differs')
  need(count()['pub']==1,'not exactly one original PUB');again=await asyncio.to_thread(call_worker);need(again==first and count()['pub']==1,'repeat changed/refired original')
  need(all(x['loop']==id(loop) and x['thread']==main_thread and x['args']==[source.effect,source.binding,source.pub] for x in json.loads(json.dumps(observations))),'actual coroutine wrong loop/args')
  need(all(t!=main_thread for t in workers),'caller did not run on worker')
  start=json.loads((Path(old['path'])/'manifest.json').read_bytes())['range']['next_sequence'];f.reserve('bridge-after',start=start);new=await f.prepare('bridge-after',start=start)
  need((Path(new['path'])/'events.jsonl').read_bytes()==expected+b'\n','next E input did not include original event');need(tree(old['path'])==oldbytes,'prior input changed')
  results.append(dict(id='EB02',status='PASS',first=first,repeat=again,original_nats=expected.decode(),old_input=old,next_input=new,worker_threads=workers,loop=id(loop),main_thread=main_thread,publish_observations=observations,original_E_client_retained=rt.events.nc is client,actual_RuntimeFiles_bound_same_loop_and_R=True))
  save(out/'checks.json',results)
  cut=Source(out,'timeout-source',b'',line(1,'timeout',None));rt.emissions=EmitService(f.service,cut.resolve);entered=asyncio.Event();cancelled=asyncio.Event();never=asyncio.Event()
  async def barrier(label,binding):
   need(label=='after_dispatch_before_publish','wrong real checkpoint');save(out/'timeout-barrier.json',dict(label=label,binding=binding));entered.set()
   try:await never.wait()
   finally:cancelled.set()
  f.service.checkpoint=barrier
  original=asyncio.run_coroutine_threadsafe;waits=[]
  class Bounded:
   def __init__(self,future):self.future=future
   def result(self,timeout):waits.append(timeout);return self.future.result(timeout=1)
   def cancel(self):return self.future.cancel()
  def shortened(coro,target):
   future=original(coro,target);return Bounded(future) if target is loop else future
  before_pub=count()['pub'];asyncio.run_coroutine_threadsafe=shortened
  try:
   task=asyncio.create_task(asyncio.to_thread(rejected,lambda:rt._emit_from_worker(cut.effect,cut.binding,cut.pub),'delivery_unknown'))
   await asyncio.wait_for(entered.wait(),2);issued=f.stores[0].query('runtime',cut.expected_id(1));need(issued['phase']=='issued','no actual issued row')
   error=await task;await asyncio.wait_for(cancelled.wait(),2)
  finally:asyncio.run_coroutine_threadsafe=original;f.service.checkpoint=None
  need(waits==[30] and count()['pub']==before_pub,'timeout did not preserve requested bound/original no-PUB')
  queried=await f.service.query('alice',cut.expected_id(1));need(queried['status']=='UNKNOWN','timeout query not UNKNOWN')
  resumed=await asyncio.to_thread(lambda:rt._emit_from_worker(cut.effect,cut.binding,cut.pub));need(resumed[0]['status']=='UNKNOWN' and count()['pub']==before_pub,'unknown retried PUB')
  need(f.stores[0].query('runtime',cut.expected_id(1))['phase']=='issued','unknown responsibility lost')
  results.append(dict(id='EB03',status='PASS',error=error,issued=issued,queried=queried,resubmitted=resumed,original_requested_timeout=waits,actual_wait_override_seconds=1,actual_cancellation_observed=True,pub_count=count()['pub']))
  await rt.close();before=count();closed=await asyncio.to_thread(rejected,lambda:rt._emit_from_worker(source.effect,source.binding,source.pub));need(count()==before,'closed emitted or wrote')
  need(not rt.reader.thread.is_alive() and rt.execution.journal.owner_fd is None and f.service.nc.is_closed,'actual close leaked own handles')
  results.append(dict(id='EB01',status='PASS',unopened=unopened,main_loop=mainloop,closed=closed,no_writes=True,closed_thread_alive=rt.reader.thread.is_alive()))
  return results
 finally:
  if rt is not None and not rt.closed:await rt.close()
  await f.close();save(out/'checks.json',results)

def worker(out):
 result=dict(status='FAIL',actual_runs=0,checks=[])
 try:
  result['checks'].append(dict(id='BR01',status='PASS',result=routing(out)));result['actual_runs']+=1
  result['checks']+=asyncio.run(asyncio.wait_for(physical(out),45));result['actual_runs']+=3
  need(load(out/'actual/cleanup.json')==dict(errors=[],nats_reaped=True),'actual cleanup incomplete')
  result['status']='PASS_FINITE_RA03_ROUTING_ONLY'
 except BaseException as e:result.update(error=repr(e),traceback=traceback.format_exc())
 finally:
  loaded={str(Path(m.__file__).resolve()):sha(Path(m.__file__).read_bytes()) for n,m in sys.modules.items() if n.startswith(('lore_','validation.emissions','fixture','support','receipt_authority','dependency_snapshot')) and getattr(m,'__file__',None) and str(m.__file__).endswith('.py')}
  result['loaded_sources']=loaded;result['all_loaded_candidate_in_copy']=all(Path(p).is_relative_to(ROOT) for p in loaded)
  if not result['all_loaded_candidate_in_copy']:result['status']='FAIL'
  save(out/'assessment.json',result)
 return 0 if result['status'].startswith('PASS_') else 1

def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--worker',action='store_true');a=p.parse_args()
 if a.worker:return worker(Path(a.batch))
 out=ROOT/'validation/runtime-emit-bridge-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);work=out/'workspace';work.mkdir()
 files=[Path(__file__).relative_to(ROOT),Path('validation/emissions/fixtures.py'),Path('design/g3/system/runtime-emit-bridge-checks.md'),Path('design/g3/system/runtime-assembly.md'),Path('design/g3/system/entry-contract.md'),Path('design/g3/system/emit.md'),Path('design/g4/r-gate.json')]
 for package in ('lore_runtime','lore_control','lore_files','lore_events','lore_execution','lore_session','lore_provider','validation/components/e'):
  files += [x.relative_to(ROOT) for x in (ROOT/package).glob('*') if x.is_file() and x.suffix in ('.py','.json') and x.name!='session_sources.py']
 before={str(p):sha((ROOT/p).read_bytes()) for p in sorted(set(files))}
 for p in before:(work/p).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p,work/p)
 gate=load(ROOT/'design/g4/r-gate.json');mapping={name:dict(copy=str(work/Path(name).relative_to(ROOT)),sha256=h) for name,h in gate['implementation'].items()}
 proof=dict(schema='lore.source-equivalence/r-v1',workspace=str(work),gate_copy=str(work/'design/g4/r-gate.json'),gate_original=str(ROOT/'design/g4/r-gate.json'),gate_sha256=before['design/g4/r-gate.json'],source_to_copy=mapping,copied_package_root=str(work/'lore_control'));save(out/'R-source-equivalence.json',proof);save(out/'source-before.json',before)
 binary=ROOT/'research/.cache/nats-server/nats-server';python=ROOT/'research/.venvs/runtime-research/bin/python'
 import nats
 external={str(x):sha(x.read_bytes()) for x in Path(nats.__file__).parent.rglob('*.py')};external[str(binary)]=sha(binary.read_bytes());external[str(python.resolve())]=sha(python.read_bytes());save(out/'external-tools.json',external)
 env=dict(os.environ,PYTHONPATH=str(work),PYTHONDONTWRITEBYTECODE='1',LORE_PROBE_ORIGIN=str(ROOT),LORE_EVENT_MODULE='lore_events',LORE_CONTROL_MODULE='lore_control',LORE_R_GATE=str(work/'design/g4/r-gate.json'),LORE_R_SOURCE_EQUIVALENCE=str(out/'R-source-equivalence.json'),LORE_DEPENDENCY_AUDIT=str(out/'R-loaded.jsonl'))
 command=[str(python),'-B',str(work/'validation/runtime_emit_bridge_probe.py'),'--worker','--batch',str(out)];save(out/'command.json',dict(argv=command,cwd=str(work)))
 with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:proc=subprocess.run(command,cwd=work,env=env,stdout=stdout,stderr=stderr,timeout=90)
 result=load(out/'assessment.json') if (out/'assessment.json').exists() else dict(status='FAIL',actual_runs=0)
 result.update(exit_code=proc.returncode,source_unchanged=all((ROOT/p).is_file() and sha((ROOT/p).read_bytes())==h for p,h in before.items()),copied_source_unchanged=all(sha((work/p).read_bytes())==h for p,h in before.items()),external_tools_unchanged=all(sha(Path(p).read_bytes())==h for p,h in external.items()))
 bound={str((work/p).resolve()):h for p,h in before.items()};result['loaded_source_bound']=all(bound.get(p)==h for p,h in result.get('loaded_sources',{}).items()) and bool(result.get('loaded_sources'))
 if not all(result[k] for k in ('source_unchanged','copied_source_unchanged','external_tools_unchanged','loaded_source_bound')):result['status']='FAIL'
 save(out/'result.json',result);print(json.dumps({k:result.get(k) for k in ('status','actual_runs','exit_code','source_unchanged','copied_source_unchanged','loaded_source_bound','error')}));return 0 if result['status'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
