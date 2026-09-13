"""Real R facility transitions with explicit scripted S/facts; no Engine/model/NATS."""
import argparse,copy,hashlib,importlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def raw(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(v):return hashlib.sha256(raw(v)).hexdigest()
def need(v,m):
 if not v:raise AssertionError(m)
class Snapshots:
 def __init__(self):self.rows={}
 def query(self,id):return copy.deepcopy(self.rows[id])
def envelope(b):
 return {'owner':'S','session_id':'s','namespace':'n','session_generation':1,'snapshot_ref':b['snapshot_ref'],'original_archive':{'path':'/NoEngine','sha256':'0'*64,'bytes':1},'owner_record_ref':b['owner_record_ref'],'storage_charge_ref':b['storage_charge_ref']}
class Plans:
 def __init__(self,c,s):self.control=c;self.snapshots=s;self.host={'principal':'runtime'};self.calls=[]
 def prepare(self,p,id,*,execution_id):
  self.calls.append(id);return {'node_request':{'protocol':'lore.s/1','action':'accept','session_ref':{'owner':'S','session_id':'s'},'operation_id':id,'harness_ref':{'id':sha({'owner':'F','sha256':'h'}),'sha256':'h'},'input_ref':{'id':'i','sha256':'i'},'source_result_ref':None,'capability_ref':{'id':'c','sha256':'c'}}}
class Facts:
 def __init__(self,s):self.s=s;self.observed={}
 def facility(self,node,eid,cid,stopped,released):
  b=self.s.query(cid);return {'owner':'X','kind':'session_execution','execution_id':eid,'confirmation_request_id':cid,'node_request_digest':sha(node),'session_confirmation':b,'original_stopped_response':stopped,'original_execution_response':released}
 def read(self,facility,node):
  need(facility['node_request_digest']==sha(node),'fake exact original Node binding')
  need(facility['session_confirmation']==self.s.query(facility['confirmation_request_id']),'fake snapshot changed')
  original=self.observed[facility['execution_id']];need(original['node']==node,'fake original request changed')
  return copy.deepcopy(original['facts'])
class Service:
 def __init__(self,c):self.snapshots=Snapshots();self.plans=Plans(c,self.snapshots);self.facts=Facts(self.snapshots);self.calls=[];self.c=c;self.tools=None
 def invoke(self,node,*,execution_id,deadline_monotonic):
  row=self.c.query('runtime',execution_id);need(row['phase']=='issued' and row['payload']['node_request']==node,'S entered before exact R dispatch')
  self.calls.append(node['action']);cid='s-'+sha([execution_id,'s-service-final'])
  full={'owner':'S','session_id':'s','namespace':'n','session_generation':1,'archive_path':'/NoEngine','archive_sha256':'0'*64,'archive_bytes':1}
  b={'snapshot_ref':full,'owner_record_ref':{'fixture':cid},'storage_charge_ref':{'fixture':'charge'}};self.snapshots.rows[cid]=b
  binding={'session_id':'s','session_scope':{'namespace':'n','surface_id':'surface','session_id':'s','session_generation':1},**{k:node[k] for k in ('operation_id','harness_ref','input_ref','source_result_ref','capability_ref')}}
  source={'owner':'S','operation_id':node['operation_id'],'fixture':'original'}
  frame={'type':'result','operation_id':node['operation_id'],'boundary_kind':'accepted'}
  if node['action']=='drive':
   frame.update(boundary_kind='answer_saved',operation_result_ref=source,decision_proposal={'decision_id':'original-decision','source_result_ref':source,'harness_ref':node['harness_ref'],'input_ref':node['input_ref'],'control':{'parent_id':node['operation_id'],'harness_ref':{'owner':'F','sha256':'h'},'body':{'stop_ref':{'owner':'S','kind':'runtime-policy-stop','operation_id':node['operation_id'],'source_result_ref':source,'confirmation_ref':{'owner':'S','kind':'confirmation','confirmation_request_id':cid,'session_scope':binding['session_scope']}}}}})
  result={'frame':frame,'confirmation_request_id':cid,'original_session_snapshot_ref':envelope(b),'stopped':{'fixture':'original-stop','binding':{'execution_id':execution_id}},'released':{'fixture':'original-release','binding':{'execution_id':execution_id}}}
  self.facts.observed[execution_id]={'node':copy.deepcopy(node),'facts':{'frame':frame,'binding':binding,'bundle':b,'confirmation_request_id':cid}}
  return copy.deepcopy(result)
def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args();assert a.batch and all(c.isalnum() or c in '-_' for c in a.batch)
 out=ROOT/'validation/runtime-delivery-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);product=ROOT/'lore_runtime/session_delivery.py';result={'status':'MISSING','cases':[],'scope':'real R, explicit scripted S/Facts'}
 if product.exists():
  from lore_control import ControlStore
  Delivery=importlib.import_module('lore_runtime.session_delivery').SessionDelivery
  before=hashlib.sha256(product.read_bytes()).hexdigest()
  for id in ['SD01','SD02','SD03','SD04','SD05','SD06']:
   path=out/id;path.mkdir();c=ControlStore(path/'R.sqlite',{'runtime':{'namespaces':['n'],'roles':['runtime','admin','submit']}},reference_checker=lambda ref,purpose,expected:purpose=='harness')
   s=Service(c);d=Delivery(c,s,s.facts);prior=c.reference_checker;c.reference_checker=lambda ref,purpose,expected:d.control_reference(ref,purpose,expected) or prior(ref,purpose,expected)
   parent=c.accept('runtime',{'id':'parent','namespace':'n','kind':'invocation','payload':{'harness_ref':{'owner':'F','sha256':'h'}}})
   try:
    if id=='SD03':
     eid='s-exec-'+sha(['parent','accept']);node=s.plans.prepare('runtime','parent',execution_id=eid)['node_request'];c.accept('runtime',{'id':eid,'namespace':'n','kind':'execution','payload':{'parent_id':'parent','action':'accept','execution_id':eid,'node_request':node}});c.mark_dispatched('runtime',eid,'X');need(d.execute(parent,time.monotonic()+3) is None and not s.calls,'issued Session re-executed')
    else:
     source=d.execute(parent,time.monotonic()+3);need(s.calls==['accept','drive'] and source=={'owner':'S','operation_id':'parent','fixture':'original'},'fresh delivery did not preserve original')
     if id=='SD02':
      before_calls=copy.deepcopy((s.calls,s.plans.calls));need(d.execute(parent,time.monotonic()+3)==source and before_calls==(s.calls,s.plans.calls),'confirmed delivery replayed/planned')
     elif id=='SD04':
      bad=copy.deepcopy(parent);bad['payload']['harness_ref']['sha256']='changed'
      try:d.execute(bad,time.monotonic()+3)
      except Exception:pass
      else:raise AssertionError('changed original parent accepted')
     elif id=='SD05':
      parent['result_ref']=source;proposal=d.decision(parent,source);d.validate_decision(parent,proposal);changed=copy.deepcopy(proposal);changed['body']={'stop_ref':{'invented':True}}
      try:d.validate_decision(parent,changed)
      except Exception:pass
      else:raise AssertionError('new body replaces original')
     elif id=='SD06':
      eid='s-exec-'+sha(['parent','drive']);row=c.query('runtime',eid);ref=row['receipt_ref'];expected={k:ref[k] for k in ('request_id','namespace','source','delivery_owner','request_digest')}
      for k,v in [('namespace','other'),('source','other'),('request_digest','bad'),('sha256','bad')]:
       bad=copy.deepcopy(ref);bad[k]=v;need(not d.control_reference(bad,'receipt',expected),'bad original wrapper admitted')
    result['cases'].append({'id':id,'status':'PASS','calls':s.calls})
   except Exception as ex:result['cases'].append({'id':id,'status':'FAIL','error':repr(ex)})
   finally:(path/'R.sql').write_text('\n'.join(c.db.iterdump()));c.close()
  result.update(status='PASS' if all(c['status']=='PASS' for c in result['cases']) else 'FAIL',source_sha256=before,source_unchanged=before==hashlib.sha256(product.read_bytes()).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return 0 if result['status']=='PASS' else 2 if result['status']=='MISSING' else 1
if __name__=='__main__':raise SystemExit(main())
