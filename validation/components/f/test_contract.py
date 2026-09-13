"""Preregistered F component contract tests; candidate imported only by run_contract.py."""
import base64, copy, hashlib, io, json, mmap, os, signal, stat, struct, subprocess, sys, tarfile, time, unittest, zlib
from pathlib import Path
from observer import snapshot, assert_tree, assert_ref, git_archive, assert_bundle
from writer_handshake import attempt_under_lease
FACTORY=None; OUT=None; MODULE=None

def fixture(root):
 root.mkdir()
 fixed={'.gitignore':b'ignored-input\n','.gitattributes':b'* export-ignore filter=evil\n','ignored-input':b'NEEDED\x00\xff','template.md':'T0 雪'.encode(),'blocks/goal.md':b'B0','.git/config':b'[filter "evil"]\n clean = false\n','line\nbreak':b'newline name'}
 for name,data in fixed.items():
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 (root/'empty').mkdir();os.symlink('../template.md',root/'blocks/link');os.link(root/'ignored-input',root/'hardlink')
 for p in [root]+list(root.rglob('*')):
  if not p.is_symlink():p.chmod(0o1750 if p.is_dir() else 0o640)
 (root/'template.md').chmod(0o4750)
 os.setxattr(root/'template.md','user.lore',b'exact-xattr\x00value')
 acl=struct.pack('<I',2)+b''.join(struct.pack('<HHI',tag,perm,who) for tag,perm,who in [(1,6,0xffffffff),(2,4,12345),(4,0,0xffffffff),(16,4,0xffffffff),(32,0,0xffffffff)])
 os.setxattr(root/'blocks/goal.md','system.posix_acl_access',acl)
 for p in [root]+list(root.rglob('*')):os.utime(p,ns=(1700000000123456789,1700000000123456789),follow_symlinks=False)
 obs=snapshot(root)
 assert len(obs['entries'])==13 and obs['hardlink_groups']==[['hardlink','ignored-input']]
 assert (root/'ignored-input').read_bytes()==b'NEEDED\x00\xff'
 return obs

def record_authority(value,purpose,context):
 target=(OUT if OUT is not None else Path(__file__).parent/'evidence')/'authority-calls.jsonl';target.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 try:os.write(fd,(json.dumps({'pid':os.getpid(),'purpose':purpose,'value':value,'context':context},sort_keys=True)+'\n').encode())
 finally:os.close(fd)
def auth(value,purpose,context):
 record_authority(value,purpose,context);return value=={'principal':'fixture-owner','grant':'all'}
def reference(value,purpose,context):
 record_authority(value,purpose,context)
 if not isinstance(value,dict):return False
 if purpose=='stop':return value=={'kind':'stop','execution_id':'E1','generation':1,'authority':'controlled-writer-fixture'}
 return value.get('authority')=='controlled-writer-fixture' and not value.get('invalid')
AUTH={'principal':'fixture-owner','grant':'all'}
COORD={'authority':'controlled-writer-fixture','execution_id':'E1','generation':1}
STOP={'kind':'stop','execution_id':'E1','generation':1,'authority':'controlled-writer-fixture'}

def binding(root,resource='S1',domain='surface'):
 s=root.stat();return {'resource_id':resource,'domain':domain,'path':str(root),'root':{'dev':s.st_dev,'ino':s.st_ino},'revision':1,'authorization':AUTH}

class Contract(unittest.TestCase):
 def setUp(self):
  self.case=OUT/self._testMethodName;self.case.mkdir();self.root=self.case/'ordinary';self.expected=fixture(self.root);self.bound=binding(self.root);self.control=self.case/'control';self.store=FACTORY(self.control,auth,reference)
  (self.case/'expected-before-candidate.json').write_text(json.dumps(self.expected,indent=2))
 def capture(self,name='capture',**kw):
  expected=snapshot(self.root);value=self.store.capture(name,self.bound,COORD,**kw);assert_bundle(value,self.control,expected,'S1','surface');return value
 def fail_code(self,allowed,call):
  try:call()
  except Exception as e:
   self.assertIn(getattr(e,'code',None),allowed,repr(e));return
  self.fail('expected exact component rejection '+str(allowed))
 def materialize(self,result,name='restored'):
  target=self.case/name;ret=self.store.materialize(name,result['version_ref'],str(target),AUTH);self.assertEqual(Path(ret['path']),target);return target
 def read(self,result,path='template.md',**overrides):
  ref={'version_ref':result['version_ref'],'path':path,'kind':'file'};ref.update(overrides);return self.store.read_reference(ref,AUTH)
 def prepared_install(self):
  base=self.capture('base');out=self.materialize(base,'staged');(out/'template.md').write_bytes(b'OUTPUT');b=binding(out);expected_output=snapshot(out);made=self.store.capture('output',b,COORD);assert_bundle(made,self.control,expected_output,'S1','surface');s=out.stat()
  intent={'resource_id':'S1','domain':'surface','binding':self.bound,'staged_path':str(out),'staged_root':{'dev':s.st_dev,'ino':s.st_ino},'version_ref':made['version_ref'],'base_ref':base['version_ref'],'execution_id':'E1','generation':1,'intent_ref':{'authority':'controlled-writer-fixture','request_id':'install-1'}}
  return base,out,made,intent
 def test_F01_ordinary_complete(self):
  plain=self.case/'plain-without-git';plain.mkdir();(plain/'template.md').write_bytes(b'ORDINARY');(plain/'blocks').mkdir();(plain/'blocks/goal.md').write_bytes(b'GOAL');plain_expected=snapshot(plain)
  self.assertFalse((plain/'.git').exists());pv=self.store.capture('without-git',binding(plain,'S0'),COORD);assert_bundle(pv,self.control,plain_expected,'S0','surface');target=self.case/'plain-restored';self.store.materialize('plain-materialize',pv['version_ref'],str(target),AUTH);assert_tree(target,plain_expected);self.assertFalse((plain/'.git').exists())
  got=self.capture();restored=self.materialize(got);assert_tree(restored,self.expected);assert_tree(self.root,self.expected)
  imported=self.store.import_archive('real-archive-import',self.bound,got['archive_path'],COORD,got['version_ref'],'host-v1');assert_bundle(imported,self.control,self.expected,'S1','surface');assert_tree(self.materialize(imported,'imported-restore'),self.expected)
 def test_F02_rooted_gc(self):
  got=self.capture();self.store.retain('active',got['version_ref']);raw=git_archive(self.control,got['version_ref']);self.store.gc();self.assertEqual(git_archive(self.control,got['version_ref']),raw)
  p=subprocess.run(['git','--git-dir='+str(self.control/'versions.git'),'gc','--prune=now'],capture_output=True,timeout=15);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(git_archive(self.control,got['version_ref']),raw)
  self.fail_code({'UNAUTHORIZED'},lambda:self.store.release('active',{'principal':'other'}));self.assertEqual(git_archive(self.control,got['version_ref']),raw)
 def test_F03_historical_exact(self):
  old=self.capture('v1');(self.root/'template.md').write_bytes(b'NEW');new=self.capture('v2');self.assertEqual(self.read(old),'T0 雪'.encode());self.assertEqual(self.read(new),b'NEW')
 def test_F04_reference_authority(self):
  got=self.capture();ref={'version_ref':got['version_ref'],'path':'template.md','kind':'file'}
  self.fail_code({'UNAUTHORIZED'},lambda:self.store.read_reference(ref,{'principal':'other'}))
  for key,val in [('domain','workspace'),('resource_id','OTHER')]:
   bad=copy.deepcopy(ref);bad['version_ref'][key]=val;self.fail_code({'UNAUTHORIZED','VERSION_CORRUPT'},lambda:self.store.read_reference(bad,AUTH))
  self.fail_code({'REFERENCE_TYPE','UNAUTHORIZED'},lambda:self.read(got,'blocks/link'))
 def test_F05_corrupt_missing(self):
  got=self.capture();ref=copy.deepcopy(got);ref['version_ref']['archive_sha256']='0'*64;self.fail_code({'VERSION_CORRUPT'},lambda:self.read(ref))
  missing=copy.deepcopy(got);missing['version_ref']['git_ref']='refs/lore/versions/definitely-missing';self.fail_code({'VERSION_MISSING'},lambda:self.read(missing))
  bad_manifest=copy.deepcopy(got);bad_manifest['version_ref']['manifest_sha256']='0'*64;self.fail_code({'VERSION_CORRUPT'},lambda:self.read(bad_manifest))
  for field in ['archive_path','manifest_path']:
   absent=copy.deepcopy(got);absent[field]=str(self.control/('missing-'+field))
   with self.assertRaises(FileNotFoundError):assert_bundle(absent,self.control,self.expected,'S1','surface')
  raw=git_archive(self.control,got['version_ref']);repo=self.control/'versions.git'
  def git(*args):
   p=subprocess.run(['git','--git-dir='+str(repo),*args],capture_output=True,timeout=15);self.assertEqual(p.returncode,0,p.stderr);return p.stdout
  moid=git('rev-parse',got['version_ref']['git_ref']+':manifest.json').strip().decode();mraw=git('cat-file','blob',moid);mobj=repo/'objects'/moid[:2]/moid[2:];mobj.parent.mkdir(exist_ok=True)
  if mobj.exists():mobj.unlink()
  mobj.write_bytes(b'ACTUALLY-CORRUPTED-MANIFEST');self.fail_code({'VERSION_CORRUPT'},lambda:self.read(got));mobj.write_bytes(zlib.compress(('blob '+str(len(mraw))+'\0').encode()+mraw))
  oid=git('rev-parse',got['version_ref']['git_ref']+':archive.tar').strip().decode();obj=repo/'objects'/oid[:2]/oid[2:];obj.parent.mkdir(exist_ok=True)
  if obj.exists():obj.unlink()
  obj.write_bytes(b'ACTUALLY-CORRUPTED-GIT-OBJECT')
  self.fail_code({'VERSION_CORRUPT'},lambda:self.read(got));obj.write_bytes(zlib.compress(('blob '+str(len(raw))+'\0').encode()+raw))
  for name in git('for-each-ref','--format=%(refname)').decode().splitlines():git('update-ref','-d',name)
  git('reflog','expire','--expire=now','--all');git('gc','--prune=now')
  self.fail_code({'VERSION_MISSING','VERSION_CORRUPT'},lambda:self.read(got))
 def test_F06_unsupported(self):
  os.mkfifo(self.root/'pipe');self.fail_code({'UNSUPPORTED'},lambda:self.capture());(self.root/'pipe').unlink()
  (self.root/'unreadable').write_bytes(b'REQUIRED');(self.root/'unreadable').chmod(0)
  self.fail_code({'UNREADABLE','UNSUPPORTED'},lambda:self.store.capture('locked',self.bound,COORD));self.assertEqual(stat.S_IMODE((self.root/'unreadable').stat().st_mode),0);(self.root/'unreadable').chmod(0o600)
 def test_F07_archive_safety(self):
  canary=self.case/'canary';canary.write_bytes(b'KEEP')
  variants=[('absolute',str(canary),'file'),('traversal','../canary','file'),('duplicate','same','duplicate'),('symlink-parent','alias','symlink-parent'),('hardlink-escape','alias','hardlink'),('device','node','device'),('oversize','large','oversize')]
  for label,name,kind in variants:
   with self.subTest(label=label):
    archive=self.case/(label+'.tar')
    with tarfile.open(archive,'w',format=tarfile.PAX_FORMAT) as t:
     member=tarfile.TarInfo(name)
     if kind=='symlink-parent':member.type=tarfile.SYMTYPE;member.linkname='..';t.addfile(member);member=tarfile.TarInfo('alias/canary')
     if kind=='hardlink':member.type=tarfile.LNKTYPE;member.linkname='../canary';t.addfile(member)
     elif kind=='device':member.type=tarfile.CHRTYPE;member.devmajor=1;member.devminor=3;t.addfile(member)
     else:
      data=b'X'*(1048577 if kind=='oversize' else 1);member.size=len(data);t.addfile(member,io.BytesIO(data))
      if kind=='duplicate':t.addfile(member,io.BytesIO(data))
    self.fail_code({'ARCHIVE_INVALID','LIMIT_EXCEEDED'},lambda:self.store.import_archive(label,self.bound,str(archive),COORD,None,'host-v1'))
    self.assertEqual(canary.read_bytes(),b'KEEP');assert_tree(self.root,self.expected)
 def test_F08_old_writer_fd(self):
  fd=os.open(self.root/'template.md',os.O_RDWR)
  try:self.fail_code({'WRITER_NOT_QUIESCENT'},lambda:self.capture())
  finally:os.close(fd)
  self.capture('after-close')
 def test_F09_old_writable_mmap(self):
  fd=os.open(self.root/'template.md',os.O_RDWR);mm=mmap.mmap(fd,0,access=mmap.ACCESS_WRITE);os.close(fd)
  try:self.fail_code({'WRITER_NOT_QUIESCENT'},lambda:self.capture())
  finally:mm.close()
 def test_F10_external_structure(self):
  observed=[]
  def checkpoint(label,record):
   if label=='capture_leases_acquired':(self.root/'human-new').write_bytes(b'PRESERVE');observed.append(label)
  self.store=FACTORY(self.control,auth,reference,checkpoint=checkpoint)
  self.fail_code({'CHANGE_OBSERVED','BASE_CHANGED'},lambda:self.capture());self.assertEqual(observed,['capture_leases_acquired']);self.assertEqual((self.root/'human-new').read_bytes(),b'PRESERVE')
 def test_F11_observation_loss(self):
  observed=[]
  def checkpoint(label,record):
   if label=='capture_leases_acquired':
    fd=record['monitor_fd'];actual=os.readlink('/proc/self/fd/'+str(fd));self.assertEqual(actual,'anon_inode:inotify')
    (self.case/'actual-monitor.json').write_text(json.dumps({'pid':os.getpid(),'fd':fd,'actual_kernel_object':actual}));os.close(fd);observed.append(label)
  self.store=FACTORY(self.control,auth,reference,checkpoint=checkpoint)
  self.fail_code({'OBSERVATION_LOST'},lambda:self.capture());self.assertEqual(observed,['capture_leases_acquired'])
 def test_F12_base_changed(self):
  base,out,made,intent=self.prepared_install();(self.root/'human').write_bytes(b'KEEP')
  self.fail_code({'BASE_CHANGED'},lambda:self.store.install('install-1',intent,STOP));self.assertEqual((self.root/'human').read_bytes(),b'KEEP');self.assertEqual((out/'template.md').read_bytes(),b'OUTPUT')
 def test_F13_stop_identity(self):
  base,out,made,intent=self.prepared_install();before=snapshot(self.root);staged_before=snapshot(out)
  self.assertTrue(reference(STOP,'stop',None))
  for key,value in [('execution_id','E2'),('generation',2)]:
   wrong=copy.deepcopy(intent);wrong[key]=value;rid='first-install-wrong-'+key;wrong['intent_ref']['request_id']=rid
   self.assertTrue(reference(wrong['intent_ref'],'intent',None))
   self.fail_code({'UNAUTHORIZED','REFERENCE_INVALID','WRITER_NOT_QUIESCENT'},lambda:self.store.install(rid,wrong,STOP))
   assert_tree(self.root,before);assert_tree(out,staged_before)
  for bad in [None,{**STOP,'execution_id':'OTHER'},{**STOP,'generation':2}]:self.fail_code({'UNAUTHORIZED','REFERENCE_INVALID','WRITER_NOT_QUIESCENT'},lambda:self.store.install('install-1',intent,bad))
  assert_tree(self.root,before)
 def test_F14_install_reconcile(self):
  base,out,made,intent=self.prepared_install();old=self.root.stat().st_ino;new=out.stat().st_ino
  self.store.install('install-1',intent,STOP);self.assertEqual(self.root.stat().st_ino,new);self.assertEqual(out.stat().st_ino,old)
  self.store.install('install-1',intent,STOP);self.assertEqual(self.root.stat().st_ino,new)
  q=self.store.query_install('install-1');self.assertEqual(q['original_intent'],intent);self.assertEqual(q['current_root']['ino'],new);self.assertEqual(q['retired_root']['ino'],old);self.assertEqual(q['stopped_ref'],STOP);self.assertIn(q['status'],{'installed_pending_confirmation','confirmed'})
  bad=copy.deepcopy(intent);bad['generation']=2;self.fail_code({'CONFLICT'},lambda:self.store.install('install-1',bad,STOP))
 def test_F15_install_crash(self):
  # Each repetition uses a separate source/store and kills a real candidate process.
  for repeat in range(3):
   if repeat:
    self.case=OUT/self._testMethodName/str(repeat);self.case.mkdir();self.root=self.case/'ordinary';self.expected=fixture(self.root);self.bound=binding(self.root);self.control=self.case/'control';self.store=FACTORY(self.control,auth,reference)
   base,out,made,intent=self.prepared_install();new=out.stat().st_ino;old=self.root.stat().st_ino;inp=self.case/'crash-input.json';inp.write_text(json.dumps({'module':MODULE,'control':str(self.control),'intent':intent}))
   p=subprocess.run([sys.executable,'-B',str(Path(__file__).parent/'crash_child.py'),str(inp)],capture_output=True,timeout=15,env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(Path(__file__).resolve().parents[3])})
   (self.case/'child.stdout').write_bytes(p.stdout);(self.case/'child.stderr').write_bytes(p.stderr);self.assertEqual(p.returncode,-signal.SIGKILL,p.stderr)
   self.store=FACTORY(self.control,auth,reference);q=self.store.query_install('install-1');self.assertEqual(self.root.stat().st_ino,new);self.assertEqual(out.stat().st_ino,old);self.assertEqual(q['current_root']['ino'],new);self.assertEqual(q['original_intent'],intent)
   self.store.install('install-1',intent,STOP);self.assertEqual(self.root.stat().st_ino,new)
 def test_F16_domain_restore(self):
  workspace=self.case/'workspace';workspace.mkdir();(workspace/'code').write_bytes(b'W0');raw=self.case/'session-original';raw.write_bytes(b'SESSION-FACT');w0=snapshot(workspace)
  old=self.capture('surface-old');(self.root/'template.md').write_bytes(b'S1');rest=self.materialize(old,'surface-restore');assert_tree(rest,self.expected);assert_tree(workspace,w0);self.assertEqual(raw.read_bytes(),b'SESSION-FACT')
  wb=binding(workspace,'W1','workspace');wref=self.store.capture('w-old',wb,COORD);assert_bundle(wref,self.control,w0,'W1','workspace');(workspace/'code').write_bytes(b'W1');target=self.case/'workspace-restore';self.store.materialize('w-restore',wref['version_ref'],str(target),AUTH);assert_tree(target,w0);self.assertEqual((self.root/'template.md').read_bytes(),b'S1');self.assertEqual(raw.read_bytes(),b'SESSION-FACT')
 def test_F17_budgets(self):
  small=self.case/'small';small.mkdir();(small/'exact').write_bytes(b'1234');b=binding(small)
  bounded=FACTORY(self.case/'bounded-control',auth,reference,limits={'max_entries':2,'max_logical_bytes':4,'max_archive_bytes':2097152,'window_seconds':10})
  bounded.capture('at-limit',b,COORD);(small/'exact').write_bytes(b'12345');self.fail_code({'LIMIT_EXCEEDED'},lambda:bounded.capture('over-bytes',b,COORD));(small/'exact').write_bytes(b'1234');(small/'extra').write_bytes(b'')
  self.fail_code({'LIMIT_EXCEEDED'},lambda:bounded.capture('over-entries',b,COORD))
  archive_limit=FACTORY(self.case/'archive-limit',auth,reference,limits={'max_entries':64,'max_logical_bytes':1048576,'max_archive_bytes':1,'window_seconds':10})
  self.fail_code({'LIMIT_EXCEEDED'},lambda:archive_limit.capture('over-archive',b,COORD))
  def delay(label,record):
   if label=='capture_leases_acquired':time.sleep(.1)
  timed=FACTORY(self.case/'time-limit',auth,reference,checkpoint=delay,limits={'max_entries':64,'max_logical_bytes':1048576,'max_archive_bytes':2097152,'window_seconds':.05})
  self.fail_code({'LIMIT_EXCEEDED'},lambda:timed.capture('over-time',b,COORD))
 def test_F18_root_identity(self):
  self.root.rename(self.case/'retired');self.root.mkdir();(self.root/'substitute').write_bytes(b'OTHER');self.fail_code({'STALE_BINDING'},lambda:self.capture());self.assertEqual((self.root/'substitute').read_bytes(),b'OTHER')
 def test_F19_new_writer_break(self):
  children=[]
  def checkpoint(label,record):
   if label=='capture_leases_acquired':
    attempt_under_lease(self.root/'template.md',self.case/'writer-handshake',timeout=2,on_started=children.append)
  self.store=FACTORY(self.control,auth,reference,checkpoint=checkpoint)
  try:self.fail_code({'CHANGE_OBSERVED','WRITER_NOT_QUIESCENT'},lambda:self.capture())
  finally:
   for p in children:
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.kill();p.wait()
    stdout,stderr=p.communicate();(self.case/'writer.stdout').write_bytes(stdout);(self.case/'writer.stderr').write_bytes(stderr)
  self.assertEqual(len(children),1);self.assertEqual((self.root/'template.md').read_bytes(),b'AFTER')
