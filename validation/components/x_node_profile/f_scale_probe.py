"""Direct actual F scale probe under its verified source copy; independent filesystem oracle."""
from pathlib import Path
import copy,fcntl,hashlib,io,json,os,resource,stat,subprocess,sys,tarfile,time
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/x'))
from source_closure import verify_f
from lore_files import FileStore,FileError
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False,parents=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def identity(p):s=p.stat();return {'dev':s.st_dev,'ino':s.st_ino}
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def snapshot(root):
 rows={}
 for p in [root,*sorted(root.rglob('*'))]:
  name='.' if p==root else str(p.relative_to(root));s=p.lstat();row={'kind':'dir' if stat.S_ISDIR(s.st_mode) else 'file','mode':stat.S_IMODE(s.st_mode),'mtime_ns':s.st_mtime_ns,'uid':s.st_uid,'gid':s.st_gid,'xattrs':{}}
  assert stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)
  assert not os.listxattr(p)
  if p.is_file():data=p.read_bytes();row.update(size=len(data),sha256=sha(data))
  rows[name]=row
 return rows
class Authority:
 def __init__(self):self.allowed={};self.calls=[]
 def allow(self,kind,purpose,value,context):self.allowed[kind,purpose]=(copy.deepcopy(value),copy.deepcopy(context))
 def check(self,kind,value,purpose,context):
  good=(value,context)==self.allowed.get((kind,purpose));self.calls.append({'kind':kind,'purpose':purpose,'value':value,'context':context,'accepted':good});save(OUT/'authority-calls.json',self.calls);return good
 def auth(self,v,p,c):return self.check('auth',v,p,c)
 def ref(self,v,p,c):return self.check('ref',v,p,c)
def context(op,**kw):return {'schema':'lore-f-authority-context/v1','operation':op,**copy.deepcopy(kw)}
def main():
 equivalence=verify_f(ROOT);save(OUT/'source-equivalence.json',equivalence);source=OUT/'source';source.mkdir();mt=1700000000123456789
 for i in range(64):(source/f'd{i:02d}').mkdir()
 for i in range(512):
  row=(f'original-file-{i:04d}|'.encode()+b'a'*(128-19)) # pad below makes exact128 deterministic bytes
  row=(row+b' '*(128-len(row)))[:128];(source/f'd{i%48:02d}'/f'f{i:04d}.txt').write_bytes(row)
 diff=''.join(('+' if i%2 else '-')+f'line {i:04d} stable original source payload\n' for i in range(4096)).encode();(source/'workspace.diff').write_bytes(diff)
 for p in sorted(source.rglob('*'),key=lambda p:len(p.parts),reverse=True):os.chmod(p,0o750 if p.is_dir() else 0o640);os.utime(p,ns=(mt,mt))
 os.chmod(source,0o750);os.utime(source,ns=(mt,mt));original=snapshot(source);save(OUT/'original-members.json',original);assert len(original)==578 and sum(v['kind']=='file' for v in original.values())==513
 auth=Authority();binding={'resource_id':'xn-input-workspace','domain':'workspace','path':str(source),'root':identity(source),'revision':1,'authorization':{'owner':'XN-controlled-R-fixture','id':'registered-input-scope'}};coord={'owner':'XN-controlled-R-fixture','id':'read-coordination','binding':binding};checks=[];actual=[]
 def allow_capture(rid):
  c=context('capture',request_id=rid,binding=binding,actual_root=binding['root'],profile='host-v1',base_ref=None,coordination=coord);auth.allow('auth','capture',binding['authorization'],c);auth.allow('ref','coordination',coord,c)
 def expect_error(label,code,fn):
  try:fn()
  except FileError as e:actual.append({'case':label,'actual_error':e.code,'message':str(e)});assert e.code==code;return
  raise AssertionError(label+' unexpectedly accepted')
 small=FileStore(OUT/'default-control',auth.auth,auth.ref);allow_capture('default');expect_error('FS01','LIMIT_EXCEEDED',lambda:small.capture('default',binding,coord));assert list((OUT/'default-control/artifacts').iterdir())==[];checks.append({'id':'FS01','pass':True})
 protocol=json.loads((ROOT/'design/g3/x-node-profile/f-scale-protocol.json').read_text());leases=[]
 def checkpoint(label,record):
  if label=='capture_leases_acquired':
   observed={'label':label,'monitor_fd':record['monitor_fd'],'actual_monitor':os.readlink('/proc/self/fd/'+str(record['monitor_fd'])),'leases':[{'fd':fd,'actual_target':os.readlink('/proc/self/fd/'+str(fd)),'actual_lease':fcntl.fcntl(fd,fcntl.F_GETLEASE)} for fd in record['lease_fds']]};leases.append(observed);assert observed['actual_monitor']=='anon_inode:inotify' and len(observed['leases'])==513 and all(x['actual_lease']==fcntl.F_RDLCK and Path(x['actual_target']).is_relative_to(source) for x in observed['leases']);save(OUT/'actual-held-window.json',leases)
 store=FileStore(OUT/'configured-control',auth.auth,auth.ref,checkpoint=checkpoint,limits=protocol['limits']);allow_capture('configured');started=time.monotonic();bundle=store.capture('configured',binding,coord);actual.append({'case':'FS02','capture_seconds':time.monotonic()-started,'bundle':bundle});assert leases;ref=bundle['version_ref'];manifest_raw=Path(bundle['manifest_path']).read_bytes();manifest=json.loads(manifest_raw);assert manifest['tree']['entries']==original;checks.append({'id':'FS02','pass':True});save(OUT/'bundle.json',bundle)
 raw=Path(bundle['archive_path']).read_bytes();assert sha(raw)==ref['archive_sha256'] and sha(manifest_raw)==ref['manifest_sha256'];git=[]
 for member,data in [('archive.tar',raw),('manifest.json',manifest_raw)]:
  cmd=['/usr/bin/git','--git-dir='+str(OUT/'configured-control/versions.git'),'cat-file','blob',ref['git_ref']+':'+member];p=subprocess.run(cmd,capture_output=True,env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'});(OUT/('git-'+member)).write_bytes(p.stdout);git.append({'argv':cmd,'exit':p.returncode,'stderr':p.stderr.decode(),'sha256':sha(p.stdout)});assert p.returncode==0 and p.stdout==data
 save(OUT/'independent-git-read.json',git)
 with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
  members={m.name:m for m in tar.getmembers()};assert set(members)==set(original)
  for name,row in original.items():
   m=members[name];assert m.isdir() if row['kind']=='dir' else m.isfile()
   if row['kind']=='file':assert tar.extractfile(m).read()==(source/name).read_bytes()
 target=OUT/'materialized';grant={'owner':'XN-controlled-R-fixture','id':'exact-materialize-scope'}
 def allow_materialize(rid,path,version):auth.allow('auth','materialize',grant,context('materialize',request_id=rid,version_ref=version,target_path=str(path),target_parent={'path':str(path.parent),'root':identity(path.parent)},profile='host-v1'))
 allow_materialize('materialize',target,ref);materialized=store.materialize('materialize',ref,str(target),grant);assert snapshot(target)==original;save(OUT/'materialized.json',materialized);checks.append({'id':'FS03','pass':True,'actual_archive_bytes':len(raw),'logical_bytes':sum(v.get('size',0) for v in original.values())})
 allow_capture('configured');again=store.capture('configured',binding,coord);assert again==bundle and snapshot(source)==original;checks.append({'id':'FS04','pass':True})
 bad=copy.deepcopy(ref);bad['archive_sha256']='0'*64;badpath=OUT/'wrong-hash';expect_error('FS05-wrong-hash','VERSION_CORRUPT',lambda:store.materialize('wrong-hash',bad,str(badpath),grant));assert not badpath.exists();bad=copy.deepcopy(ref);bad['git_ref']='refs/lore/versions/missing-original';badpath=OUT/'missing-version';expect_error('FS05-missing-version','VERSION_MISSING',lambda:store.materialize('missing-version',bad,str(badpath),grant));assert not badpath.exists();checks.append({'id':'FS05','pass':True})
 badpath=OUT/'wrong-target';allow_materialize('wrong-target',target,ref);expect_error('FS06','UNAUTHORIZED',lambda:store.materialize('wrong-target',ref,str(badpath),grant));assert not badpath.exists() and snapshot(target)==original;checks.append({'id':'FS06','pass':True})
 store.retain('original-input-pin',ref);member='d00/f0000.txt';expected=(target/member).read_bytes();(source/member).write_bytes(b'Z'*128);reference={'version_ref':ref,'path':member,'kind':'file','sha256':sha(expected)};auth.allow('auth','read_reference',grant,context('read_reference',reference=reference));read=store.read_reference(reference,grant);assert read==expected and read!=(source/member).read_bytes();bad=copy.deepcopy(reference);bad['sha256']='0'*64;auth.allow('auth','read_reference',grant,context('read_reference',reference=bad));expect_error('FS07','VERSION_CORRUPT',lambda:store.read_reference(bad,grant));checks.append({'id':'FS07','pass':True})
 save(OUT/'checks.json',checks);save(OUT/'operations.json',actual);save(OUT/'assessment.json',{'status':'PASS_F_SCALE_PREPARATION_ONLY','checks':checks,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'source_edited_after_capture':member,'full_XN12':'UNVERIFIED: actual Node RO F mount remains','loaded_F':{n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n=='lore_files' or n.startswith('lore_files.')}});print(json.dumps({'status':'PASS_F_SCALE_PREPARATION_ONLY','checks':len(checks)}))
if __name__=='__main__':main()
