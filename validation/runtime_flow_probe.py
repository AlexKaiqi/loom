"""Finite original R orchestration checks with explicit NoEngine S/E fixtures."""
import argparse,asyncio,copy,hashlib,importlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def save(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")
def need(v,m):
 if not v:raise AssertionError(m)
class Interrupted(BaseException):pass
class Events:
 def __init__(self,c):self.control=c;self.profile={'input_root':'/unused-noengine','page_size':16};self.calls=[]
 async def prepare_input(self,source,id,ns,start,filters,target_dir,*,input_context):
  self.calls.append(id);row=self.control.query(source,id);ref={'owner':'E','kind':'input','id':id}
  self.control.bind_input('runtime',id,row['payload']['input_binding'],ref);return ref
class Delivery:
 def __init__(self,c,delay=0):self.c=c;self.calls=[];self.queries=[];self.delay=delay;self.bad=False;self.decisions_checked=[]
 def execute(self,row,deadline):
  self.calls.append(row['id']);time.sleep(self.delay);return self.query(row)
 def query(self,row):
  self.queries.append(row['id'])
  if row['id']=='unknown':return None
  return {'owner':'S','operation_id':row['id'],'original':'NoEngine-original-'+row['id']}
 def decision(self,row,source):
  if row['id']=='no-control':return None
  body={'stop_ref':{'owner':'S','original':row['id']}}
  if row['id']=='first':body={'successors':[request('next',row['namespace'])]}
  return {'decision_id':'decision-'+row['id'],'source_ref':source,'harness_ref':{'owner':'F','id':'h'},'body':body}
 def validate_decision(self,row,proposal):
  self.decisions_checked.append(row['id'])
  need(not self.bad and proposal==self.decision(row,row['result_ref']),'external original body differs')
def request(id,ns='one'):
 return {'id':id,'namespace':ns,'kind':'invocation','payload':{'harness_ref':{'owner':'F','id':'h'},'input_binding':{'namespace':ns,'source':'runtime','start_sequence':1,'filters':{},'page_size':16,'surface_ref':{'fixture':ns},'previous_session_ref':None,'execution_targets':[]}}}
def fixture(path,Flow,delay=0,hook=None):
 from lore_control import ControlStore
 def check(ref,purpose,expected):
  if purpose=='harness':return ref=={'owner':'F','id':'h'}
  if purpose=='input':return ref=={'owner':'E','kind':'input','id':expected['invocation_id']}
  if purpose=='result':return ref.get('owner')=='S' and ref.get('original')=='NoEngine-original-'+ref.get('operation_id','')
  if purpose=='stop':return ref.get('owner')=='S' and ref.get('original')==expected['parent_id']
  return False
 c=ControlStore(path/'R.sqlite',{'runtime':{'namespaces':['one','two'],'roles':['runtime','submit','admin']}},reference_checker=check,lease_seconds=.09)
 e=Events(c);d=Delivery(c,delay);f=Flow(c,e,d,'worker',checkpoint=hook);return c,e,d,f
async def case(id,path,Flow):
 c,e,d,f=fixture(path,Flow,delay=.12 if id=='RF02' else 0)
 try:
  if id=='RF01':
   f.start('runtime',request('first'));need(not d.calls and not e.calls,'start dispatched an effect')
   value=await f.drive_until('runtime','first',deadline_monotonic=time.monotonic()+3)
   need(d.calls==['first','next'] and e.calls==['first','next'],'original explicit successor flow differs')
   need(all(row['phase']=='settled' for row in value['requests']),'original handoff unsettled')
  elif id=='RF02':
   f.start('runtime',request('earlier','two'));f.start('runtime',request('target'));renewals=[];old=c.renew
   def renew(*a):renewals.append(a);return old(*a)
   c.renew=renew
   await f.drive_until('runtime','target',deadline_monotonic=time.monotonic()+3)
   need(d.calls==['earlier','target'] and len(renewals)>=2,'fair claim or live lease renewal omitted')
  elif id=='RF03':
   f.start('runtime',request('saved'))
   def hook(label,value):
    if label=='decision_accepted':raise Interrupted()
   f.checkpoint=hook
   try:await f.drive_until('runtime','saved',deadline_monotonic=time.monotonic()+3)
   except Interrupted:pass
   else:raise AssertionError('interrupt cut not reached')
   time.sleep(.1);g=Flow(c,e,d,'recovery')
   await g.drive_until('runtime','saved',deadline_monotonic=time.monotonic()+3)
   need(d.calls==['saved'] and c.query('runtime','saved')['phase']=='settled','recovery reexecuted or lost decision')
  elif id=='RF04':
   for name in ('unknown','no-control'):
    f.start('runtime',request(name));await f.drive_until('runtime',name,deadline_monotonic=time.monotonic()+3)
    need(c.query('runtime',name)['phase']=='paused','missing original was interpreted as a decision')
    await f.drive_until('runtime',name,deadline_monotonic=time.monotonic()+3)
   need(d.calls==['unknown','no-control'] and c.db.execute('SELECT count(*) FROM decisions').fetchone()[0]==0,'paused source retried or invented decision')
  elif id=='RF05':
   d.bad=True;f.start('runtime',request('bad-body'));await f.drive_until('runtime','bad-body',deadline_monotonic=time.monotonic()+3)
   need(c.query('runtime','bad-body')['phase']=='paused' and c.db.execute('SELECT count(*) FROM decisions').fetchone()[0]==0,'bad source admitted')
  else:
   f.start('runtime',request('readonly'));await f.drive_until('runtime','readonly',deadline_monotonic=time.monotonic()+3)
   before=c.db.total_changes;calls=copy.deepcopy((d.calls,d.queries,e.calls));first=f.query('runtime','readonly');second=f.query('runtime','readonly')
   await f.drive_until('runtime','readonly',deadline_monotonic=time.monotonic()+3)
   need(first==second and before==c.db.total_changes and calls==(d.calls,d.queries,e.calls),'query/repeated drive wrote or called facility')
  need(len(d.decisions_checked)>=2 if id=='RF01' else True,'both original decision checks missing')
  return {'id':id,'status':'PASS','calls':d.calls,'input_calls':e.calls,'decision_checks':d.decisions_checked,'requests':[dict(r) for r in c.db.execute('SELECT id,phase FROM requests')]}
 finally:(path/'R.sql').write_text('\n'.join(c.db.iterdump()));c.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args();assert a.batch and all(x.isalnum() or x in '-_' for x in a.batch)
 out=ROOT/'validation/runtime-flow-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);target=ROOT/'lore_runtime/flow.py';result={'status':'MISSING','scope':'real R, explicit NoEngine S/E fixtures','cases':[]}
 if target.exists():
  before=hashlib.sha256(target.read_bytes()).hexdigest();Flow=importlib.import_module('lore_runtime.flow').RuntimeFlow
  for id in ['RF01','RF02','RF03','RF04','RF05','RF06']:
   path=out/id;path.mkdir()
   try:row=asyncio.run(case(id,path,Flow))
   except Exception as ex:row={'id':id,'status':'FAIL','error':repr(ex)}
   result['cases'].append(row)
  result.update(status='PASS' if all(x['status']=='PASS' for x in result['cases']) else 'FAIL',source_sha256=before,source_unchanged=before==hashlib.sha256(target.read_bytes()).hexdigest())
 save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 2 if result['status']=='MISSING' else 1
if __name__=='__main__':raise SystemExit(main())
