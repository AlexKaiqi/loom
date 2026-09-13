"""Frozen V contracts. Fixture observers are verifier-side, never candidate status."""
import copy, hashlib, json, os, unittest
from pathlib import Path
AUDIT=None; OUT=None

def digest(q):return hashlib.sha256(q.read_bytes()).hexdigest()
def write(q,obj):q.write_text(json.dumps(obj,sort_keys=True,allow_nan=False))

class Contract(unittest.TestCase):
 def setUp(self):
  self.n=0;self.case=OUT/self._testMethodName;self.case.mkdir();self.fresh()
 def fresh(self):
  self.n+=1;self.root=self.case/str(self.n);self.root.mkdir();self.ev=self.root/'evidence';self.ev.mkdir();self.run=self.ev/'run-a';self.run.mkdir();self.calls=[]
  self.requirements=[{'id':'A','requirement':'real artifact'},{'id':'B','requirement':'actual execution'},{'id':'C','requirement':'versions'}];write(self.root/'requirements.json',self.requirements)
  bindings=[]
  for k in ['implementation','tests','data','environment']:
   q=self.root/(k+'.txt');q.write_text('FIXED '+k);bindings.append({'path':q.name,'sha256':digest(q),'kind':k})
  self.plan={'schema':'lore-validation-baseline/v1','requirements_source':{'path':'requirements.json','sha256':digest(self.root/'requirements.json')},'requirements':{'A':['C1'],'B':['C1'],'C':['C1']},'bindings':bindings,'runs':[{'id':'run-a','cases':['a','b','c'],'observer':'original'}],'checks':[{'id':'C1','run_id':'run-a','level':'SYSTEM','checker':'artifact'}]}
  self.sub={'schema':'lore-validation-submission/v1','baseline_sha256':'','runs':[{'id':'run-a','evidence_dir':'run-a'}]}
  self.raw={'run_id':'run-a','level':'SYSTEM','started':['a','b','c'],'finished':['a','b','c'],'skipped':[],'exit_code':0,'artifacts':{'report':{'path':'report.txt','sha256':''}}}
  (self.run/'report.txt').write_bytes(b'10\n');self.raw['artifacts']['report']['sha256']=digest(self.run/'report.txt');write(self.run/'original-run.json',self.raw)
  # A second run and non-first checker are mandatory, so prefix-only verifiers fail.
  self.run_b=self.ev/'run-b';self.run_b.mkdir();(self.run_b/'report.txt').write_bytes(b'10\n')
  raw_b=copy.deepcopy(self.raw);raw_b.update(run_id='run-b',started=['d','e'],finished=['d','e']);write(self.run_b/'original-run.json',raw_b)
  self.plan['runs'].append({'id':'run-b','cases':['d','e'],'observer':'secondary'})
  self.plan['checks'].extend([{'id':'C2','run_id':'run-b','level':'SYSTEM','checker':'artifact'},{'id':'C3','run_id':'run-b','level':'SYSTEM','checker':'secondary'}])
  self.plan['requirements'].update(B=['C2'],C=['C3']);self.sub['runs'].append({'id':'run-b','evidence_dir':'run-b'})
  self.freeze()
  def observe(spec,directory):
   self.calls.append(('observe',spec['id'],str(directory)));return json.loads((Path(directory)/'original-run.json').read_text())
  def check(spec,observed,directory):
   self.calls.append(('check',spec['id'],str(directory)));data=(Path(directory)/observed['artifacts']['report']['path']).read_bytes();good=data==b'10\n'
   return {'passed':good,'assertions':[{'id':'independent-sum','passed':good}],'facts':{'actual_bytes':data.decode()}}
  self.observers={'original':observe,'secondary':observe};self.checkers={'artifact':check,'secondary':check}
 def freeze(self):
  write(self.root/'baseline.json',self.plan);self.sub['baseline_sha256']=digest(self.root/'baseline.json');write(self.root/'submission.json',self.sub)
 def save_raw(self):write(self.run/'original-run.json',self.raw)
 def call(self):return AUDIT(self.root,self.root/'baseline.json',self.ev,self.root/'submission.json',self.observers,self.checkers)
 def reject(self):
  try:r=self.call()
  except Exception as e:
   self.assertIn(getattr(e,'code',None),{'invalid','missing','conflict','version_mismatch','observation_failed','check_failed','path_invalid'},repr(e));return
  self.assertEqual(r['status'],'FAIL',r);self.assertTrue(r.get('failures'),r)
 def test_V01_complete(self):
  got=self.call();self.assertEqual(got['status'],'PASS',got);self.assertCountEqual([x[:2] for x in self.calls],[('observe','run-a'),('observe','run-b'),('check','C1'),('check','C2'),('check','C3')]);self.assertEqual(len(self.calls),5);self.assertEqual(got['baseline_sha256'],digest(self.root/'baseline.json'));self.assertEqual(set(got['runs']),{'run-a','run-b'});self.assertCountEqual([c['id'] for c in got['checks']],['C1','C2','C3']);self.assertEqual(len(got['checks']),3);self.assertTrue(all(c['passed'] is True and c['assertions'] for c in got['checks']));self.assertEqual(got['requirements'],self.plan['requirements'])
  for rid in ['run-a','run-b']:self.assertEqual(got['runs'][rid],json.loads((self.ev/rid/'original-run.json').read_text()))
  for row in got['checks']:
   self.assertEqual(row['assertions'],[{'id':'independent-sum','passed':True}]);self.assertEqual(row['facts'],{'actual_bytes':'10\n'})
 def test_V02_false_success(self):
  for name in ['run-a','run-b']:
   with self.subTest(failing_run=name):
    self.fresh();self.sub.update(status='PASS',success=True);write(self.root/'submission.json',self.sub);directory=self.ev/name;(directory/'report.txt').write_bytes(b'999\n');raw=json.loads((directory/'original-run.json').read_text());raw['artifacts']['report']['sha256']=digest(directory/'report.txt');write(directory/'original-run.json',raw);self.reject();self.assertTrue(any(c[0]=='check' for c in self.calls))
 def test_V03_requirement_coverage(self):
  for kind in ['missing','extra','empty','duplicate-source','unknown-check','empty-all','duplicate-check','duplicate-run','duplicate-case']:
   with self.subTest(kind=kind):
    self.fresh()
    if kind=='missing':self.plan['requirements'].pop('B')
    if kind=='extra':self.plan['requirements']['OTHER']=['C1']
    if kind=='empty':self.plan['requirements']['B']=[]
    if kind=='unknown-check':self.plan['requirements']['B']=['missing']
    if kind=='empty-all':
     write(self.root/'requirements.json',[]);self.plan['requirements_source']['sha256']=digest(self.root/'requirements.json');self.plan['requirements']={}
    if kind=='duplicate-check':self.plan['checks'].append(copy.deepcopy(self.plan['checks'][0]))
    if kind=='duplicate-run':self.plan['runs'].append(copy.deepcopy(self.plan['runs'][0]))
    if kind=='duplicate-case':self.plan['runs'][0]['cases'].append('a')
    if kind=='duplicate-source':
     write(self.root/'requirements.json',self.requirements+[self.requirements[0]]);self.plan['requirements_source']['sha256']=digest(self.root/'requirements.json')
    self.freeze();self.reject()
 def test_V04_versions(self):
  for kind in ['baseline','requirements','implementation','tests','data','environment']:
   with self.subTest(kind=kind):
    self.fresh();q=self.root/('baseline.json' if kind=='baseline' else 'requirements.json' if kind=='requirements' else kind+'.txt');q.write_bytes(q.read_bytes()+b' ');self.reject()
 def test_V05_run_inventory(self):
  for kind in ['missing','extra','duplicate','missing-nonfirst']:
   with self.subTest(kind=kind):
    self.fresh()
    if kind=='missing':self.sub['runs']=[]
    elif kind=='missing-nonfirst':self.sub['runs']=self.sub['runs'][:1]
    elif kind=='extra':self.sub['runs'].append({'id':'unexpected','evidence_dir':'run-a'})
    else:self.sub['runs'].append(copy.deepcopy(self.sub['runs'][0]))
    write(self.root/'submission.json',self.sub);self.reject()
 def test_V06_execution_inventory(self):
  for field,value in [('started',[]),('finished',['a','b']),('started',['a','b','c','z']),('finished',['a','a','b','c']),('skipped',['b'])]:
   with self.subTest(field=field,value=value):self.fresh();self.raw[field]=value;self.save_raw();self.reject()
 def test_V07_actual_exit(self):
  for value in [1,-9,False,'0',0.0]:
   with self.subTest(value=value):self.fresh();self.raw['exit_code']=value;self.save_raw();self.reject()
 def test_V08_evidence_level(self):
  self.raw['level']='COMPONENT';self.save_raw();self.reject()
 def test_V09_actual_files(self):
  for kind in ['missing','hash','absent-field']:
   with self.subTest(kind=kind):
    self.fresh()
    if kind=='missing':(self.run/'report.txt').unlink()
    elif kind=='hash':self.raw['artifacts']['report']['sha256']='0'*64
    else:self.raw.pop('artifacts')
    self.save_raw();self.reject()
 def test_V10_paths(self):
  for kind in ['traversal','absolute','symlink','binding-escape','run-escape']:
   with self.subTest(kind=kind):
    self.fresh();outside=self.root/'outside.txt';outside.write_bytes(b'10\n')
    if kind=='traversal':self.raw['artifacts']['report']['path']='../../outside.txt'
    elif kind=='absolute':self.raw['artifacts']['report']['path']=str(outside)
    elif kind=='symlink':os.symlink(outside,self.run/'alias');self.raw['artifacts']['report']['path']='alias'
    elif kind=='binding-escape':self.plan['bindings'][0]['path']='../not-authorized';self.freeze()
    else:self.sub['runs'][0]['evidence_dir']='../';write(self.root/'submission.json',self.sub)
    self.save_raw();self.reject()
 def test_V11_callbacks(self):
  def broken(*args):raise RuntimeError('independent observer unavailable')
  for kind in ['missing-observer','missing-checker','observer-error','checker-error','missing-nonfirst-checker','nonfirst-observer-error','nonfirst-checker-error']:
   with self.subTest(kind=kind):
    self.fresh()
    if kind=='missing-observer':self.observers={}
    elif kind=='missing-checker':self.checkers={}
    elif kind=='observer-error':self.observers['original']=broken
    elif kind=='missing-nonfirst-checker':self.checkers.pop('secondary')
    elif kind=='nonfirst-observer-error':self.observers['secondary']=broken
    elif kind=='nonfirst-checker-error':self.checkers['secondary']=broken
    else:self.checkers['artifact']=broken
    self.reject()
 def test_V12_assertions(self):
  valid={'passed':True,'assertions':[{'id':'only','passed':True}],'facts':{}}
  variants=[{'passed':True,'assertions':[],'facts':{}},{'passed':True,'assertions':[{'id':'only','passed':False}],'facts':{}},{'passed':True,'assertions':[{'id':'only','passed':1}],'facts':{}},{'passed':True,'assertions':[{'id':'only','passed':True},{'id':'only','passed':True}],'facts':{}},{'passed':'true','assertions':valid['assertions'],'facts':{}},{**valid,'facts':{'latency':float('nan')}}]
  for v in variants:
   with self.subTest(value=repr(v)):self.fresh();self.checkers['secondary']=lambda *args,v=v:copy.deepcopy(v);self.reject()
 def test_V13_strict_json(self):
  for kind in ['duplicate','nan','infinity','deep-array']:
   with self.subTest(kind=kind):
    self.fresh();q=self.root/'submission.json';s=q.read_text()
    if kind=='deep-array':s=s[:-1]+',"extra":'+'['*1500+'0'+']'*1500+'}'
    elif kind=='duplicate':s=s[:-1]+',"schema":"lore-validation-submission/v1"}'
    else:s=s[:-1]+',"extra":'+('NaN' if kind=='nan' else 'Infinity')+'}'
    q.write_text(s);self.reject()
 def test_V14_untrusted_code_and_repeat(self):
  canary=self.root/'must-not-exist';self.sub['command']=['touch',str(canary)];self.sub['checker']='os.system';write(self.root/'submission.json',self.sub)
  before={str(q.relative_to(self.root)):digest(q) for q in self.root.rglob('*') if q.is_file()};first=self.call();second=self.call();self.assertEqual(first['status'],'PASS',first);self.assertEqual(second['status'],'PASS',second);self.assertFalse(canary.exists());after={str(q.relative_to(self.root)):digest(q) for q in self.root.rglob('*') if q.is_file()};self.assertEqual(before,after)
