"""Finite real R/F worker delegation cases; no Engine or candidate F changes."""
import argparse,asyncio,copy,hashlib,importlib,json,os,shutil,subprocess,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'validation')]
from file_publication_probe import Fixture, Cut, ident, SOURCE

def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,default=str)+'\n')
def load(p):return json.loads(Path(p).read_bytes())
def need(v,m):
 if not v:raise AssertionError(m)
def reject(fn,codes):
 try:fn()
 except BaseException as e:
  need(getattr(e,'code',None) in codes,'unexpected rejection '+repr(e));return dict(code=e.code,message=str(e))
 raise AssertionError('missing rejection')

class F(Fixture):
 adapter=None
 def open_stores(self):
  from lore_control import ControlStore
  from lore_files import FileStore
  authority={self.principal:dict(namespaces=[self.namespace],roles=['admin','runtime','submit'])}
  self.control=ControlStore(self.root/'R.sqlite',authority,reference_checker=self.rref)
  cls=self.adapter or FileStore
  kwargs={} if self.adapter is None else dict(control=self.control,delegate_timeout=.1 if self.root.name=='FT04' else 5)
  self.files=cls(self.control_dir,self.auth,self.fref,checkpoint=self.checkpoint,**kwargs)
  self.thread_facts=[]
 def checkpoint(self,label,facts):
  self.thread_facts.append(dict(label=label,thread=threading.get_ident(),main=threading.current_thread() is threading.main_thread(),facts=copy.deepcopy(facts)))
  if label=='capture_leases_acquired':
   need(os.readlink('/proc/self/fd/'+str(facts['monitor_fd']))=='anon_inode:inotify','not actual inotify')
   import fcntl
   need(facts['lease_fds'] and all(fcntl.fcntl(fd,fcntl.F_GETLEASE)==fcntl.F_RDLCK for fd in facts['lease_fds']),'actual read lease absent')
   if getattr(self,'slow',False):self.slow=False;time.sleep(.25)
  super().checkpoint(label,facts)
 def auth(self,ref,purpose,context):
  self.thread_facts.append(dict(authority=purpose,thread=threading.get_ident(),main=threading.current_thread() is threading.main_thread()))
  if purpose=='capture':
   with self.control._lock:
    row=self.control.db.execute('SELECT id FROM resources WHERE id=?',(self.resource['id'],)).fetchone()
    return row is not None and ref==self.grant and context['binding']==self.capbinding
  return super().auth(ref,purpose,context)
 def fref(self,ref,purpose,context):
  if purpose=='coordination':return ref==self.coordination and context['binding']==self.capbinding
  return super().fref(ref,purpose,context)
 def capture_setup(self):
  p=self.root/'capture-root';p.mkdir();(p/'doc.txt').write_bytes(b'actual worker capture\n')
  self.capbinding=dict(self.fbinding,path=str(p),root=ident(p));self.coordination=dict(owner='controlled-writer-fixture',binding=self.capbinding)
 def cap(self,id):return self.files.capture(id,self.capbinding,self.coordination)
 def finish(self):
  save(self.root/'threads.json',self.thread_facts);super().finish()

async def run_case(id,out,cls):
 from lore_runtime.file_publication import FilePublication
 F.adapter=cls;f=F(out,FilePublication);f.capture_setup()
 if cls is not None:
  if id=='FT01':f.cap('main-before-bind')
  f.files.bind_loop(asyncio.get_running_loop())
 main=threading.get_ident()
 try:
  if id=='FT00':
   first=await asyncio.to_thread(reject,lambda:f.cap('fresh-worker'),{'UNSUPPORTED'})
   need(f.files.journal.get('fresh-worker') is None,'original failed capture became complete')
   second=await asyncio.to_thread(reject,f.publish,{'UNSUPPORTED'})
   third=await asyncio.to_thread(f.files.query_install,'install');need(third['status']=='unknown' and third['observation_error']=='UNSUPPORTED','original worker query not reproduced')
   actual=f.files.query_install('install');need(actual['status']=='not_installed','main original layout differs')
   return dict(original_capture=first,original_install=second,original_worker_query=third,main_query=actual)
  if id=='FT01':
   captured=await asyncio.to_thread(f.cap,'worker-capture');raw,tree,contents=f.files.versions.load(captured['version_ref']);need(contents['doc.txt']==b'actual worker capture\n','capture bytes differ')
   need(all(x['main'] for x in f.thread_facts if x.get('label')=='capture_leases_acquired'),'capture not main')
   f.thread_facts.clear()
   imported=await asyncio.to_thread(f.files.import_archive,'worker-import',f.fbinding,str(f.originals/'original-checkpoint.tar'),f.source,f.base,'host-v1');need(imported['version_ref']['archive_sha256']==f.output['version_ref']['archive_sha256'],'ordinary import bytes differ')
   need(any(x.get('authority')=='import_archive' and not x['main'] for x in f.thread_facts),'import unnecessarily delegated')
   result=await asyncio.to_thread(f.publish);f.verify_installed(result);oldroots=(ident(f.root/'current'),ident(f.root/'stage'))
   again=await asyncio.to_thread(f.publish);need(again==result and oldroots==(ident(f.root/'current'),ident(f.root/'stage')),'repeat exchanged or changed');f.verify_installed(again)
   def installed_in_transaction():
    with f.control._tx():
     count=len(f.thread_facts);q=f.files.query_install('install');need(len(f.thread_facts)==count,'installed query invoked R callbacks');return q
   iq=await asyncio.to_thread(installed_in_transaction);need(iq==result['F_query'],'installed R transaction query differs')
   from lore_files import FileStore
   need(cls.import_archive is FileStore.import_archive and cls.materialize is FileStore.materialize and cls.read_reference is FileStore.read_reference,'non-window method overridden')
   need(all(x['main'] for x in f.thread_facts if x.get('label') in ('before_exchange','after_exchange_before_record','after_record_before_reply')),'install not main')
   return dict(capture=captured,published=result,repeated=again,exchange_count=f.exchanges,import_on_worker=True)
  if id=='FT02':
   fd=os.open(f.root/'capture-root/doc.txt',os.O_WRONLY)
   try:first=await asyncio.to_thread(reject,lambda:f.cap('held-writer'),{'WRITER_NOT_QUIESCENT'})
   finally:os.close(fd)
   need(f.files.journal.get('held-writer') is None,'writer rejection produced capture');captured=await asyncio.to_thread(f.cap,'held-writer')
   target=next(p for p in (f.root/'current').rglob('*') if p.is_file() and not p.is_symlink());fd=os.open(target,os.O_WRONLY)
   try:second=await asyncio.to_thread(reject,f.publish,{'WRITER_NOT_QUIESCENT'})
   finally:os.close(fd)
   need(f.exchanges==0 and ident(f.root/'current')==f.old_root and ident(f.root/'stage')==f.stage_root,'writer case exchanged roots')
   need(f.sql()['installations'][0]['installation_ref_json'] is None and len(f.sql()['holders'])==1,'writer failure lost responsibility')
   return dict(capture_writer=first,recovered_capture=captured,install_writer=second,original_query=f.files.query_install('install'))
  if id=='FT03':
   def locked_mutations():
    with f.control._tx():
     before=len(f.thread_facts)
     a=reject(lambda:f.cap('locked-capture'),{'UNSUPPORTED'})
     b=reject(lambda:f.files.install('locked-install',{},{}),{'UNSUPPORTED'})
     need(len(f.thread_facts)==before and f.files.journal.get('locked-capture') is None and f.files.journal.get('locked-install') is None,'locked mutation was dispatched')
     return [a,b]
   blocked=await asyncio.to_thread(locked_mutations)
   f.cut='before_exchange'
   try:await asyncio.to_thread(f.publish)
   except Cut:pass
   else:raise AssertionError('original pre-exchange cut missing')
   def locked_query():
    with f.control._tx():
     before=len(f.thread_facts);value=f.files.query_install('install');need(len(f.thread_facts)==before,'query called an authority/checkpoint');return value
   uninstalled=await asyncio.to_thread(locked_query);need(uninstalled['status']=='not_installed' and uninstalled['observation_error'] is None,'transaction query failed')
   # Preserve the original not-installed intent; FT01 covers installed transaction queries.
   return dict(blocked=blocked,original_uninstalled_query=uninstalled,query_no_callbacks=True)
  if id=='FT04':
   unbound=cls(f.root/'unbound-F',f.auth,f.fref,control=f.control)
   missing_loop=await asyncio.to_thread(reject,lambda:unbound.capture('no-loop',f.capbinding,f.coordination),{'UNSUPPORTED'})
   need(unbound.journal.get('no-loop') is None,'unbound worker performed F action')
   original_loop=asyncio.get_running_loop();wrong_bind=await asyncio.to_thread(reject,lambda:f.files.bind_loop(original_loop),{'UNSUPPORTED'})
   observed=[]
   def queued():observed.append(reject(lambda:f.cap('cancelled-before-start'),{'PUBLICATION_UNKNOWN'}))
   thread=threading.Thread(target=queued);thread.start();thread.join(1);need(not thread.is_alive(),'queued timeout did not bound worker')
   await asyncio.sleep(0);need(f.files.journal.get('cancelled-before-start') is None and not any(x.get('label')=='capture_leases_acquired' for x in f.thread_facts),'cancelled queued call executed')
   f.slow=True;before=sum(x.get('label')=='capture_leases_acquired' for x in f.thread_facts)
   error=await asyncio.to_thread(reject,lambda:f.cap('already-running'),{'PUBLICATION_UNKNOWN'})
   original=f.files.journal.get('already-running');need(original is not None and original['state']=='complete','running original operation was lost')
   later=await asyncio.to_thread(f.cap,'already-running');need(later==original['result'],'original lookup changed result');need(sum(x.get('label')=='capture_leases_acquired' for x in f.thread_facts)==before+1,'running original executed twice')
   sentinel=TimeoutError('original F checkpoint timeout exception')
   original_checkpoint=f.files.checkpoint
   def original_failure(label,facts):
    if label=='capture_leases_acquired':raise sentinel
    return original_checkpoint(label,facts)
   f.files.checkpoint=original_failure
   try:
    try:await asyncio.to_thread(f.cap,'original-exception')
    except BaseException as actual:need(actual is sentinel,'original F exception was replaced by delegation timeout')
    else:raise AssertionError('original F exception lost')
   finally:f.files.checkpoint=original_checkpoint
   return dict(unbound=missing_loop,wrong_bind=wrong_bind,queued_timeout=observed,running_timeout=error,original_record=original,same_id=later,capture_count=1,original_exception_preserved=True)
 finally:f.finish()

def worker(out,baseline):
 result=dict(status='FAIL',actual_runs=0,cases=[])
 try:
  if baseline:cls=None
  else:
   try:cls=importlib.import_module('lore_runtime.file_thread').RuntimeFiles
   except ModuleNotFoundError:save(out/'assessment.json',dict(status='MISSING',actual_runs=0,cases=[]));return 2
  async def all_cases():
   for id in (['FT00'] if baseline else ['FT01','FT02','FT03','FT04']):
    row=dict(id=id);result['actual_runs']+=1
    try:row.update(status='PASS',result=await asyncio.wait_for(run_case(id,out/'actual'/id,cls),35))
    except BaseException as e:row.update(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    result['cases'].append(row);save(out/'assessment.json',result)
  asyncio.run(all_cases());result['status']=('BASELINE_FAILURE_REPRODUCED' if baseline else 'PASS_FILE_THREAD_AUTHOR_ONLY') if all(x['status']=='PASS' for x in result['cases']) else 'FAIL'
 except BaseException as e:result.update(error=repr(e),traceback=traceback.format_exc())
 loaded={str(Path(m.__file__).resolve()):sha(Path(m.__file__).read_bytes()) for n,m in sys.modules.items() if n.startswith(('lore_','file_publication_probe')) and getattr(m,'__file__',None) and str(m.__file__).endswith('.py')};result['loaded_sources']=loaded
 save(out/'assessment.json',result);return 0 if result['status']!='FAIL' else 1

def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--worker',action='store_true');p.add_argument('--baseline',action='store_true');a=p.parse_args()
 if a.worker:return worker(Path(a.batch),a.baseline)
 out=ROOT/'validation/file-thread-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);work=out/'workspace';work.mkdir()
 names=['validation/file_thread_probe.py','validation/file_publication_probe.py','design/g3/system/file-thread.md','design/g4/f-gate.json','design/g4/r-gate.json','lore_runtime/file_publication.py']
 if (ROOT/'lore_runtime/file_thread.py').exists():names.append('lore_runtime/file_thread.py')
 for pkg in ['lore_control','lore_files']:names += [str(p.relative_to(ROOT)) for p in (ROOT/pkg).glob('*.py')]
 before={n:sha((ROOT/n).read_bytes()) for n in names}
 for name,h in before.items():p=work/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
 originals=work/'originals';originals.mkdir();old={}
 sourcefiles=[SOURCE/n for n in ['base.json','prepared-source.json','actual-stop.json','original-checkpoint.tar']]+[p for p in (SOURCE/'control/versions.git').rglob('*') if p.is_file()]
 base=load(SOURCE/'base.json');sourcefiles.append(Path(base['bundle']['archive_path']))
 for p in sourcefiles:
  rel=Path('versions.git')/p.relative_to(SOURCE/'control/versions.git') if p.is_relative_to(SOURCE/'control/versions.git') else Path(p.name) if p.parent==SOURCE else Path('base-archive.tar')
  target=originals/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);old[str(p)]=sha(p.read_bytes())
 for gatefile in ['design/g4/f-gate.json','design/g4/r-gate.json']:
  gate=load(ROOT/gatefile);need(gate['stage']=='G4' and gate['status']=='PASS','dependency not approved');need(all(sha(Path(n).read_bytes())==h for n,h in gate['implementation'].items()),'dependency gate changed')
 save(out/'source-before.json',before);save(out/'original-X-source.json',old)
 cmd=[sys.executable,'-B',str(work/'validation/file_thread_probe.py'),'--worker','--batch',str(out)]+(['--baseline'] if a.baseline else [])
 save(out/'command.json',dict(argv=cmd,cwd=str(work)))
 with (out/'stdout').open('wb') as o,(out/'stderr').open('wb') as e:proc=subprocess.run(cmd,cwd=work,env=dict(os.environ,PYTHONPATH=str(work),PYTHONDONTWRITEBYTECODE='1'),stdout=o,stderr=e,timeout=150)
 result=load(out/'assessment.json') if (out/'assessment.json').exists() else dict(status='FAIL',actual_runs=0)
 result.update(exit_code=proc.returncode,source_unchanged=all(sha((ROOT/n).read_bytes())==h for n,h in before.items()),copied_source=all(sha((work/n).read_bytes())==h for n,h in before.items()),original_X_unchanged=all(sha(Path(n).read_bytes())==h for n,h in old.items()))
 bound={str(work/n):h for n,h in before.items()};result['loaded_source_bound']=all(bound.get(n)==h for n,h in result.get('loaded_sources',{}).items())
 if not all(result[n] for n in ['source_unchanged','copied_source','original_X_unchanged','loaded_source_bound']):result['status']='FAIL'
 save(out/'result.json',result);print(json.dumps({k:result.get(k) for k in ['status','actual_runs','exit_code','source_unchanged','copied_source','loaded_source_bound']}));return proc.returncode if result['status']!='FAIL' else 1
if __name__=='__main__':raise SystemExit(main())
