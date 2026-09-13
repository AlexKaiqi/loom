"""M04 comparisons over existing independent owner/Engine/Pi readers."""
import base64,copy,json
from pathlib import Path
from validation.runtime_recovery.facts import snapshot as owner_snapshot
from validation.runtime_security.observations import files,EngineRead
from validation.runtime_security.fixtures import save
from validation.system.runtime_observer_sources import refraw,tar_files,raw_value,digest
from validation.components.s.oracle import pi_jsonl

def snapshot(config,sample,http,out):
    out=Path(out);value=owner_snapshot(config,sample,http,out)
    value['state']['E_input_files']=files(Path(config['runtime']['event_profile']['input_root']))
    objects=json.loads((out/'original-X-objects.json').read_bytes());engine=EngineRead(config['runtime']['engine_endpoint'])
    for row in objects:
        b=row['record']['binding'];row['volume']=engine.get('/volumes/'+b['volume_id'])
    save(out/'original-X-objects.json',objects);value['objects']=objects;save(out/'facts.json',value);return value

def parent(facts,rid):return next(r for r in facts['state']['R']['requests'] if r['id']==rid)
def saved(config,bundle,source,out):
    root=config['runtime']['session_dir'];full=bundle['snapshot_ref'];raw=refraw(dict(path=full['archive_path'],sha256=full['archive_sha256'],bytes=full['archive_bytes']),root,18874368)
    members,_=tar_files(raw);data=members[source['session_relative_path']];observed=pi_jsonl(data);op=source['operation_id']
    result=raw_value(data,'pi.result',op);boundary=raw_value(data,'lore.s.boundary',op);owner=json.loads(refraw(bundle['owner_record_ref'],root))
    if owner.get('retention_only',False) or digest(result)!=source['result_sha256']:raise AssertionError('normal original Pi result/owner differs')
    if digest(data)!=source['session_sha256'] or len(data)!=source['session_bytes']:raise AssertionError('original Session bytes differ')
    out=Path(out);out.mkdir();(out/'session.jsonl').write_bytes(data);(out/'pi-result.value').write_bytes(result);(out/'boundary.value').write_bytes(boundary)
    value=dict(bundle=bundle,owner=owner,source=source,jsonl_sha256=digest(data),jsonl_bytes=len(data),result_bytes_b64=base64.b64encode(result).decode(),boundary=json.loads(boundary),binding=observed['values']['lore.s.binding'][op],counts=observed['counts'])
    save(out/'facts.json',value);return value

def unchanged_old(before,after):return all(after.get(k)==v for k,v in before.items())
def absent(facts):return bool(facts['objects']) and all(o['record'].get('released') is True and o['container']['status']==o['volume']['status']==404 for o in facts['objects'])
def assess(rid,killed,before,after_read,after_node,after_drive,read,node,drive,old_pi,new_pi,old_dispatch,new_dispatch,read_dispatch,drive_dispatch):
    checks=[]
    def check(name,value):checks.append(dict(check=name,passed=value is True))
    old=parent(before,rid);restored=parent(after_node,rid);current=parent(after_drive,rid)
    check('result_saved original process killed/reaped',killed['returncode']==-9 and killed['cut']['label']=='result_saved' and killed['cut']['value']['id']==rid and killed['cut']['pid']==killed['pid'])
    check('saved result with nonempty undecided responsibility',old['phase']=='decide' and old['result_ref']==old_pi['source'] and before['state']['R']['decisions']==[] and set(old_pi['boundary']['decision_proposal']['control']['body'])=={'stop_ref'})
    check('old real containers and volumes absent before new Runtime',absent(before) and len(old_dispatch)==len(before['objects'])==2)
    check('fresh Runtime query only preserves complete originals',read['status']=='OBSERVED_QUERY' and read['pid']!=killed['pid'] and before['state']==after_read['state'] and read_dispatch==[] and before['counts']==after_read['counts'])
    check('fresh explicit Session query retains pending R responsibility',node['status']=='OBSERVED_SESSION_QUERY' and node['pid'] not in (killed['pid'],read['pid']) and node['query_before']==node['query_after'] and old==restored and before['state']['R']==after_node['state']['R'])
    check('new restored Pi result and all original JSONL bytes same',old_pi['result_bytes_b64']==new_pi['result_bytes_b64'] and old_pi['jsonl_sha256']==new_pi['jsonl_sha256'] and old_pi['jsonl_bytes']==new_pi['jsonl_bytes'] and old_pi['binding']==new_pi['binding'])
    check('returned result is original saved boundary',node['evidence']['frame']==dict(type='result',operation_id=rid,**old_pi['boundary']))
    check('no Node effect callbacks on saved result query',node['callbacks']==[])
    new=[o for o in after_node['objects'] if o['record']['binding']['execution_id']==node['execution_id']]
    check('one new Node container actual live at dispatch',len(new)==len(new_dispatch)==1 and new_dispatch[0]['container']['status']==new_dispatch[0]['exec']['status']==200 and new_dispatch[0]['exec']['body']['ContainerID']==new_dispatch[0]['binding']['container_id'] and new_dispatch[0]['container']['body']['State']['Running'] is True)
    if len(new)==1 and len(new_dispatch)==1:
        b=new[0]['record']['binding'];old_bindings=[x['record']['binding'] for x in before['objects']]
        check('new physical identity differs from every old object',all(b['container_id']!=x['container_id'] and b['volume_id']!=x['volume_id'] and b['exec_id']!=x['exec_id'] for x in old_bindings))
        cp=new_pi['owner']['source']['original_checkpoint_full_ref'];check('normal new S owner binds actual query execution',new_pi['owner']['scope']==old_pi['owner']['scope'] and cp['source_binding']['execution_id']==node['execution_id'] and cp['source_binding']['container_id']==b['container_id'])
        check('actual query binding and original accepted compact input',new[0]['record']['request']['schema_version']==2 and new[0]['record']['request']['domain']=='session' and new[0]['record']['request']['session_binding']==old_pi['binding']['session_scope'] and new[0]['record']['request']['source_result']==old_pi['binding']['source_result_ref'])
    check('all old immutable owner files retained after new Node query',all(unchanged_old(before['state'][k],after_node['state'][k]) for k in ('S_files','F_files','provider_files','host_authority')) and before['state']['domains']==after_node['state']['domains'] and before['state']['E_input_files']==after_node['state']['E_input_files'])
    check('new read environment actually released too',absent(after_node))
    check('only original one fixed provider and zero tools/exchanges/effects',all(f['counts']==dict(HTTP=1,tools=0,exchanges=0,effects=0) for f in (before,after_read,after_node,after_drive)) and all(f['provider_prepared']==before['provider_prepared'] for f in (after_read,after_node,after_drive)))
    check('recovery drive respects original lease and creates no Node',drive['status']=='OBSERVED_DRIVE' and drive['actual_start']>=drive['lease_before'] and drive_dispatch==[])
    decisions=after_drive['state']['R']['decisions'];check('original pending decision completed exactly once',current['phase']=='settled' and current['result_ref']==old['result_ref'] and len(decisions)==1 and decisions[0]['applied']==1 and decisions[0]['body']==old_pi['boundary']['decision_proposal']['control']['body'])
    old_other={x['id']:x for x in after_node['state']['R']['requests'] if x['id']!=rid};new_other={x['id']:x for x in after_drive['state']['R']['requests'] if x['id']!=rid}
    check('drive preserves original facilities and no extra responsibility',old_other==new_other and all(after_node['state']['R'][k]==after_drive['state']['R'][k] for k in after_node['state']['R'] if k not in ('requests','decisions')))
    check('drive does not rewrite prior X S F input provider facts',all(after_node['state'][k]==after_drive['state'][k] for k in after_node['state'] if k not in ('R','R_auxiliary')))
    return checks
