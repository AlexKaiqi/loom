"""Explicit R authority fixture: original JSON bytes and actual ordinary F-layout objects."""
import hashlib,json,stat
from pathlib import Path

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def tree_digest(root):
 rows=[]
 for p in sorted(Path(root).rglob('*')):
  if not p.is_file() or p.is_symlink():raise ValueError('fixture tree must contain ordinary files only')
  rows.append([str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()])
 return hashlib.sha256(canonical(rows)).hexdigest()
def root_record(path):
 p=Path(path);s=p.lstat();return {'path':str(p),'dev':s.st_dev,'ino':s.st_ino}
def add_ref(f,key,kind,owner,**fields):
 assert key.startswith('rp-')
 raw=canonical({'authority_fixture':True,'id':key,'kind':kind,'owner':owner,**fields});(f.refroot/key).write_bytes(raw)
 ref={'id':key,'kind':kind,'owner':owner,'sha256':hashlib.sha256(raw).hexdigest(),**fields};f.refs[key]=ref;return ref

def check(ref,purpose,expected,refs,refroot):
 try:
  if not isinstance(ref,dict) or not str(ref.get('id','')).startswith('rp-'):return None
  original=refs.get(ref['id']);p=Path(refroot)/ref['id']
  if ref!=original or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=ref['sha256']:return False
  kinds={'restore_version':'file_version','restore_session':'session','restore_events':'event_cursor','restore_effect':'effect','environment':'environment','staged':'staged','installation':'installation','stopped':'stopped','published':'file_version'}
  if purpose in kinds and ref['kind']!=kinds[purpose]:return False
  if any(canonical(ref.get(k))!=canonical(v) for k,v in (expected or {}).items()):return False
  for field in (['root'] if purpose=='staged' else ['current','retired'] if purpose=='installation' else []):
   root=ref[field];s=Path(root['path']).lstat()
   if not stat.S_ISDIR(s.st_mode) or {'dev':s.st_dev,'ino':s.st_ino}!={k:root[k] for k in ['dev','ino']}:return False
  if purpose in ['staged','installation']:
   tree=ref['root' if purpose=='staged' else 'current']['path']
   if tree_digest(tree)!=ref['tree_sha256']:return False
  return True
 except (OSError,KeyError,TypeError,ValueError):return False
