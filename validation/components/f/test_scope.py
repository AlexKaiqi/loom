"""Independent authority-scope supplement. Missing context exposes old behavior; never permits a PASS."""
import copy,hashlib,json,os,subprocess,unittest
from pathlib import Path
from test_contract import fixture,binding,AUTH,COORD,STOP
FACTORY=None;OUT=None;MODULE=None
SCHEMA='lore-f-authority-context/v1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def context(operation,**fields):return {'schema':SCHEMA,'operation':operation,**fields}
def broad(value,purpose,actual=None):return True

def safe(value):
 if isinstance(value,bytes):return {'bytes_hex':value.hex(),'sha256':sha(value)}
 return value

class Contract(unittest.TestCase):
 def setUp(self):
  self.case=OUT/self._testMethodName;self.case.mkdir();self.events=[];self.verdicts=[];self.serial=0
  self.root=self.case/'surface';fixture(self.root);self.bound=binding(self.root);self.control=self.case/'control';self.store=FACTORY(self.control,broad,broad)
  self.base=self.store.capture('fixture-base',self.bound,COORD)
  self.other=self.case/'other';fixture(self.other);(self.other/'template.md').write_bytes(b'OTHER-VERSION')
  self.alternate=self.store.capture('fixture-alternate',binding(self.other),COORD)
  self.addCleanup(self.save)
 def save(self):
  (self.case/'scope-observations.json').write_text(json.dumps({'events':self.events,'checks':self.verdicts,'status':'PASS' if self.verdicts and all(x['pass'] for x in self.verdicts) else 'FAIL'},indent=2))
 def assertion(self,name,passed):self.verdicts.append({'name':name,'pass':bool(passed)})
 def finish(self):self.assertTrue(self.verdicts and all(x['pass'] for x in self.verdicts),json.dumps(self.verdicts))
 def authority(self,value,purpose,expected):
  self.serial+=1;original=copy.deepcopy({'value':value,'purpose':purpose,'context':expected});p=self.case/('authority-'+str(self.serial)+'.json');p.write_text(json.dumps(original,sort_keys=True));raw=p.read_bytes();calls=[]
  def check(actual_value,actual_purpose,actual_context=None):
   call=copy.deepcopy({'value':actual_value,'purpose':actual_purpose,'context':actual_context});calls.append(call);self.events.append({'authority_file':str(p),'call':call})
   if p.read_bytes()!=raw:return False
   # Deliberate old-implementation observation: a true token without context
   # remains visible as misuse, and exact-context assertions below must fail.
   return actual_value==original['value'] and actual_purpose==original['purpose'] and (actual_context is None or actual_context==original['context'])
  return check,calls
 def observed(self,label,fn,expected_error=None):
  try:result=fn();row={'label':label,'outcome':'RETURNED','result':safe(result)}
  except Exception as e:row={'label':label,'outcome':getattr(e,'code',type(e).__name__),'detail':str(e)}
  self.events.append(row)
  if expected_error is not None:self.assertion(label,row['outcome'] in expected_error)
  else:self.assertion(label,row['outcome']=='RETURNED')
  return row
 def exact_calls(self,label,calls,expected):self.assertion(label,bool(calls) and all(c['context']==expected for c in calls))
 def refs(self):
  p=subprocess.run(['/usr/bin/git','--git-dir='+str(self.control/'versions.git'),'for-each-ref','--format=%(refname) %(objectname)'],capture_output=True,check=True);return p.stdout.decode().splitlines()
 def capture_context(self,id,bound,base=None):return context('capture',request_id=id,binding=bound,actual_root=binding(Path(bound['path']))['root'],profile='host-v1',base_ref=base,coordination=COORD)
 def import_context(self,id,bound,path,source,base=None):return context('import_archive',request_id=id,binding=bound,actual_root=binding(Path(bound['path']))['root'],profile='host-v1',base_ref=base,source_ref=source,archive={'path':str(Path(path).resolve()),'bytes':Path(path).stat().st_size,'sha256':sha(Path(path).read_bytes())})
 def prepare(self,label):
  root=self.case/(label+'-root');fixture(root);bound=binding(root);base=self.store.capture(label+'-base',bound,COORD)
  stage=self.case/(label+'-stage');self.store.materialize(label+'-stage',base['version_ref'],str(stage),AUTH);(stage/'template.md').write_bytes(b'OUTPUT')
  output=self.store.capture(label+'-output',binding(stage),COORD)
  id=label+'-install';intent={'resource_id':'S1','domain':'surface','binding':bound,'staged_path':str(stage),'staged_root':binding(stage)['root'],'version_ref':output['version_ref'],'base_ref':base['version_ref'],'execution_id':'E1','generation':1,'intent_ref':{'authority':'controlled-writer-fixture','request_id':id}}
  return id,intent,root,stage
 def install_context(self,id,intent,stop):return context('install',request_id=id,intent=intent,stopped_ref=stop,actual_current_root=binding(Path(intent['binding']['path']))['root'],actual_staged_root=binding(Path(intent['staged_path']))['root'])
 def test_FS01_capture_authorization(self):
  cap={'id':'capture-grant'}
  for label,wrong in [('wrong-root',True),('positive',False)]:
   bound=copy.deepcopy(self.bound);bound['authorization']=cap;expected=self.capture_context(label,bound);actual=copy.deepcopy(bound)
   if wrong:actual.update(path=str(self.other),root=binding(self.other)['root'])
   check,calls=self.authority(cap,'capture',expected);store=FACTORY(self.control,check,broad);before=self.refs();observed=self.observed(label,lambda:store.capture(label,actual,COORD),{'UNAUTHORIZED'} if wrong else None)
   if wrong:self.assertion('no unauthorized rooted version',self.refs()==before)
   else:self.exact_calls('capture actual context',calls,expected)
  self.finish()
 def test_FS02_capture_coordination(self):
  for label,wrong in [('wrong-revision',True),('positive',False)]:
   expected=self.capture_context(label,self.bound);actual=copy.deepcopy(self.bound)
   if wrong:actual['revision']+=1
   check,calls=self.authority(COORD,'coordination',expected);store=FACTORY(self.control,broad,check);before=self.refs();self.observed(label,lambda:store.capture(label,actual,COORD),{'REFERENCE_INVALID'} if wrong else None)
   if wrong:self.assertion('no wrong coordination version',self.refs()==before)
   else:self.exact_calls('coordination complete context',calls,expected)
  self.finish()
 def test_FS03_import_authorization(self):
  cap={'id':'import-grant'};path=self.base['archive_path']
  for label,wrong in [('wrong-resource',True),('positive',False)]:
   bound=copy.deepcopy(self.bound);bound['authorization']=cap;expected=self.import_context(label,bound,path,COORD);actual=copy.deepcopy(bound)
   if wrong:actual.update(resource_id='W1',domain='workspace')
   check,calls=self.authority(cap,'import_archive',expected);store=FACTORY(self.control,check,broad);before=self.refs();self.observed(label,lambda:store.import_archive(label,actual,path,COORD,None,'host-v1'),{'UNAUTHORIZED'} if wrong else None)
   if wrong:self.assertion('no unauthorized import root',self.refs()==before)
   else:self.exact_calls('import actual context',calls,expected)
  self.finish()
 def test_FS04_source_archive_binding(self):
  path=self.case/'export.tar';a=Path(self.base['archive_path']).read_bytes();b=Path(self.alternate['archive_path']).read_bytes();self.assertNotEqual(a,b);path.write_bytes(a)
  source={'owner':'X','kind':'frozen-export','id':'original-export-A','execution_id':'E1','generation':1,'archive_sha256':sha(a),'archive_bytes':len(a)}
  for label,wrong in [('same-path-wrong-bytes','bytes'),('wrong-base','base'),('positive',None)]:
   path.write_bytes(a);expected=self.import_context(label,self.bound,path,source,self.base['version_ref']);base=self.base['version_ref']
   if wrong=='bytes':path.write_bytes(b)
   if wrong=='base':base=self.alternate['version_ref']
   check,calls=self.authority(source,'source',expected);store=FACTORY(self.control,broad,check);before=self.refs();self.observed(label,lambda:store.import_archive(label,self.bound,str(path),source,base,'host-v1'),{'REFERENCE_INVALID'} if wrong else None)
   if wrong:self.assertion('wrong source did not root '+label,self.refs()==before)
   else:self.exact_calls('source actual bytes/base context',calls,expected)
  self.finish()
 def test_FS05_materialize_target(self):
  cap={'id':'materialize-grant'}
  for label,wrong in [('wrong-target',True),('positive',False)]:
   target=self.case/(label+'-allowed');actual=self.case/(label+'-forbidden') if wrong else target
   expected=context('materialize',request_id=label,version_ref=self.base['version_ref'],target_path=str(target),target_parent={'path':str(target.parent),'root':binding(target.parent)['root']},profile='host-v1')
   check,calls=self.authority(cap,'materialize',expected);store=FACTORY(self.control,check,broad);self.observed(label,lambda:store.materialize(label,self.base['version_ref'],str(actual),cap),{'UNAUTHORIZED'} if wrong else None)
   if wrong:self.assertion('forbidden target absent',not actual.exists())
   else:self.exact_calls('materialize actual target context',calls,expected)
  self.finish()
 def test_FS06_history_scope(self):
  cap={'id':'history-grant'};ref={'version_ref':self.base['version_ref'],'path':'template.md','kind':'file'};expected=context('read_reference',reference=ref)
  workspace=self.store.capture('workspace-version',binding(self.other,'W1','workspace'),COORD)
  for label,change in [('wrong-path',{'path':'ignored-input'}),('wrong-version',{'version_ref':self.alternate['version_ref']}),('wrong-domain',{'version_ref':workspace['version_ref']}),('positive',{})]:
   check,calls=self.authority(cap,'read_reference',expected);store=FACTORY(self.control,check,broad);actual={**copy.deepcopy(ref),**change};row=self.observed(label,lambda:store.read_reference(actual,cap),{'UNAUTHORIZED'} if change else None)
   if not change:self.exact_calls('read actual immutable reference',calls,expected);self.assertion('authorized original bytes',row.get('result',{}).get('bytes_hex')=='T0 雪'.encode().hex())
  self.finish()
 def install_case(self,purpose):
  for label,wrong in [('wrong',True),('positive',False)]:
   id,intent,root,stage=self.prepare(purpose+'-'+label);cap={'id':'install-grant'};stop=copy.deepcopy(STOP)
   if purpose=='authorization':intent['binding']['authorization']=cap
   actual=copy.deepcopy(intent);expected=self.install_context(id,intent,stop);actual_id=id
   if wrong:
    if purpose=='authorization':
     allowed_stage=self.case/(purpose+'-'+label+'-actually-authorized-stage');self.store.materialize(purpose+'-'+label+'-authorized-stage',intent['version_ref'],str(allowed_stage),AUTH)
     expected['intent']['staged_path']=str(allowed_stage);expected['intent']['staged_root']=binding(allowed_stage)['root'];expected['actual_staged_root']=binding(allowed_stage)['root']
    elif purpose=='intent':expected['request_id']=id+'-authorized';actual['intent_ref']['request_id']=id+'-authorized';expected['intent']['intent_ref']['request_id']=id+'-authorized'
    else:expected['intent']['base_ref']=self.alternate['version_ref']
   value=cap if purpose=='authorization' else actual['intent_ref'] if purpose=='intent' else stop
   check,calls=self.authority(value,'install' if purpose=='authorization' else purpose,expected)
   def refs(value,refpurpose,ctx=None):return check(value,refpurpose,ctx) if refpurpose==purpose else True
   store=FACTORY(self.control,check if purpose=='authorization' else broad,broad if purpose=='authorization' else refs)
   before=[binding(p)['root'] for p in (root,stage)];self.observed(purpose+'-'+label,lambda:store.install(actual_id,actual,stop),{'UNAUTHORIZED'} if wrong and purpose=='authorization' else {'REFERENCE_INVALID'} if wrong else None)
   if wrong:self.assertion('wrong '+purpose+' no exchange',before==[binding(p)['root'] for p in (root,stage)])
   else:self.exact_calls(purpose+' complete original install context',calls,expected);self.assertion('positive exchange real',before==[binding(p)['root'] for p in (stage,root)])
  self.finish()
 def test_FS07_install_authorization(self):self.install_case('authorization')
 def test_FS08_install_intent(self):self.install_case('intent')
 def test_FS09_install_stop(self):self.install_case('stop')
 def test_FS10_release_pin_scope(self):
  cap={'id':'release-grant'}
  for label,wrong in [('wrong-pin',True),('positive',False)]:
   pin=label+'-victim';self.store.retain(pin,self.base['version_ref'])
   if wrong:self.store.retain(pin+'-allowed',self.base['version_ref'])
   expected=context('release',pin_id=pin+'-allowed' if wrong else pin,version_ref=self.base['version_ref'])
   check,calls=self.authority(cap,'release',expected);store=FACTORY(self.control,check,broad);before=self.refs();self.observed(label,lambda:store.release(pin,cap),{'UNAUTHORIZED'} if wrong else None)
   if wrong:self.assertion('wrong pin root remains',before==self.refs())
   else:self.exact_calls('release original pin/version context',calls,expected);self.assertion('authorized pin root removed',before!=self.refs())
  self.finish()
 def test_FS11_legacy_authorization_rejected(self):
  ref={'version_ref':self.base['version_ref'],'path':'template.md','kind':'file'}
  self.observed('three-argument positive',lambda:self.store.read_reference(ref,AUTH))
  def old(value,purpose):return True
  store=FACTORY(self.control,old,broad);self.observed('legacy authorization must reject',lambda:store.read_reference(ref,AUTH),{'UNAUTHORIZED'});self.finish()
 def test_FS12_legacy_reference_rejected(self):
  self.observed('three-argument positive',lambda:self.store.capture('new-positive',self.bound,COORD))
  def old(value,purpose):return True
  store=FACTORY(self.control,broad,old);before=self.refs();self.observed('legacy reference must reject',lambda:store.capture('legacy-ref',self.bound,COORD),{'REFERENCE_INVALID'});self.assertion('legacy reference did not root version',self.refs()==before);self.finish()
