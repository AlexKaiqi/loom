"""Independent file observations; imports no F candidate and never extracts archives."""
import base64, hashlib, io, json, os, stat, subprocess, tarfile
from decimal import Decimal
from pathlib import Path

def digest(data): return hashlib.sha256(data).hexdigest()
def snapshot(root):
 root=Path(root); out={}; links={}
 def visit(q):
  s=q.lstat(); name=os.fsdecode(os.fsencode(q.relative_to(root)))
  kind='file' if stat.S_ISREG(s.st_mode) else 'dir' if stat.S_ISDIR(s.st_mode) else 'symlink' if stat.S_ISLNK(s.st_mode) else 'unsupported'
  item={'kind':kind,'mode':stat.S_IMODE(s.st_mode),'mtime_ns':s.st_mtime_ns,'uid':s.st_uid,'gid':s.st_gid,'xattrs':{x:base64.b64encode(os.getxattr(q,x,follow_symlinks=False)).decode() for x in sorted(os.listxattr(q,follow_symlinks=False))}}
  if kind=='file':item['bytes_b64']=base64.b64encode(q.read_bytes()).decode();links.setdefault((s.st_dev,s.st_ino),[]).append(name)
  elif kind=='symlink':item['target_b64']=base64.b64encode(os.fsencode(os.readlink(q))).decode()
  out[name]=item
  if kind=='dir':
   with os.scandir(q) as it: children=sorted(it,key=lambda e:os.fsencode(e.name))
   for e in children:visit(Path(e.path))
 visit(root)
 return {'entries':out,'hardlink_groups':sorted(sorted(g) for g in links.values() if len(g)>1)}

def assert_tree(actual_root, expected):
 actual=snapshot(actual_root)
 if actual!=expected:raise AssertionError('actual complete tree differs from independent expected')
 return actual

def git_archive(control, ref):
 p=subprocess.run(['git','--git-dir='+str(Path(control)/'versions.git'),'-c','core.hooksPath=/dev/null','cat-file','blob',ref['git_ref']+':archive.tar'],capture_output=True,timeout=15,env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
 if p.returncode:raise FileNotFoundError('rooted Git archive unavailable: '+p.stderr.decode(errors='replace'))
 if digest(p.stdout)!=ref['archive_sha256']:raise AssertionError('actual Git archive digest mismatch')
 return p.stdout

def assert_ref(ref, resource, domain):
 if not isinstance(ref,dict) or ref.get('resource_id')!=resource or ref.get('domain')!=domain:raise AssertionError('reference authority binding mismatch')
 for k in ['git_ref','archive_sha256','manifest_sha256','profile']:
  if not ref.get(k):raise ValueError('missing observation '+k)
 return ref


def manifest_for(tree,resource,domain,profile='host-v1'):
 entries={}
 for name,item in tree['entries'].items():
  entry=dict(item)
  if entry['kind']=='file':
   raw=base64.b64decode(entry.pop('bytes_b64'),validate=True);entry['size']=len(raw);entry['sha256']=digest(raw)
  entries[name]=entry
 return {'schema':'lore-f-manifest/v1','resource_id':resource,'domain':domain,'profile':profile,'tree':{'entries':entries,'hardlink_groups':tree['hardlink_groups']}}

def git_file(control,ref,name,expected_digest):
 p=subprocess.run(['git','--git-dir='+str(Path(control)/'versions.git'),'-c','core.hooksPath=/dev/null','cat-file','blob',ref['git_ref']+':'+name],capture_output=True,timeout=15,env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
 if p.returncode:raise FileNotFoundError('rooted Git '+name+' unavailable')
 if digest(p.stdout)!=expected_digest:raise AssertionError('actual Git '+name+' digest mismatch')
 return p.stdout

def assert_bundle(bundle,control,expected_tree,resource,domain):
 ref=assert_ref(bundle['version_ref'],resource,domain);root=Path(control).resolve();raw={}
 for field,name,key in [('archive_path','archive.tar','archive_sha256'),('manifest_path','manifest.json','manifest_sha256')]:
  p=Path(bundle[field])
  if not p.resolve().is_relative_to(root):raise AssertionError('returned artifact outside controlled root')
  if not stat.S_ISREG(p.lstat().st_mode):raise AssertionError('returned artifact is not an ordinary sealed file')
  data=p.read_bytes()
  if digest(data)!=ref[key]:raise AssertionError('returned '+field+' hash mismatch')
  if data!=git_file(control,ref,name,ref[key]):raise AssertionError('returned artifact differs from actual Git blob')
  raw[name]=data
 actual=json.loads(raw['manifest.json']);expected=manifest_for(expected_tree,resource,domain,ref['profile'])
 observed_archive=archive_tree(raw['archive.tar'])
 if json.dumps(observed_archive,sort_keys=True,separators=(',',':'),allow_nan=False)!=json.dumps(expected['tree'],sort_keys=True,separators=(',',':'),allow_nan=False):raise AssertionError('actual archive member facts differ from independent directory facts')
 # Canonical JSON comparison keeps bool/float distinct from required integer fields.
 if json.dumps(actual,sort_keys=True,separators=(',',':'),allow_nan=False)!=json.dumps(expected,sort_keys=True,separators=(',',':'),allow_nan=False):raise AssertionError('actual manifest members/sizes/hashes/metadata/scope differ from independent directory facts')
 return actual


def archive_tree(data):
 if len(data)>2097152:raise AssertionError('archive exceeds independent fixture observation budget')
 entries={};owners={};groups={};total=0
 def path(raw):
  name=raw[2:] if raw.startswith('./') else raw
  if name=='.':return name
  if name.startswith('/') or not name or any(x in {'','..','.'} for x in name.split('/')):raise AssertionError('unsafe archive member path')
  return name
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as archive:
  for member in archive:
   name=path(member.name)
   if name in entries or len(entries)>=64:raise AssertionError('duplicate/over-budget archive member')
   for parent in Path(name).parents:
    key=str(parent)
    if key in entries and entries[key]['kind']!='dir':raise AssertionError('archive uses non-directory as parent')
   kind='file' if member.isfile() or member.islnk() else 'dir' if member.isdir() else 'symlink' if member.issym() else None
   if kind is None:raise AssertionError('unsupported archive member type')
   ns=Decimal(member.pax_headers.get('mtime',str(member.mtime)))*1000000000
   if ns!=ns.to_integral_value():raise AssertionError('mtime precision not representable in nanoseconds')
   attrs={k[len('SCHILY.xattr.'):]:base64.b64encode(value.encode('utf-8','surrogateescape')).decode() for k,value in member.pax_headers.items() if k.startswith('SCHILY.xattr.')}
   item={'kind':kind,'mode':member.mode,'mtime_ns':int(ns),'uid':member.uid,'gid':member.gid,'xattrs':attrs}
   if member.islnk():
    target=path(member.linkname)
    if target not in entries or entries[target]['kind']!='file':raise AssertionError('hardlink target not prior tree regular file')
    item['size']=entries[target]['size'];item['sha256']=entries[target]['sha256'];owners[name]=owners[target];groups[owners[target]].append(name)
   elif member.isfile():
    if member.size<0 or total+member.size>1048576:raise AssertionError('logical content exceeds observation budget')
    raw=archive.extractfile(member).read();total+=len(raw)
    if len(raw)!=member.size:raise AssertionError('truncated actual archive member')
    item['size']=len(raw);item['sha256']=digest(raw);owners[name]=name;groups[name]=[name]
   elif member.issym():item['target_b64']=base64.b64encode(member.linkname.encode('utf-8','surrogateescape')).decode()
   entries[name]=item
 return {'entries':entries,'hardlink_groups':sorted(sorted(x) for x in groups.values() if len(x)>1)}
