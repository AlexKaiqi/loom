"""Independent reads of real cut effects and original owner stores, without executing Pi."""
import base64,hashlib,json,os
from pathlib import Path
from validation.runtime_security.observations import original_state,files,EngineRead
from validation.runtime_security.fixtures import save,sha

def identity(path):
    s=Path(path).lstat();return dict(dev=s.st_dev,ino=s.st_ino)

def snapshot(config,sample,http,out):
    out=Path(out);out.mkdir(exist_ok=True);state=original_state(config)
    state['S_files']=files(Path(config['runtime']['session_dir']));state['F_files']=files(Path(config['runtime']['files_dir']))
    state['host_authority']=files(Path(config['startup_root'])/'authority')
    state['provider_files']=files(Path(config['provider']['root']))
    state['domains']={d:dict(root=identity(sample[d]),files=files(Path(sample[d]))) for d in ('surface','workspace')}
    save(out/'original-owners.json',state)
    tools=[];engine=EngineRead(config['runtime']['engine_endpoint']);objects=[]
    for path in Path(config['runtime']['execution_dir']).glob('*/record.json'):
        record=json.loads(path.read_bytes());b=record['binding']
        proof=dict(path=str(path),sha256=sha(path),record=record)
        if b.get('container_id'):proof['container']=engine.get('/containers/'+b['container_id']+'/json')
        if b.get('exec_id'):proof['exec']=engine.get('/exec/'+b['exec_id']+'/json')
        objects.append(proof)
        if record['request']['schema_version']==1:tools.append(proof)
    save(out/'original-X-objects.json',objects)
    installs=[]
    for path in (Path(config['runtime']['files_dir'])/'requests').glob('*.json'):
        record=json.loads(path.read_bytes())
        if record.get('inputs',{}).get('operation')!='install':continue
        intent=record['inputs']['intent'];a,b=Path(intent['binding']['path']),Path(intent['staged_path'])
        row=dict(path=str(path),sha256=sha(path),record=record,current=identity(a),retired=identity(b))
        row['actually_exchanged']=(row['current'],row['retired'])==(intent['staged_root'],intent['binding']['root'])
        installs.append(row)
    effect=Path(sample['workspace'])/'effects.log';body=effect.read_bytes();(out/'effects.body').write_bytes(body)
    providers=[]
    for path in Path(config['provider']['root']).rglob('prepared.json'):
        providers.append(dict(path=str(path),sha256=sha(path),body=json.loads(path.read_bytes())))
    counts=dict(HTTP=len(http.records),tools=len(tools),exchanges=sum(x['actually_exchanged'] for x in installs),effects=body.count(b'M03_EFFECT\n'))
    value=dict(state=state,counts=counts,tools=tools,installs=installs,effect_bytes_b64=base64.b64encode(body).decode(),provider_prepared=providers,HTTP_originals=http.records,HTTP_errors=http.errors)
    save(out/'facts.json',value);return value

def assess(sample,spec,killed,before,after,recovered,query,drive,dispatches,original_request,query_dispatches,drive_dispatches):
    checks=[]
    def check(name,value):checks.append(dict(check=name,passed=value is True))
    expected=spec['expected'];rid=sample['id']+'-invocation'
    check('exact Runtime process SIGKILL and reaped',killed['returncode']==-9 and killed['cut']['pid']==killed['pid'] and killed['cut']['pgid']==killed['pid'])
    check('new process queried same original ID',query.get('status')=='OBSERVED_QUERY' and query['pid']!=killed['pid'] and any(x['id']==rid for x in query.get('reply',{}).get('requests',[])))
    check('query preserved all original stores and domains',before['state']==after['state'])
    check('query actual dispatch observation explicitly empty',query_dispatches==[])
    check('query performed no repeated actual effects',before['counts']==after['counts'] and before['provider_prepared']==after['provider_prepared'])
    parent=next((x for x in before['state']['R']['requests'] if x['id']==rid),{})
    check('original responsibility phase retained',parent.get('phase')==expected['parent_phase'])
    expected_binding=dict(principal='operator',**original_request)
    fields=('id','namespace','principal','kind','payload')
    queried=next((x for x in query.get('reply',{}).get('requests',[]) if x['id']==rid),{})
    after_parent=next((x for x in after['state']['R']['requests'] if x['id']==rid),{})
    check('complete original request is actual R acceptance and new query',all({k:row.get(k) for k in fields}==expected_binding for row in (parent,after_parent,queried)))
    for key in ('HTTP','tools','exchanges'):check('original '+key+' effect count',before['counts'][key]==expected[key])
    check('all actual HTTP replies complete',not before['HTTP_errors'] and all(x.get('request_complete') and x.get('response_complete') for x in before['HTTP_originals']))
    if expected['tools']:
        check('actual append is one, not regenerated expected bytes',before['effect_bytes_b64']==base64.b64encode(b'M03_EFFECT\n').decode() and before['counts']['effects']==1)
        for tool in before['tools']:
            r=tool['record'];b=r['binding'];proofs=[x for x in dispatches if x['binding']['execution_id']==b['execution_id']]
            check('native original script and complete output',base64.b64decode(r['request']['script_base64']).decode()==sample['script'] and r['result'].get('exit_code')==0 and r['result'].get('output_state')=='COMPLETE')
            check('actual CID/Exec observed at original dispatch',len(proofs)==1 and proofs[0].get('container',{}).get('status')==200 and proofs[0]['container']['body']['Id']==b['container_id'] and proofs[0].get('exec',{}).get('status')==200 and proofs[0]['exec']['body']['ContainerID']==b['container_id'])
    if sample['cut']=='install':
        check('original F intent remains unconfirmed',len(before['installs'])==1 and before['installs'][0]['record']['state']=='intent')
        check('actual original holder/install responsibility retained',bool(before['state']['R']['holders']) and any(i['installation_ref'] is None for i in before['state']['R']['installations']))
    if sample['cut']=='accept':return checks
    check('recovery actual dispatch observation explicitly empty',drive_dispatches==[])
    check('recovery preserves X S F provider and domain originals',{k:v for k,v in before['state'].items() if k not in ('R','R_auxiliary')}=={k:v for k,v in recovered['state'].items() if k not in ('R','R_auxiliary')})
    check('recovery drive used actual expired lease',drive.get('status')=='OBSERVED_DRIVE' and drive['actual_start']>=drive['lease_before'])
    check('recovery has zero extra HTTP/tool/exchange/effect',recovered['counts']==before['counts'] and recovered['provider_prepared']==before['provider_prepared'])
    check('recovery created no new original responsibility',{x['id'] for x in recovered['state']['R']['requests']}=={x['id'] for x in before['state']['R']['requests']})
    current=next((x for x in recovered['state']['R']['requests'] if x['id']==rid),{})
    allowed={'phase','token','worker','lease_until','query_ref','reason'}
    check('recovery retains original parent immutable fields',{k:v for k,v in parent.items() if k not in allowed}=={k:v for k,v in current.items() if k not in allowed})
    check('recovery keeps non-request decision R originals',all(before['state']['R'][k]==recovered['state']['R'][k] for k in before['state']['R'] if k not in ('requests','decisions')))
    check('recovery keeps original R schema metadata',[x for x in before['state']['R_auxiliary']['meta'] if x[0]!='claim_clock']==[x for x in recovered['state']['R_auxiliary']['meta'] if x[0]!='claim_clock'])
    check('recovery keeps original operations and restore indexes',all(before['state']['R_auxiliary'][k]==recovered['state']['R_auxiliary'][k] for k in ('operations','restore_installs','sqlite_sequence')))
    old_facilities={r['id']:r for r in before['state']['R']['requests'] if r['id']!=rid}
    new_facilities={r['id']:r for r in recovered['state']['R']['requests'] if r['id']!=rid}
    check('original issued/confirmed facilities remain same originals',old_facilities==new_facilities)
    if sample['cut']=='decision':
        old=before['state']['R']['decisions'];new=recovered['state']['R']['decisions']
        check('original single saved stop decision applied once',len(old)==len(new)==1 and old[0]['applied']==0 and new[0]['applied']==1 and {k:v for k,v in old[0].items() if k!='applied'}=={k:v for k,v in new[0].items() if k!='applied'} and set(old[0]['body'])=={'stop_ref'} and current.get('phase')=='settled')
    else:
        check('issued responsibility safely paused without invented result',current.get('phase')=='paused' and current.get('result_ref')==parent.get('result_ref'))
        check('original holder/install/receipts not silently acknowledged',all(recovered['state']['R'][k]==before['state']['R'][k] for k in ('holders','installations','releases')))
        check('non-decision recovery retains original decisions',before['state']['R']['decisions']==recovered['state']['R']['decisions'])
    return checks
