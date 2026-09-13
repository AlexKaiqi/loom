"""Independent byte/metadata/assertion oracle. No production imports or pass flags."""
from pathlib import PurePosixPath
from decimal import Decimal
import hashlib,io,json,tarfile
class EvidenceError(Exception):pass
def sha(b):return hashlib.sha256(b).hexdigest()
def at(value,path):
 parts=path.split('.') if path else []
 while parts:
  if not isinstance(value,dict):raise EvidenceError('not an object at '+'.'.join(parts))
  # Archive ordinary filenames may themselves contain dots/slashes.
  hit=False
  for n in range(len(parts),0,-1):
   key='.'.join(parts[:n])
   if key in value:value=value[key];parts=parts[n:];hit=True;break
  if not hit:raise EvidenceError('missing '+'.'.join(parts))
 return value
def expected_value(v,frames,fixture,params):
 if isinstance(v,dict) and set(v)=={'ref'}:return at(frames,v['ref'])
 if isinstance(v,str) and v.startswith('$fixture.'):return at(fixture,v[9:])
 if isinstance(v,str) and v.startswith('$parameter.'):return at(params,v[11:])
 return v
def compare(actual,op,wanted):
 if op=='eq':return type(actual) is type(wanted) and actual==wanted
 if op=='ne':return actual!=wanted
 if op=='one_of':return actual in wanted
 if op=='gt':return actual>wanted
 if op=='ge':return actual>=wanted
 if op=='le':return actual<=wanted
 if op=='length_gt':return len(actual)>wanted
 if op=='starts_with':return isinstance(actual,str) and actual.startswith(wanted)
 raise EvidenceError('unknown comparison '+op)
def assess(expected,frames,fixture,params):
 checks=[]
 for e in expected:
  try:
   
   if e['comparison']=='absent':
    try:at(frames,e['path']);ok=False
    except EvidenceError:ok=True
    checks.append({'path':e['path'],'comparison':'absent','pass':ok});continue
   a=at(frames,e['path']);v=expected_value(e['value'],frames,fixture,params);ok=compare(a,e['comparison'],v)
   checks.append({'path':e['path'],'comparison':e['comparison'],'actual':a,'expected':v,'pass':ok})
  except Exception as err:checks.append({'path':e['path'],'pass':False,'missing_or_invalid':str(err)})
 return {'pass':bool(checks) and all(x['pass'] for x in checks),'checks':checks}
def archive(by,canary=b'',max_raw=8388608,max_logical=12582912):
 if len(by)>max_raw:raise EvidenceError('archive raw limit')
 if len(by)<1024 or by[-1024:]!=b'\0'*1024:raise EvidenceError('archive EOF absent')
 files={};logical=0;contents={};contains=False
 with tarfile.open(fileobj=io.BytesIO(by),mode='r:') as t:
  for m in t:
   name=m.name[2:] if m.name.startswith('./') else m.name
   if name in ('','.'):
    if name=='':raise EvidenceError('empty member')
   elif name.startswith('/') or '..' in PurePosixPath(name).parts or '\x00' in name:raise EvidenceError('unsafe member '+name)
   if name in files:raise EvidenceError('duplicate member '+name)
   for par in PurePosixPath(name).parents:
    if str(par) in files and files[str(par)]['type']!='directory':raise EvidenceError('non-directory parent')
   if not (m.isdir() or m.isreg() or m.issym() or m.islnk()):raise EvidenceError('unsupported member')
   if m.sparse:raise EvidenceError('sparse metadata requires independent logical limit')
   logical+=m.size
   if logical>max_logical:raise EvidenceError('expanded limit')
   row={'type':'directory' if m.isdir() else ('symlink' if m.issym() else ('hardlink' if m.islnk() else 'regular')),'mode':m.mode,'uid':m.uid,'gid':m.gid,'mtime_ns':int(Decimal(m.pax_headers.get('mtime',str(m.mtime)))*1000000000),'linkname':m.linkname,'byte_length':m.size}
   for key in m.pax_headers:
    if key.startswith(('SCHILY.xattr.','SCHILY.acl.')):raise EvidenceError('metadata outside current X profile')
   if m.isreg():
    data=t.extractfile(m).read(max_logical+1)
    if len(data)!=m.size:raise EvidenceError('member size differs')
    contents[name]=data
   elif m.islnk():
    target=m.linkname[2:] if m.linkname.startswith('./') else m.linkname
    if target not in contents or files[target]['type'] not in ('regular','hardlink'):raise EvidenceError('unsafe hardlink')
    data=contents[target];contents[name]=data
   else:data=None
   if data is not None:
    row['sha256']=sha(data);row['byte_length']=len(data);contains=contains or bool(canary and canary in data)
    if name=='effect':row['count']=data.count(b'one\n')
    if name=='heartbeat':row['count']=int(data.strip())
    if name.endswith('.json'):
     try:
      parsed=json.loads(data)
      if isinstance(parsed,dict):row["json"]=parsed
     except (ValueError,UnicodeError):pass
    if name.endswith('.jsonl'):row['text']=data.decode();row['starts_with']=data.decode()[:256]
   files[name]=row
 return {'sha256':sha(by),'size':len(by),'logical_size':logical,'files':files,'contains_credential_canary':contains}
