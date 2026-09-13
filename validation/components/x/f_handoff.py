"""External X016 fixture. F errors come from copied verified F, stop from Engine."""
import copy,hashlib,json,os
from pathlib import Path
from oracle import archive,EvidenceError
from source_closure import verify_f
ROOT=Path(__file__).resolve().parents[3]
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def identity(path):s=Path(path).stat();return {'dev':s.st_dev,'ino':s.st_ino}
def saved(path,obj):
 with path.open('w') as f:json.dump(obj,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def require(test,message):
 if not test:raise EvidenceError(message)

class Handoff:
 def __init__(self,fixture,out):
  self.fx=fixture;self.out=out/'f-handoff';self.out.mkdir();self.calls=[];self.expected={};self.retained=None
  self.equivalence=verify_f(ROOT)
  from lore_files import FileStore,FileError
  self.FileError=FileError
  import sys
  copied={row['copy'] for row in self.equivalence['implementation']}
  require(all(str(Path(m.__file__).resolve()) in copied for n,m in sys.modules.items() if n=='lore_files' or n.startswith('lore_files.')),'F import outside gate-equivalent copy')
  self.binding={'resource_id':fixture['request']['target_id'],'domain':{'runtime':'surface','task':'workspace'}[fixture['request']['domain']],'path':str(fixture['target']),'root':identity(fixture['target']),'revision':fixture['request']['binding_generation'],'authorization':{'owner':'X016-controlled-R-fixture','id':'exact-target-grant'}}
  self.store=FileStore(self.out/'control',self.auth,self.ref)
  coord={'owner':'X016-controlled-R-fixture','id':'capture-exclusive-port','binding':copy.deepcopy(self.binding)}
  context=self.context('capture',request_id='x016-base',binding=self.binding,actual_root=self.binding['root'],profile='host-v1',base_ref=None,coordination=coord)
  self.allow('auth','capture',self.binding['authorization'],context);self.allow('ref','coordination',coord,context)
  self.base=self.store.capture('x016-base',self.binding,coord)
  fixture['request']['base_version']=digest(canonical(self.base['version_ref']));fixture['authority']['base_version']=fixture['request']['base_version']
  self.request=copy.deepcopy(fixture['request']);self.request_sha=digest(canonical(self.request))
  saved(self.out/'base.json',{'bundle':self.base,'binding':self.binding,'opaque_base_version':fixture['request']['base_version'],'original_manifest':json.loads(Path(self.base['manifest_path']).read_text()),'archive_sha256':digest(Path(self.base['archive_path']).read_bytes()),'request':self.request,'request_sha256':self.request_sha})
 def context(self,operation,**kw):return {'schema':'lore-f-authority-context/v1','operation':operation,**copy.deepcopy(kw)}
 def allow(self,kind,purpose,value,context):self.expected[kind,purpose]=(copy.deepcopy(value),copy.deepcopy(context))
 def check(self,kind,value,purpose,context):
  valid=(value,context)==self.expected.get((kind,purpose));self.calls.append({'kind':kind,'purpose':purpose,'value':value,'context':context,'accepted':valid});saved(self.out/'authority-calls.json',self.calls);return valid
 def auth(self,value,purpose,context):return self.check('auth',value,purpose,context)
 def ref(self,value,purpose,context):return self.check('ref',value,purpose,context)
 def read_checkpoint(self,ref):
  p=Path(ref['path']);root=self.fx['state'].resolve()
  require(p.is_absolute() and not p.is_symlink() and p.resolve(strict=True).is_relative_to(root),'checkpoint path outside original state')
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,'rb') as f:raw=f.read(8388609)
  require(len(raw)<=8388608 and len(raw)==ref['size'] and digest(raw)==ref['sha256'],'checkpoint actual hash/length mismatch')
  return raw
 def prepared(self,frame):
  binding=copy.deepcopy(frame['api']['binding']);physical=frame['physical'];ref=copy.deepcopy(frame['api']['artifacts']['checkpoint']);raw=self.read_checkpoint(ref)
  require(physical.get('paused') is True and physical.get('container_running') is True,'original checkpoint not actually paused')
  require(physical['container']['Id']==binding['container_id'] and physical['volume']['Name']==binding['volume_id'],'prepared Engine binding mismatch')
  require(physical['exec']['ID']==binding['exec_id'] and physical['exec']['ContainerID']==binding['container_id'],'prepared original exec mismatch')
  require(type(binding['object_generation']) is int and type(binding['freeze_generation']) is int and physical['namespace'],'missing original generation/namespace')
  parsed=archive(raw,self.fx['canary']);require(parsed['files']==frame['archive']['files'],'checkpoint differs from independent paused volume export')
  target=self.out/'original-checkpoint.tar'
  with target.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  self.retained={'binding':binding,'artifact':ref,'archive':{'path':str(target),'sha256':digest(raw),'size':len(raw)},'namespace':physical['namespace'],'volume':physical['volume'],'request_sha256':self.request_sha,'base_ref':self.base['version_ref'],'parsed':parsed}
  saved(self.out/'prepared-source.json',self.retained)
 def validate(self,frames,observer):
  require(self.retained is not None,'original prepared source absent');source=self.retained;sealed=frames['sealed'];sb=sealed['api']['binding'];pb=source['binding']
  for key in ('container_id','exec_id','volume_id','object_generation','freeze_generation'):
   require(sb.get(key)==pb[key],'sealed original '+key+' differs')
  sealed_ref=sealed['api']['artifacts']['checkpoint'];require(sealed_ref==source['artifact'],'sealed original archive ref differs')
  raw=self.read_checkpoint(sealed_ref);require(digest(raw)==source['archive']['sha256'] and Path(source['archive']['path']).read_bytes()==raw,'original source bytes changed after prepare')
  require(self.fx['request']==self.request,'execution request changed since captured F base')
  current=observer.inspect(pb['container_id'])
  require(current is None or (current['Id']==pb['container_id'] and not current['State']['Running'] and current['State']['Pid']==0),'original Engine execution still running')
  processes=observer.process_facts(0,source['namespace'],0)
  require(processes['namespace']==source['namespace'] and processes['namespace_pids']==[],'original namespace still owns processes')
  ex=observer.exec_inspect(pb['exec_id']);require(ex is None or (ex['ContainerID']==pb['container_id'] and not ex['Running']),'original exec still running or wrong container')
  stop={'owner':'X016-external-Engine-observer','execution_id':self.request['execution_id'],'generation':pb['object_generation'],'container_id':pb['container_id'],'exec_id':pb['exec_id'],'namespace':source['namespace'],'freeze_generation':pb['freeze_generation'],'archive_sha256':source['archive']['sha256'],'request_sha256':self.request_sha}
  saved(self.out/'actual-stop.json',{'reference':stop,'Engine':current,'exec':ex,'processes':processes})
  ref={'owner':'X016-external-retained-source','binding':pb,'request_sha256':self.request_sha,'base_ref':self.base['version_ref'],'resource_id':self.binding['resource_id'],'domain':self.binding['domain'],'archive':source['archive'],'stopped_ref':stop}
  context=self.context('import_archive',request_id='x016-import',binding=self.binding,actual_root=identity(self.fx['target']),profile='host-v1',base_ref=self.base['version_ref'],source_ref=ref,archive={'path':source['archive']['path'],'bytes':len(raw),'sha256':digest(raw)})
  self.allow('auth','import_archive',self.binding['authorization'],context);self.allow('ref','source',ref,context)
  output=self.store.import_archive('x016-import',self.binding,source['archive']['path'],ref,self.base['version_ref'],'host-v1');saved(self.out/'import.json',output)
  stage=self.fx['root']/'f-staged';auth={'owner':'X016-controlled-R-fixture','id':'exact-stage-grant'}
  context=self.context('materialize',request_id='x016-materialize',version_ref=output['version_ref'],target_path=str(stage),target_parent={'path':str(stage.parent),'root':identity(stage.parent)},profile='host-v1');self.allow('auth','materialize',auth,context)
  materialized=self.store.materialize('x016-materialize',output['version_ref'],str(stage),auth);saved(self.out/'materialized.json',materialized)
  intent={'resource_id':self.binding['resource_id'],'domain':self.binding['domain'],'binding':self.binding,'staged_path':str(stage),'staged_root':identity(stage),'version_ref':output['version_ref'],'base_ref':self.base['version_ref'],'execution_id':self.request['execution_id'],'generation':pb['object_generation'],'intent_ref':{'owner':'X016-controlled-R-fixture','id':'original-install-intent'}}
  saved(self.out/'original-install-intent.json',intent)
  context=self.context('install',request_id='x016-install',intent=intent,stopped_ref=stop,actual_current_root=identity(self.fx['target']),actual_staged_root=identity(stage))
  self.allow('auth','install',self.binding['authorization'],context);self.allow('ref','intent',intent['intent_ref'],context);self.allow('ref','stop',stop,context)
  result={'source':ref,'intent':intent,'before':{'target':identity(self.fx['target']),'stage':identity(stage)}}
  try:
   result['installation']=self.store.install('x016-install',intent,stop)
   response={'binding':sb,'installation':result['installation'],'observer':'external-actual-F'}
  except self.FileError as e:
   result['actual_F_error']={'code':e.code,'message':str(e)}
   # The original expected code is solely a translation of this exact F operation.
   if e.code!='BASE_CHANGED':saved(self.out/'installation.json',result);raise
   response={'binding':sb,'error':{'code':'BASE_CONFLICT','source':'actual F.install','original_code':e.code},'observer':'external-actual-F'}
  result['after']={'target':identity(self.fx['target']),'stage':identity(stage)};result['query']=self.store.query_install('x016-install')
  result['human_bytes_hex']=(self.fx['target']/'human-edit').read_bytes().hex() if (self.fx['target']/'human-edit').exists() else None
  if 'actual_F_error' in result:
   require(result['after']==result['before'],'F conflict changed roots')
   require(result['human_bytes_hex']==b'actual-human-edit'.hex(),'human original bytes not retained')
  saved(self.out/'installation.json',result);return response
