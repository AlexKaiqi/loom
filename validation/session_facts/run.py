"""Original live S/X facts; derived fault files are never claimed as real executions."""
import argparse,copy,hashlib,importlib,io,json,shutil,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from lore_session.snapshots import SnapshotStore
from lore_session.snapshot_files import canonical,sha,archive,decode,SCOPE,EXEC
from lore_execution.engine import Engine
D=copy.deepcopy

def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def digest(p):return sha(Path(p).read_bytes())
def watched(protocol):
 roots=[Path(protocol['execution_root']),Path(protocol['snapshot_root'])]
 paths=[Path(protocol['source'])]+[p for root in roots for p in root.rglob('*') if p.is_file()]
 return {str(p):digest(p) for p in sorted(paths)}
class Reads:
 def __init__(self,engine,mode=None):self.engine=engine;self.mode=mode;self.calls=[]
 def inspect(self,cid):
  value=self.engine.inspect(cid);self.calls.append({'method':'GET','path':'/containers/'+cid+'/json','actual':D(value)})
  return {'Id':cid,'State':{'Running':True}} if self.mode=='container' else value
 def call(self,method,path,missing=False):
  assert method=='GET' and path.startswith('/volumes/') and missing is True
  value=self.engine.call(method,path,missing=True);self.calls.append({'method':method,'path':path,'actual':D(value)})
  return {'Name':path.split('/')[-1]} if self.mode=='volume' else value

def owner(protocol,root=None):
 return SnapshotStore(root or Path(protocol['snapshot_root']),protocol['namespace'],lambda *args:(_ for _ in ()).throw(AssertionError('read path tried to publish owner')),global_budget_bytes=protocol['global_budget_bytes'])
def factory(cls,store,execution_root,engine,item):
 r=item['result'];return cls(store,execution_root,engine).facility(item['request'],r['stopped']['binding']['execution_id'],r['confirmation_request_id'],r['stopped'],r['released'])
def rejected(call):
 try:call()
 except Exception as exc:
  assert getattr(exc,'code',None)=='reference_invalid',repr(exc)
  return {'code':exc.code,'message':str(exc)}
 raise AssertionError('invalid original was accepted')

def derived(home,item,kind,protocol):
 """Copy X fact files and retain a derived archive through actual S, not an Engine execution."""
 home.mkdir();r=D(item['result']);eid=r['stopped']['binding']['execution_id'];original_dir=Path(r['checkpoint_ref']['path']).parent
 xroot=home/'X';xdir=xroot/sha(eid.encode());shutil.copytree(original_dir,xdir)
 record=decode((xdir/'record.json').read_bytes());cp=D(r['checkpoint_ref']);cp['path']=str(xdir/'derived-checkpoint.blob')
 snap=r['original_session_snapshot_ref'];oldowner=decode(Path(snap['owner_record_ref']['path']).read_bytes());descriptor={'jsonl_relative_path':oldowner['original_session']['jsonl']['relative_path'],'metadata_relative_path':'metadata.json','binding_namespace':'lore.s.binding','binding_key':item['request']['operation_id'],'binding':oldowner['original_session']['binding']}
 raw=Path(snap['snapshot_ref']['archive_path']).read_bytes()
 if kind in ('missing-boundary','paused-result'):
  output=io.BytesIO()
  with tarfile.open(fileobj=io.BytesIO(raw)) as src,tarfile.open(fileobj=output,mode='w',format=tarfile.PAX_FORMAT) as dst:
   for member in src:
    data=src.extractfile(member).read() if member.isfile() else None
    if member.name.removeprefix('./')==descriptor['jsonl_relative_path']:
     lines=data.splitlines(keepends=True);kept=[lines[0]]
     for line in lines[1:]:
      rows=json.loads(line);rows=rows if type(rows) is list else [rows]
      if any(q.get('namespace')=='lore.s.boundary' and q.get('key')==item['request']['operation_id'] for q in rows):
       assert len(rows)==1,'do not drop other original transaction members'
      else:kept.append(line)
     data=b''.join(kept);member.size=len(data)
     cp['members'][descriptor['jsonl_relative_path']].update(size=len(data),sha256=sha(data))
    dst.addfile(member,io.BytesIO(data) if data is not None else None)
  raw=output.getvalue()
 Path(cp['path']).write_bytes(raw);cp.update(sha256=sha(raw),size=len(raw))
 scope={**oldowner['scope'],'original_execution':{**{k:cp['source_binding'][k] for k in EXEC},'state':cp['state']}}
 store=SnapshotStore(home/'S',protocol['namespace'],lambda *args:None,global_budget_bytes=protocol['global_budget_bytes']);confirmation='derived-'+kind
 bundle=(store.quarantine(confirmation,scope,cp,'explicit derived quarantine control') if kind=='quarantine' else store.confirm(confirmation,scope,cp,descriptor))
 receipt=store.receipt('derived-receipt-'+kind,cp,bundle,sealed=True);Path(cp['path']).unlink()
 def remap(value):
  if type(value) is str and value.startswith(str(original_dir)+'/'):return str(xdir)+value[len(str(original_dir)):]
  if type(value) is dict:return {k:remap(v) for k,v in value.items()}
  if type(value) is list:return [remap(v) for v in value]
  return value
 # Preserve exact original X request and binding. Only copied fact/source paths change.
 record['calls']=remap(record['calls']);record['artifacts']=remap(record['artifacts']);record['artifacts']['checkpoint']=cp
 oldproof=decode(Path(r['stopped']['artifacts']['stopped']['path']).read_bytes());oldproof['prepared_ref']=cp
 if kind=='wrong-proof':oldproof['object_generation']+=1
 proofpath=xdir/'derived-stopped.blob';proofpath.write_bytes(canonical(oldproof));record['artifacts']['stopped']={'path':str(proofpath),'size':proofpath.stat().st_size,'sha256':digest(proofpath)}
 if kind in ('raw-frame','paused-result'):
  stdout=Path(record['artifacts']['stdout']['path']);rows=stdout.read_bytes().splitlines();last=json.loads(rows[-1])
  if kind=='raw-frame':last['decision_proposal']['final']['content'][0]['text']='changed raw original answer'
  else:last={k:last[k] for k in ('type','operation_id','operation_result_ref')};last['boundary_kind']='paused_reconciliation_required'
  stdout.write_bytes(b'\n'.join(rows[:-1]+[canonical(last)])+b'\n');record['artifacts']['stdout'].update(size=stdout.stat().st_size,sha256=digest(stdout))
 record['checkpoints']={'derived-final':{'purpose':'original_session','artifact':cp,'state':'PREPARED','retention':{'state':'RELEASED','release_id':receipt['receipt_id'],'owner_receipt_ref':receipt}}}
 def response(old):
  value={k:D(record[k]) for k in ('binding','result','artifacts')}
  ref=D(old['artifacts']['slot']);destination=xroot/'.slots'/Path(ref['path']).parent.name;destination.mkdir(parents=True,exist_ok=True);new=destination/Path(ref['path']).name
  shutil.copyfile(ref['path'],new);ref['path']=str(new);value['artifacts']['slot']=ref
  return value
 stopped,released=response(r['stopped']),response(r['released']);record['artifacts']['slot']=stopped['artifacts']['slot'];save(xdir/'record.json',record)
 derived_item=D(item);derived_item['result'].update(confirmation_request_id=confirmation,stopped=stopped,released=released)
 save(home/'DERIVED-NOT-AN-EXECUTION.json',{'source_execution_id':eid,'kind':kind,'original_archive_sha256':digest(snap['snapshot_ref']['archive_path']),'derived_archive_sha256':sha(raw),'copied_record_sha256':digest(xdir/'record.json')})
 return store,xroot,derived_item

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);a=ap.parse_args();assert a.batch and all(c.isalnum() or c in '-_' for c in a.batch)
 out=HERE/'evidence'/a.batch;out.mkdir(parents=True);protocol=json.loads((HERE/'protocol.json').read_bytes());assert digest(protocol['source'])==protocol['source_sha256']
 source_files=[HERE/'run.py',HERE/'protocol.json',ROOT/'design/g3/system/session-facts.md']+list((ROOT/'lore_session').glob('*.py'))+[ROOT/'lore_execution/engine.py',ROOT/'lore_execution/journal.py',ROOT/'lore_execution/profile.json',ROOT/'lore_execution/seccomp.json']
 candidate=ROOT/'lore_runtime/session_facts.py'
 if candidate.exists():source_files.append(candidate)
 source_before={str(p):digest(p) for p in source_files}
 try:cls=importlib.import_module('lore_runtime.session_facts').SessionFacts
 except ModuleNotFoundError as exc:
  if exc.name!='lore_runtime.session_facts':raise
  save(out/'result.json',{'status':'MISSING','tests_run':0,'source_before':source_before});print('MISSING 0');return 2
 original_before=watched(protocol);items=json.loads(Path(protocol['source']).read_bytes());engine=Reads(Engine('unix:///run/docker.sock'));store=owner(protocol);checks=[];facilities=[];rejections={}
 def check(id,run):
  try:run();checks.append({'id':id,'passed':True})
  except Exception as exc:checks.append({'id':id,'passed':False,'error':repr(exc)})
 def positives():
  for i,item in enumerate(items):
   facility=factory(cls,store,protocol['execution_root'],engine,item);observed=cls(store,protocol['execution_root'],engine).read(facility,item['request']);facilities.append(facility)
   assert observed['frame']==item['result']['frame'] and observed['bundle']==store.query(item['result']['confirmation_request_id'])
   assert observed['binding']==decode(Path(observed['bundle']['owner_record_ref']['path']).read_bytes())['original_session']['binding']
   assert facility['original_stopped_response']==item['result']['stopped'] and facility['original_execution_response']==item['result']['released']
   save(out/('original-'+str(i)+'.json'),{'facility':facility,'read':observed})
 def bindings():
  base=factory(cls,store,protocol['execution_root'],engine,items[1]);sut=cls(store,protocol['execution_root'],engine)
  changes=[('execution',lambda f,n:f.update(execution_id='absent-original')),
   ('existing-execution',lambda f,n:f.update(execution_id=items[2]['result']['stopped']['binding']['execution_id'])),
   ('namespace',lambda f,n:n['session_ref'].update(namespace='wrong')),
   ('operation',lambda f,n:n.update(operation_id='wrong')),
   ('source',lambda f,n:n.update(source_result_ref={'owner':'S','wrong':'source'})),
   ('action',lambda f,n:n.update(action='accept')),
   ('confirmation',lambda f,n:f.update(confirmation_request_id=items[0]['result']['confirmation_request_id'])),
   ('node-digest',lambda f,n:f.update(node_request_digest='0'*64)),
   ('raw-result',lambda f,n:f['original_execution_response']['result'].update(exit_code=49)),
   ('full-binding',lambda f,n:f['original_stopped_response']['binding'].update(freeze_generation=999)),
   ('raw-stdout-hash',lambda f,n:f['original_execution_response']['artifacts']['stdout'].update(sha256='0'*64))]
  for name,change in changes:
   f,n=D(base),D(items[1]['request']);change(f,n)
   if name in ('namespace','operation','source','action'):f['node_request_digest']=sha(canonical(n))
   rejections[name]=rejected(lambda:sut.read(f,n))
  assert not (Path(protocol['execution_root'])/sha(b'absent-original')).exists()
 def physical():
  for name in ('container','volume'):
   monitor=Reads(engine.engine,name);rejections[name]=rejected(lambda:factory(cls,store,protocol['execution_root'],monitor,items[0]));assert monitor.calls
   save(out/('declared-present-'+name+'.json'),{'control':'DECLARED_PRESENT_CONTROL_NOT_ACTUAL_LIVE_OBJECT','original_reads':monitor.calls})
 def cross():
  for kind in ('missing-boundary','raw-frame','quarantine','wrong-proof','paused-result'):
   own,xroot,item=derived(out/kind,items[1],kind,protocol);sut=cls(own,xroot,engine)
   if kind=='paused-result':
    f=factory(cls,own,xroot,engine,item);r=sut.read(f,item['request']);assert r['frame']['boundary_kind']=='paused_reconciliation_required' and 'decision_proposal' not in r['frame'] and r['frame']['operation_result_ref']==items[1]['result']['frame']['operation_result_ref'];save(out/'paused-read.json',r)
   else:rejections[kind]=rejected(lambda:factory(cls,own,xroot,engine,item))
 check('SF01-original-nine',positives);check('SF02-binding-controls',bindings);check('SF03-physical-controls',physical);check('SF04-original-cross-check-controls',cross)
 after=watched(protocol);source_after={str(p):digest(p) for p in source_files};valid=all(c['passed'] for c in checks) and original_before==after and source_before==source_after
 save(out/'result.json',{'status':'PASS' if valid else 'FAIL','tests_run':len(checks),'checks':checks,'scope':protocol['scope'],'source_before':source_before,'source_after':source_after,'source_unchanged':source_before==source_after,'original_files':original_before,'original_unchanged':original_before==after,'engine_reads':engine.calls,'rejections':rejections})
 print(json.dumps({'status':'PASS' if valid else 'FAIL','checks':checks}));return 0 if valid else 1
if __name__=='__main__':raise SystemExit(main())
