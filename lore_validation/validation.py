"""Strict local data and identity validation; does not interpret business facts."""
import hashlib,json,math,stat
from pathlib import Path

class ValidationError(ValueError):
 def __init__(self,code,message):self.code=code;super().__init__(message)

def fail(message,code='invalid'):raise ValidationError(code,message)
def digest(data):return hashlib.sha256(data).hexdigest()
def _finite(value):
 if isinstance(value,float) and not math.isfinite(value):fail('nonfinite observation')
 if isinstance(value,dict):
  if any(type(k) is not str for k in value):fail('nonstring JSON object key')
  for v in value.values():_finite(v)
 elif isinstance(value,list):
  for v in value:_finite(v)
 elif value is not None and type(value) not in (str,bool,int,float):fail('observation not JSON data')

def finite(value):
 try:_finite(value)
 except RecursionError:fail('JSON data nesting exceeds supported depth')

def strict_json(path):
 def pairs(items):
  out={}
  for k,v in items:
   if k in out:fail('duplicate JSON key '+k)
   out[k]=v
  return out
 def constant(value):fail('nonfinite JSON constant '+value)
 try:
  q=Path(path)
  if not stat.S_ISREG(q.lstat().st_mode):fail('JSON input is not ordinary file')
  with q.open('rb') as f:raw=f.read(2097153)
  if len(raw)>2097152:fail('JSON input exceeds2MiB')
  value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant);finite(value);return value,raw
 except (OSError,UnicodeError,json.JSONDecodeError,RecursionError) as e:fail('invalid JSON input: '+str(e))

def local_file(root,relative):
 if type(relative) is not str or not relative or '\x00' in relative:fail('invalid relative file','path_invalid')
 path=Path(relative)
 if path.is_absolute() or '..' in path.parts:fail('file path escapes permitted root','path_invalid')
 base=Path(root).resolve();p=base/path
 try:
  if not p.resolve(strict=True).is_relative_to(base) or not stat.S_ISREG(p.lstat().st_mode):fail('file outside root or not ordinary','path_invalid')
 except OSError as e:fail('missing original file: '+str(e),'missing')
 return p

def local_dir(root,relative):
 if type(relative) is not str or not relative:fail('invalid evidence directory','path_invalid')
 path=Path(relative)
 if path.is_absolute() or '..' in path.parts:fail('evidence directory escapes root','path_invalid')
 base=Path(root).resolve();p=base/path
 try:
  if not p.resolve(strict=True).is_relative_to(base) or not stat.S_ISDIR(p.lstat().st_mode):fail('evidence directory not ordinary controlled directory','path_invalid')
 except OSError as e:fail('missing evidence directory: '+str(e),'missing')
 return p

def file_digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while chunk:=f.read(1048576):h.update(chunk)
 return h.hexdigest()

def verify_file(root,ref):
 if type(ref) is not dict or not {'path','sha256'}<=ref.keys():fail('incomplete file reference')
 p=local_file(root,ref['path']);actual=file_digest(p)
 if type(ref['sha256']) is not str or actual!=ref['sha256']:fail('original file differs: '+ref['path'],'version_mismatch')
 return {'path':ref['path'],'sha256':actual}

def ids(values,label):
 if type(values) is not list or not values or any(type(x) is not str or not x for x in values) or len(set(values))!=len(values):fail('empty/duplicate/invalid '+label)
 return set(values)

def indexed(rows,label):
 if type(rows) is not list:fail('invalid '+label)
 keys=ids([r.get('id') if type(r) is dict else None for r in rows],label)
 return {r['id']:r for r in rows}
