"""G3 probes of existing OS/Git/tar facilities. Not a production file component."""
from pathlib import Path
import base64, ctypes, datetime, errno, fcntl, hashlib, json, mmap, os, signal, stat, struct, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'validation/components/f/evidence'/sys.argv[1]
OUT.mkdir(parents=True,exist_ok=False)
STATE=OUT/'fixture'; STATE.mkdir()
ENV={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_AUTHOR_NAME':'F probe','GIT_AUTHOR_EMAIL':'fixture@invalid','GIT_COMMITTER_NAME':'F probe','GIT_COMMITTER_EMAIL':'fixture@invalid'}
record={'scope':'G3 facility feasibility only','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'cases':{},'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((ROOT/'design/g3/f/facility-protocol.json').read_bytes()).hexdigest()}
def command(label,args,stdin=None,check=True):
 p=subprocess.run(args,env=ENV,input=stdin,capture_output=True,timeout=15)
 (OUT/(label+'-stdout.bin')).write_bytes(p.stdout);(OUT/(label+'-stderr.txt')).write_bytes(p.stderr)
 record['commands'].append({'label':label,'argv':[str(x) for x in args],'exit_code':p.returncode})
 if check and p.returncode: raise RuntimeError(label+': '+p.stderr.decode(errors='replace'))
 return p

def observe(root):
 result={};groups={}
 for q in [root]+sorted(root.rglob('*')):
  s=q.lstat(); name=q.relative_to(root).as_posix(); mode=stat.S_IMODE(s.st_mode)
  kind='file' if stat.S_ISREG(s.st_mode) else 'dir' if stat.S_ISDIR(s.st_mode) else 'symlink' if stat.S_ISLNK(s.st_mode) else 'unsupported'
  attrs={k:base64.b64encode(os.getxattr(q,k,follow_symlinks=False)).decode() for k in os.listxattr(q,follow_symlinks=False)}
  e={'kind':kind,'mode':mode,'mtime_ns':s.st_mtime_ns,'uid':s.st_uid,'gid':s.st_gid,'xattrs':attrs}
  if kind=='file':e['bytes_b64']=base64.b64encode(q.read_bytes()).decode();groups.setdefault((s.st_dev,s.st_ino),[]).append(name)
  if kind=='symlink':e['target_b64']=base64.b64encode(os.fsencode(os.readlink(q))).decode()
  result[name]=e
 return {'entries':result,'hardlink_groups':sorted(sorted(x) for x in groups.values() if len(x)>1)}

def archive_probe():
 source=STATE/'source'; restored=STATE/'restored';source.mkdir();restored.mkdir()
 fixtures={'.gitignore':b'ignored-input\n','.gitattributes':b'* export-ignore filter=evil\n','ignored-input':b'NEEDED\x00\xff','template.md':'T0 雪'.encode(),'blocks/goal.md':b'B0','.git/config':b'[filter "evil"]\n clean = false\n','line\nbreak':b'newline name'}
 for name,data in fixtures.items():
  q=source/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
 (source/'empty').mkdir();os.symlink('../template.md',source/'blocks/link');os.link(source/'ignored-input',source/'hardlink')
 for q in [source]+list(source.rglob('*')):
  if not q.is_symlink():q.chmod(0o750 if q.is_dir() else 0o640)
 os.setxattr(source/'template.md','user.lore',b'exact-xattr\x00value')
 # Linux POSIX ACL xattr format: version2 and user_obj/named_user/group_obj/mask/other entries.
 acl=struct.pack('<I',2)+b''.join(struct.pack('<HHI',tag,perm,who) for tag,perm,who in [(1,6,0xffffffff),(2,4,12345),(4,0,0xffffffff),(16,4,0xffffffff),(32,0,0xffffffff)])
 os.setxattr(source/'blocks/goal.md','system.posix_acl_access',acl)
 for q in [source]+list(source.rglob('*')):os.utime(q,ns=(1700000000123456789,1700000000123456789),follow_symlinks=False)
 before=observe(source);(OUT/'source-observation.json').write_text(json.dumps(before,indent=2))
 expected_names={'.','.git','blocks','empty','blocks/link','hardlink',*fixtures.keys()}
 assert set(before['entries'])==expected_names
 assert before['entries']['ignored-input']['bytes_b64']==base64.b64encode(fixtures['ignored-input']).decode()
 assert before['hardlink_groups']==[['hardlink','ignored-input']]
 tar=OUT/'complete.tar'
 command('tar-create',['tar','--create','--format=pax','--numeric-owner','--acls','--xattrs','--xattrs-include=*','--pax-option=delete=atime,delete=ctime','--file',str(tar),'--directory',str(source),'--','.'])
 command('tar-restore',['tar','--extract','--same-permissions','--same-owner','--numeric-owner','--acls','--xattrs','--xattrs-include=*','--file',str(tar),'--directory',str(restored)])
 after=observe(restored);(OUT/'restored-observation.json').write_text(json.dumps(after,indent=2))
 mismatches=[k for k in before['entries'] if before['entries'].get(k)!=after['entries'].get(k)]
 missing=[k for k in before['entries'] if k not in after['entries']]
 bad=json.loads(json.dumps(after));bad['entries'].pop('ignored-input');bad['entries'].pop('empty');bad['entries']['template.md']['mode']=0o644
 record['cases']['FP01']={'exact_equal':before==after,'mismatches':mismatches,'missing':missing,'weakened_sample_rejected':bad!=before,'archive_sha256':hashlib.sha256(tar.read_bytes()).hexdigest(),'entry_count':len(before['entries'])}
 return tar

def git_probe(tar):
 repo=STATE/'versions.git';empty=STATE/'empty-template';empty.mkdir()
 command('git-init',['git','init','--bare','--template='+str(empty),str(repo)])
 def git(label,*args,stdin=None,check=True):return command(label,['git','--git-dir='+str(repo),'-c','core.hooksPath=/dev/null',*args],stdin,check)
 blob=git('git-blob','hash-object','--no-filters','-w','--stdin',stdin=tar.read_bytes()).stdout.strip().decode()
 tree=git('git-tree','mktree',stdin=('100644 blob '+blob+'\tarchive.tar\n').encode()).stdout.strip().decode()
 commit=git('git-commit','commit-tree',tree,'-m','fixed resource version').stdout.strip().decode()
 git('git-root','update-ref','refs/lore/versions/fixture-v1',commit)
 orphan=git('git-orphan','hash-object','--no-filters','-w','--stdin',stdin=b'UNROOTED-NOT-CONFIRMED').stdout.strip().decode()
 git('git-gc','gc','--prune=now')
 recovered=git('git-read','cat-file','blob',commit+':archive.tar').stdout
 missing=git('git-unrooted-check','cat-file','-e',orphan,check=False)
 record['cases']['FP02']={'rooted_commit':commit,'rooted_blob':blob,'archive_preserved':recovered==tar.read_bytes(),'unrooted_absent':missing.returncode!=0,'unrooted_blob':orphan,'managed_filter_executed':(STATE/'filter-sentinel').exists()}

def lease_probe():
 q=STATE/'lease-file';q.write_bytes(b'OLD')
 prior=signal.getsignal(signal.SIGIO);received=[];signal.signal(signal.SIGIO,lambda sig,frame:received.append(sig))
 def try_lease():
  fd=os.open(q,os.O_RDONLY)
  try:
   fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_RDLCK);fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_UNLCK);return {'granted':True}
  except OSError as e:return {'granted':False,'errno':e.errno}
  finally:os.close(fd)
 fdw=os.open(q,os.O_RDWR)
 try:oldfd=try_lease();mm=mmap.mmap(fdw,3,access=mmap.ACCESS_WRITE)
 finally:os.close(fdw)
 try:mapped=try_lease()
 finally:mm.close()
 fd=os.open(q,os.O_RDONLY);fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_RDLCK)
 child=subprocess.Popen([sys.executable,'-B','-c','from pathlib import Path;import sys;Path(sys.argv[1]).write_bytes(b"NEW")',str(q)],env=ENV,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 try:
  end=time.monotonic()+2
  while not received and time.monotonic()<end:time.sleep(.01)
  before={'sigio_count':len(received),'writer_finished':child.poll() is not None,'bytes':q.read_text()}
 finally:fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_UNLCK);os.close(fd)
 stdout,stderr=child.communicate(timeout=5);(OUT/'lease-writer-stdout.bin').write_bytes(stdout);(OUT/'lease-writer-stderr.txt').write_bytes(stderr);signal.signal(signal.SIGIO,prior)
 after_release=q.read_text()
 # Observe real ordinary changes under the kernel interface; not a synthetic freeze claim.
 libc=ctypes.CDLL(None,use_errno=True);libc.inotify_init1.argtypes=[ctypes.c_int];libc.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
 watcher=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC);mask=0x00000002|0x00000004|0x00000008|0x00000040|0x00000080|0x00000100|0x00000200|0x00000400|0x00000800|0x00002000|0x00004000|0x00008000
 if watcher<0:raise OSError(ctypes.get_errno(),'inotify_init1')
 try:
  wd=libc.inotify_add_watch(watcher,os.fsencode(STATE),mask)
  if wd<0:raise OSError(ctypes.get_errno(),'inotify_add_watch')
  q.write_bytes(b'UNCOORDINATED');q.chmod(0o600);q.rename(STATE/'lease-renamed')
  data=os.read(watcher,65536);events=[];pos=0
  while pos<len(data):
   wid,flags,cookie,size=struct.unpack_from('iIII',data,pos);name=data[pos+16:pos+16+size].rstrip(b'\0');events.append({'wd':wid,'mask':flags,'cookie':cookie,'name_b64':base64.b64encode(name).decode()});pos+=16+size
  (OUT/'inotify-raw.bin').write_bytes(data)
 finally:os.close(watcher)
 record['cases']['FP03']={'existing_writer_fd':oldfd,'existing_writable_mmap':mapped,'before_release':before,'writer_exit':child.returncode,'after_release_bytes':after_release,'events':events,'scope':'Only current user-owned regular fixture. No recursive monitor/production coordinator or overflow stress implemented.'}

def exchange_probe():
 a=STATE/'current';b=STATE/'staged';a.mkdir();b.mkdir();(a/'payload').write_text('OLD');(b/'payload').write_text('NEW');fd=os.open(a/'payload',os.O_WRONLY|os.O_APPEND)
 before={'current':a.stat().st_ino,'staged':b.stat().st_ino};libc=ctypes.CDLL(None,use_errno=True);fn=libc.renameat2;fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
 try:
  rc=fn(-100,os.fsencode(a),-100,os.fsencode(b),2)
  if rc:raise OSError(ctypes.get_errno(),'renameat2')
  os.write(fd,b'+OLD_FD')
 finally:os.close(fd)
 after={'current':a.stat().st_ino,'staged':b.stat().st_ino}
 record['cases']['FP04']={'before':before,'after':after,'current_bytes':(a/'payload').read_text(),'retired_bytes':(b/'payload').read_text(),'objects_exchanged':after=={'current':before['staged'],'staged':before['current']},'current_unchanged_by_old_fd':(a/'payload').read_text()=='NEW','old_fd_is_not_revoked':(b/'payload').read_text()=='OLD+OLD_FD','scope':'Primitive supports object replacement; does not prove X revocation or R publication transaction.'}

for name,call in [('archive',archive_probe),('lease',lease_probe),('exchange',exchange_probe)]:
 try:
  value=call()
  if name=='archive':git_probe(value)
 except Exception as e:record['cases']['ERROR_'+name]={'type':type(e).__name__,'message':str(e)}
record['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record['cases'],indent=2))
