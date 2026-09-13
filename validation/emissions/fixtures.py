"""Ordinary archives and a declared source-resolver fixture, never an X/F authority claim."""
import copy,hashlib,io,json,tarfile
from pathlib import Path
D=copy.deepcopy
PATH='.lore/emit-requests.jsonl'
def encode(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def line(id,name='notice',payload=None):return encode(dict(id=id,name=name,payload=payload))+b'\n'
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def archive(path,outbox,kind='file'):
 stream=io.BytesIO()
 with tarfile.open(fileobj=stream,mode='w',format=tarfile.PAX_FORMAT) as tar:
  items=[('.',None),('goal.txt',b'ordinary goal stays complete\n')]
  if outbox is not None:items += [('.lore',None),(PATH,outbox)]
  for name,data in items:
   item=tarfile.TarInfo(name);item.uid=item.gid=1000;item.mode=0o755 if data is None else 0o644
   if data is None:item.type=tarfile.DIRTYPE
   elif name==PATH and kind=='symlink':item.type=tarfile.SYMTYPE;item.mode=0o777;item.linkname='../goal.txt'
   elif name==PATH and kind=='hardlink':item.type=tarfile.LNKTYPE;item.linkname='goal.txt'
   else:item.size=len(data)
   tar.addfile(item,io.BytesIO(data) if data is not None and item.isfile() else None)
 raw=stream.getvalue();Path(path).write_bytes(raw)
 return dict(path=str(Path(path).absolute()),bytes=len(raw),sha256=sha(raw))
class Source:
 def __init__(self,root,label,base=b'',output=None,kind='file'):
  self.root=Path(root)/label;self.root.mkdir();self.calls=[]
  scope=dict(namespace='n1',surface_id='surface-n1',session_id='session-1',session_generation=1)
  self.binding=dict(session_scope=scope,session_id='session-1',operation_id='invocation-1',source_result_ref=None,harness_ref={'id':'h1','sha256':'a'*64},input_ref={'id':'input1','sha256':'b'*64})
  self.effect='s-tool-'+sha(encode([scope,self.binding['operation_id'],label]))
  self.frame=dict(type='tool.request',session_id='session-1',operation_id='invocation-1',effect_id=self.effect,invocation_id=label,source_result_ref=None,request=dict(target='runtime',script='ordinary emitted application data'))
  base_ref=archive(self.root/'base.tar',base or None);out_ref=archive(self.root/'output.tar',output,kind)
  xb=dict(domain='runtime',execution_id=self.effect,object_generation=1,freeze_generation=1,target_id='surface-n1',binding_generation=1,base_version='base-fixture')
  cp=dict(path=out_ref['path'],size=out_ref['bytes'],sha256=out_ref['sha256'],owner='X',state='PREPARED',execution_id=self.effect,object_generation=1,freeze_generation=1,source_binding=xb)
  version=dict(resource_id='surface-n1',domain='surface',archive_sha256=out_ref['sha256'])
  self.pub=dict(R_intent=dict(resource_id='surface-n1',execution_id=self.effect,base_ref=dict(resource_id='surface-n1',domain='surface',archive_sha256=base_ref['sha256'])),F_query=dict(version_ref=version),installation_ref=dict(version_ref=version),registration=dict(id='surface-n1',namespace='n1',kind='surface',revision=2),release=dict(resource_id='surface-n1',execution_id=self.effect,released=True))
  self.source=dict(principal='alice',namespace='n1',domain='runtime',emit_allowed=True,execution_id=self.effect,effect_id=self.effect,binding=self.binding,frame=self.frame,base_archive_ref=base_ref,output_archive_ref=cp,publication_ref=self.pub)
  save(self.root/'source.json',dict(scope='ARCHIVE_SOURCE_FIXTURE_NOT_REAL_XF',source=self.source))
 def resolve(self,effect,binding,pub):
  self.calls.append(dict(effect_id=effect,binding=D(binding),publication_ref=D(pub)))
  return D(self.source)
 def expected_id(self,index):return 'emit-'+sha(encode(['n1',self.binding['operation_id'],self.effect,index]))
 def expected_raw(self,index,name,payload):return encode(dict(schema_version=1,origin='application',source='alice',namespace='n1',request_id=self.expected_id(index),name=name,payload=payload))
