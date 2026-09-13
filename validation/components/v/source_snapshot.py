"""Capture the complete candidate package before import; execute only copied .py."""
import hashlib,importlib,sys
from pathlib import Path
class SourceError(ValueError):pass

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def capture(module,search_paths,out):
 parts=module.split('.')
 if not all(x.isidentifier() for x in parts):raise SourceError('invalid explicit candidate module')
 top=parts[0];origin=None;package=False
 for base in map(Path,search_paths):
  if (base/top/'__init__.py').is_file():origin=base/top;package=True;break
  if len(parts)==1 and (base/(top+'.py')).is_file():origin=base/(top+'.py');break
 if origin is None:return None
 files=sorted(origin.rglob('*.py')) if package else [origin]
 if not files or any(q.is_symlink() for q in files):raise SourceError('candidate source absent or symlinked')
 target=Path(out);target.mkdir(parents=True,exist_ok=False);original={};copied={}
 for q in files:
  relative=Path(top)/q.relative_to(origin) if package else Path(q.name);dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True);data=q.read_bytes();dest.write_bytes(data);original[str(q.resolve())]=hashlib.sha256(data).hexdigest();copied[str(dest.resolve())]=hashlib.sha256(data).hexdigest()
 return {'module':module,'search_path':str(target.resolve()),'original':original,'executed_snapshot':copied,'scope':'all Python source of selected package; stdlib identified by run environment; no pyc copied'}
def unchanged(record):
 return all(Path(q).is_file() and digest(Path(q))==h for group in ['original','executed_snapshot'] for q,h in record[group].items())
def load(record):
 top=record['module'].split('.')[0]
 if any(n==top or n.startswith(top+'.') for n in sys.modules):raise SourceError('candidate already imported before snapshot')
 sys.path.insert(0,record['search_path']);sys.dont_write_bytecode=True;importlib.invalidate_caches();mod=importlib.import_module(record['module'])
 if str(Path(mod.__file__).resolve()) not in record['executed_snapshot']:raise SourceError('candidate imported outside bound snapshot')
 for name,item in list(sys.modules.items()):
  if name==top or name.startswith(top+'.'):
   f=getattr(item,'__file__',None)
   if f and str(Path(f).resolve()) not in record['executed_snapshot']:raise SourceError('candidate helper imported outside bound snapshot')
 return mod
