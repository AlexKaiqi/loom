"""R approval stays original; a full byte-equivalence witness only relocates its sources."""
import hashlib,json,os
from pathlib import Path

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rejected(message):raise RuntimeError("MISSING verified R dependency: "+message)
def gate_original(path):
 try:gate=json.loads(Path(path).read_text())
 except (OSError,ValueError) as e:rejected("original gate unavailable: "+str(e))
 if gate.get('component')!='R' or gate.get('stage')!='G4' or gate.get('status')!='PASS':rejected('actual G4 R PASS required; readiness/FAIL is not acceptance')
 sources=gate.get('implementation')
 if not isinstance(sources,dict) or not sources:rejected('complete absolute implementation closure required')
 for name,expected in sources.items():
  p=Path(name)
  if not p.is_absolute() or not p.is_file() or p.is_symlink() or digest(p)!=expected:rejected('original implementation changed or missing')
 return gate

def verify_loaded(path,loaded,snapshot_path=None):
 gate=gate_original(path);sources=gate['implementation'];loaded=Path(loaded).resolve();original_entry=None
 if not snapshot_path:
  if sources.get(str(loaded))!=digest(loaded):rejected('gate does not bind loaded original')
  original_entry=str(loaded)
 else:
  try:
   proof=json.loads(Path(snapshot_path).read_text());workspace=Path(proof['workspace']).resolve();mapping=proof['source_to_copy']
   if proof['schema']!='lore.source-equivalence/r-v1' or Path(proof['gate_copy']).resolve()!=Path(path).resolve():rejected('wrong source-equivalence gate')
   if digest(path)!=proof['gate_sha256'] or digest(proof['gate_original'])!=proof['gate_sha256']:rejected('original gate bytes differ from copy')
   if gate_original(proof['gate_original'])!=gate:rejected('original gate object differs')
   if set(mapping)!=set(sources):rejected('source-equivalence closure omitted/added original')
   if len({x['copy'] for x in mapping.values()})!=len(mapping):rejected('multiple originals mapped onto one file')
   for original,item in mapping.items():
    copy=Path(item['copy'])
    if not copy.is_absolute() or not copy.resolve().is_relative_to(workspace) or copy.is_symlink() or not copy.is_file() or item['sha256']!=sources[original] or digest(copy)!=sources[original]:rejected('copied R source not equivalent')
    if copy.resolve()==loaded:original_entry=original
   if original_entry is None:rejected('loaded R path is not a bound source copy')
   package=Path(proof['copied_package_root']);actual={str(p.resolve()) for p in package.rglob('*.py')}
   if actual!={str(Path(x['copy']).resolve()) for x in mapping.values()}:rejected('copied R package inventory differs from approved closure')
  except (OSError,ValueError,KeyError,TypeError) as e:rejected('source-equivalence invalid: '+str(e))
 audit=os.environ.get('LORE_DEPENDENCY_AUDIT')
 if audit:
  with Path(audit).open('a') as f:f.write(json.dumps({'pid':os.getpid(),'gate':str(Path(path).resolve()),'gate_sha256':digest(path),'loaded':str(loaded),'original_entry':original_entry,'files':len(sources),'source_equivalence':str(snapshot_path) if snapshot_path is not None else None})+'\n');f.flush();os.fsync(f.fileno())
 return gate
