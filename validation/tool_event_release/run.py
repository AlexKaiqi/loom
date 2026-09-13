"""Actual original R/F/X tool, rejected outbox, retained bytes and exact absence."""
from pathlib import Path
import argparse,asyncio,hashlib,json,sys,traceback
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from validation.tool_service_probe import ToolFixture,raw,save,need,load
from lore_runtime.tool_plans import ToolPlans
from lore_runtime.tool_service import ToolService
from lore_runtime.emissions import EmitService
from validation.system.runtime_observer_sources import EngineRead

def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args();assert Path(a.batch).name==a.batch
 out=Path(__file__).parent/'evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
 paths=[q for pkg in ['lore_runtime','lore_control','lore_files','lore_execution','lore_events','lore_session'] for q in (ROOT/pkg).glob('*.py')]+[Path(__file__),ROOT/'validation/tool_service_probe.py',ROOT/'validation/session_plans_probe.py',ROOT/'validation/components/s/f_peer.py',Path(__file__).parent/'contract.md']
 sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest();before={str(q):sha(q) for q in paths};copies=out/'source-before';copies.mkdir()
 for i,q in enumerate(paths):(copies/(str(i)+'-'+q.name)).write_bytes(q.read_bytes())
 save(out/'source-before.json',before);f=None;checks=[];result={'status':'FAIL'}
 def check(name,condition):checks.append(dict(check=name,passed=bool(condition)))
 try:
  import validation.session_plans_probe as fixture_module
  fixture_root=out/'fixture-resources';fixed=ROOT/'validation/session-plan-evidence/context-independent-001/workspace/original-host';sources=[]
  for name in ['dependencies-manifest.json','profile.json','request-template.json']:
   source=fixed/name;dest=fixture_root/'original-host'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes());sources.append(dict(path=str(source),copy=str(dest),sha256=sha(source)))
  source=ROOT/'lore_session/node/entry.mts';dest=fixture_root/'lore_session/node/entry.mts';dest.parent.mkdir(parents=True);dest.write_bytes(source.read_bytes());sources.append(dict(path=str(source),copy=str(dest),sha256=sha(source)))
  save(out/'fixed-fixture-sources.json',sources);fixture_module.ROOT=fixture_root
  f=ToolFixture(out/'actual',ToolPlans,ToolService)
  script="mkdir -p .lore; printf '%s\n' '{\"id\":1,\"name\":\"surface.registered\",\"payload\":{\"origin\":\"system\"}}' >> .lore/emit-requests.jsonl; printf 'rejected-outbox-original\n'"
  binding,frame,original=f.pending(script=script);service=f.service_with();emitter=EmitService(None,service.resolve_tool_source);calls=[]
  def emit(*args):
   try:return asyncio.run(emitter.publish(*args))
   except Exception as e:calls.append(dict(type=type(e).__name__,code=getattr(e,'code',None),message=str(e)));raise
  service.emission_submit=emit
  response=service.execute(binding,frame,original);eid=frame['effect_id'];record=f.execution.journal.get(eid);r=f.f.control.query(f.f.principal,eid)
  save(out/'original-response.json',response);save(out/'original-R.json',r);save(out/'original-X.json',record);save(out/'actual-emission-errors.json',calls)
  check('original malformed outbox rejected after exactly one source check',len(calls)==1 and calls[0]['type']=='EventError' and calls[0]['code']=='invalid' and 'trusted source' in calls[0]['message'])
  check('UNKNOWN responsibility retained without positive receipt',response['status']=='UNKNOWN' and r['phase']=='issued' and r['receipt_ref'] is None)
  installed=f.f.peer.store.query_install('tool-install-'+eid);save(out/'original-F-query.json',installed)
  cp=record['artifacts']['checkpoint'];bundle=f.f.peer.store.journal.get('tool-import-'+eid)['result']
  check('original complete archive retained after publication',f.f.peer.store.versions.load(bundle['version_ref'])[0]==Path(cp['path']).read_bytes())
  check('actual source contains malicious original outbox',b'"origin":"system"' in (Path(r['payload']['plan']['resource']['path'])/'.lore/emit-requests.jsonl').read_bytes())
  check('original stdout retained',Path(record['artifacts']['stdout']['path']).read_bytes()==b'rejected-outbox-original\n')
  engine=EngineRead('unix://'+f.execution.engine.path);b=record['binding'];observed={k:engine.get(u) for k,u in [('container','/containers/'+b['container_id']+'/json'),('volume','/volumes/'+b['volume_id'])]};save(out/'actual-absence-before-cleanup.json',observed)
  check('X original released',record.get('released') is True);check('exact original CID/volume physically absent',all(v['status']==404 for v in observed.values()))
  sql='\n'.join(f.f.control.db.iterdump());x=raw(record);old_calls=list(calls)
  query=service.query(eid,binding);again=service.execute(binding,frame,original)
  check('query and duplicate execute no effects or state changes',query['status']==again['status']=='UNKNOWN' and old_calls==calls and sql=='\n'.join(f.f.control.db.iterdump()) and x==raw(f.execution.journal.get(eid)))
  result.update(checks=checks,status='PASS_COMPONENT_ONLY' if all(c['passed'] for c in checks) else 'FAIL')
 except Exception as e:result.update(error=repr(e),traceback=traceback.format_exc(),checks=checks)
 finally:
  save(out/'assessment-before-cleanup.json',result)
  if f and f.execution:
   cleanup=[]
   for q in f.execution.journal.root.glob('*/record.json'):
    r=load(q);b=r.get('binding',{})
    for kind,id in [('container',b.get('container_id')),('volume',b.get('volume_id'))]:
     if not id:continue
     url='/containers/'+id+'?force=1' if kind=='container' else '/volumes/'+id
     f.execution.engine.call('DELETE',url,missing=True)
     got=EngineRead('unix://'+f.execution.engine.path).get('/containers/'+id+'/json' if kind=='container' else '/volumes/'+id)
     cleanup.append(dict(kind=kind,id=id,after=got));need(got['status']==404,'exact fixture cleanup absent proof missing')
   save(out/'cleanup.json',cleanup)
  if f:f.close()
  result['source_unchanged']=all(sha(Path(q))==h for q,h in before.items());save(out/'result.json',result)
 print(json.dumps(result));return 0 if result['status']=='PASS_COMPONENT_ONLY' and result['source_unchanged'] else 1
if __name__=='__main__':raise SystemExit(main())
