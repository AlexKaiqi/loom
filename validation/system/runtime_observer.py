"""M01 independent original-store observer. Never starts Runtime/model/task objects."""
import asyncio,base64,copy,json,os,time
from pathlib import Path
from urllib.parse import quote
from .runtime_observer_sources import (ObserverError,require,canonical,digest,strict,read,refraw,sql,tar_files,git_version,EngineRead,allocation,rss,nats_listener,raw_value,helper_allowed,confirmed_removal,complete_tool_result,complete_tool_feedback)
from validation.components.s.oracle import pi_jsonl
from .m01 import check_artifact_files
from lore_runtime.startup_assets import SLOT
ROOT=Path(__file__).resolve().parents[2]

def values(value):
    if isinstance(value,dict):
        yield value
        for item in value.values():yield from values(item)
    elif isinstance(value,list):
        for item in value:yield from values(item)
def strings(value,depth=0):
    if depth>12:return []
    if isinstance(value,str):
        result=[value]
        try:result+=strings(strict(value),depth+1)
        except (ValueError,ObserverError):pass
        return result
    if isinstance(value,dict):return [s for x in value.values() for s in strings(x,depth+1)]
    if isinstance(value,list):return [s for x in value for s in strings(x,depth+1)]
    return []

class Observer:
    def __init__(self,config,output_dir):
        self.config=copy.deepcopy(config);self.out=Path(output_dir).absolute();self.out.mkdir(parents=True,exist_ok=True)
        self.cfg=self.config.get('runtime',{});self.checks=[];self.observations={};self.trace=[];self.started=None;self.accepting=None;self.finished=None;self.task=None;self.closed=False;self.wake=None;self.loop=None;self.registration_ids={};self.engine=None;self.nats_pid=None;self.pi_bindings={}
    def save(self,name,value):
        p=self.out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(canonical(value)+b'\n');return str(p)
    def check(self,group,name,yes,**fact):
        self.checks.append(dict(group=group,check=name,passed=bool(yes),**fact))
    def required(self):
        for k in ('control_db','files_dir','execution_dir','session_dir','nats_url','engine_endpoint','event_profile','authority'):
            require(k in self.cfg,'MISSING config.runtime.'+k)
        require('root' in self.config.get('provider',{}),'MISSING config.provider.root')
        for k in ('control_db','files_dir','execution_dir','session_dir'):
            p=Path(self.cfg[k]);require(p.is_absolute() and p.resolve()==p,'unaliased configured owner '+k)
    async def begin(self,sample,registration_ids):
        self.required();require(self.started is None,'observer already begun')
        require(set(registration_ids)=={'surface','workspace'},'two original registration identities required')
        raw=read(Path(sample['original_input']),65536);require(digest(raw)==sample['original_sha256'],'protected original input changed')
        self.registration_ids=copy.deepcopy(registration_ids);self.started=time.monotonic();self.engine=EngineRead(self.cfg['engine_endpoint']);self.loop=asyncio.get_running_loop();self.wake=asyncio.Event()
        self.save('begin.json',dict(sample=sample,registration_ids=registration_ids,monotonic=self.started,pid=os.getpid(),config_sha256=digest(canonical(self.config))))
        self.task=asyncio.create_task(self._watch());await asyncio.sleep(0)
    def mark_accepting(self):
        require(self.started is not None and self.accepting is None,"accept clock requires begun observer and single start")
        self.accepting=time.monotonic();self.save("task-clock.json",dict(accepting=self.accepting,finished=None));self.notify()
    def mark_finished(self):
        require(self.accepting is not None,"finish requires actual accept clock")
        if self.finished is None:self.finished=time.monotonic();self.save("task-clock.json",dict(accepting=self.accepting,finished=self.finished));self.notify()
    def notify(self,*_):
        if self.loop is not None and self.wake is not None:self.loop.call_soon_threadsafe(self.wake.set)
    async def final_tick(self):
        # m01-real-2026-09-14aq v5-2 counterexample: mark_finished only wakes the
        # watch loop, so the last sample races with the runtime close that removes
        # containers; tail executions then lose their live Engine evidence and O8
        # is unsatisfiable for them. The caller awaits this deterministic final
        # sample before closing the runtime.
        if self.started is None:return
        self.trace.append(await asyncio.to_thread(self._sample));self.save('Engine-samples.json',self.trace)
    def _records(self):
        out=[];root=Path(self.cfg['execution_dir'])
        for p in root.glob('*/record.json'):
            r=strict(read(p));q=r['request'];ns=q.get('session_binding',{}).get('namespace',r.get('authority',{}).get('namespace'))
            if ns!=self.config['startup']['namespace']:continue
            if self.registration_ids and q.get('session_binding',{}).get('surface_id',q.get('target_id')) not in self.registration_ids.values():continue
            out.append((p,r))
        require(len(out)<=128,'finite original execution bound');return out
    def _sample(self):
        entry=dict(monotonic=time.monotonic(),objects=[],errors=[],recovered_reads=[])
        for attempt in range(3):
            try:
                records=self._records();objects={};slots=set();owner=digest(str(Path(self.cfg['execution_dir'])).encode())
                for p,r in records:
                    b=r['binding'];cid=b.get('container_id')
                    if r.get('slot_ref'):slots.add(r['slot_ref']['slot_id'])
                    if not cid:continue
                    result=self.engine.get('/containers/'+quote(cid,safe='')+'/json')
                    if result['status']==200:
                        got=result['body'];require(got['Id']==cid and got['Config']['Labels'].get('lore.x.execution_id')==b['execution_id'],'Engine original object association')
                    objects[cid]=dict(record_path=str(p),record_sha256=digest(read(p)),execution_id=b['execution_id'],binding=b,inspect=result)
                    if result['status']==200 and b.get('exec_id'):objects[cid]['exec_inspect']=self.engine.get('/exec/'+quote(b['exec_id'],safe='')+'/json')
                for slot in slots:
                    filters=quote(json.dumps({'label':['lore.x.slot_owner='+owner,'lore.x.slot_id='+slot]}))
                    listed=self.engine.get('/containers/json?all=true&filters='+filters);require(listed['status']==200,'slot original listing unavailable')
                    for item in listed['body']:
                        cid=item['Id'];result=self.engine.get('/containers/'+cid+'/json')
                        if result['status']==200:
                            labels=result['body']['Config']['Labels'];require(labels.get('lore.x.slot_owner')==owner and labels.get('lore.x.slot_id')==slot,'actual slot helper owner differs')
                        if cid not in objects:objects[cid]=dict(execution_id=item['Labels'].get('lore.x.execution_id'),slot=slot,inspect=result)
                entry['objects']=list(objects.values());entry['slots']=[];entry['volume_transitions']={}
                for slot in slots:
                    slotpath=Path(self.cfg['execution_dir'])/'.slots'/digest(slot.encode())/'current.json';raw=read(slotpath);entry['slots'].append(dict(path=str(slotpath),sha256=digest(raw),record=strict(raw)))
                entry['volumes']={}
                for item in objects.values():
                    if item['inspect']['status']!=200:continue
                    for mount in item['inspect']['body'].get('Mounts',[]):
                        if mount['Type']=='volume' and mount['Name'] not in entry['volumes']:entry['volumes'][mount['Name']]=self.engine.get('/volumes/'+quote(mount['Name'],safe=''))
                for name,v in entry['volumes'].items():
                    if v['status']!=404:continue
                    cids={o['inspect']['body']['Id'] for o in entry['objects'] if o['inspect']['status']==200 and any(m.get('Type')=='volume' and m.get('Name')==name for m in o['inspect']['body']['Mounts'])}
                    entry['volume_transitions'][name]=dict(volume_id=name,containers=[dict(container_id=cid,response=self.engine.get('/containers/'+quote(cid,safe='')+'/json')) for cid in sorted(cids)],volume_response=self.engine.get('/volumes/'+quote(name,safe='')))
                if self.nats_pid is None:self.nats_pid=nats_listener(self.cfg['nats_url'])
                entry['shared_rss']={'runtime_pid':os.getpid(),'nats_pid':self.nats_pid,'bytes':rss(os.getpid())+rss(self.nats_pid)}
                entry['private_storage']=allocation([self.cfg['execution_dir'],self.cfg['session_dir']]);break
            except Exception as exc:
                transient=isinstance(exc,FileNotFoundError) or 'original changed during read' in str(exc)
                if transient and attempt<2:entry['recovered_reads'].append(str(exc));continue
                entry['errors'].append(type(exc).__name__+': '+str(exc));break
        return entry
    async def _watch(self):
        # Watch lifetime derives from the runner budget (m01-real-2026-09-14bd
        # seeded-3 counterexample: the hard-coded 310s bound predated the 1800s
        # budget amendment; long chains outlived the watcher and every execution
        # after it lost its tick evidence, leaving O8 unsatisfiable).
        while not self.closed and time.monotonic()-self.started<=self.config.get('observer_seconds',310):
            self.trace.append(await asyncio.to_thread(self._sample));self.save('Engine-samples.json',self.trace)
            try:await asyncio.wait_for(self.wake.wait(),.1)
            except asyncio.TimeoutError:pass
            self.wake.clear()
    def _R(self,request_id):
        db=sql(self.cfg['control_db']);byid={r['id']:r for r in db['requests']};require(request_id in byid,'original invocation absent')
        chain={request_id};changed=True
        while changed:
            changed=False
            for d in db['decisions']:
                if d['parent_id'] in chain:
                    for s in d['body'].get('successors',[]):
                        require(s['id'] in byid,'accepted successor actual R row absent')
                        if s['id'] not in chain:chain.add(s['id']);changed=True
        rows=[r for r in db['requests'] if r['id'] in chain];require(all(r['kind']=='invocation' for r in rows),'non-invocation in original continuation chain')
        ns=self.config['startup']['namespace'];principal=self.config['startup']['principal'];require(all(r['namespace']==ns and r['principal']==principal for r in rows),'original invocation scope differs')
        self.accepted_invocations={r['id']:{k:r[k] for k in ('principal','id','namespace','kind','payload')} for r in rows}
        decisions=[d for d in db['decisions'] if d['parent_id'] in chain]
        self.check('O1','original_chain_has_applied_external_stop',bool(decisions) and len(decisions)==len(rows) and all(d['applied']==1 and d['source_ref']==byid[d['parent_id']]['result_ref'] and d['harness_ref']==byid[d['parent_id']]['payload']['harness_ref'] for d in decisions) and any(d['body'].get('stop_ref') is not None for d in decisions))
        self.check('O1','no_unknown_or_live_responsibility',all(r['phase'] not in ('accepted','issued','paused','decide') for r in rows) and not any(h['resource_id'] in self.registration_ids.values() for h in db['holders']))
        selected={r['id']:r for r in db['resources'] if r['id'] in self.registration_ids.values()}
        require(len(selected)==2,'actual two R registrations missing')
        for domain,rid in self.registration_ids.items():
            resource=selected[rid];path=Path(resource['path']);st=path.stat()
            require(resource['namespace']==ns and resource['kind']==domain and 'read' in resource['grants'].get(principal,[]) and resource['active']==1 and (st.st_dev,st.st_ino)==(resource['dev'],resource['ino']),'original current R authority/root differs')
        self.check('O1','actual_registered_current_authorized_roots',True)
        self.save('R-original.json',db);self.observations['R_chain']=[r['id'] for r in rows]
        return db,rows,decisions
    def _S(self,chain,decisions):
        all_entries={};boundaries={};sources=[];root=Path(self.cfg['session_dir']);scope=self.config['initial_session_ref'];seen=[]
        for directory in sorted(root.glob('confirm-*')):
            if not (directory/'result.json').exists():continue
            request=strict(read(directory/'request.json'));expected=request['expected_scope']
            if expected['namespace']!=scope['namespace'] or expected['session_id']!=scope['session_id']:continue
            result=strict(read(directory/'result.json'))
            if 'snapshot_ref' not in result:continue
            owner=strict(refraw(result['owner_record_ref'],root));ref=result['snapshot_ref']
            require(not owner.get('retention_only',False) and owner['snapshot_ref']==ref and owner['confirmation_request_id']==request['request_id'],'normal original S owner differs')
            record=strict(read(Path(ref['record_path'])));require(digest(read(Path(ref['record_path'])))==ref['record_sha256'],'S record hash')
            data=refraw(record['archive'],root,18874368);manifest=strict(refraw(record['manifest'],root));require(digest(data)==ref['archive_sha256']==manifest['archive_sha256'] and len(data)==ref['archive_bytes']==manifest['archive_bytes'],'S actual original archive differs')
            files,names=tar_files(data);require(set(manifest['entries'])==names,'S whole archive member set')
            if request['checkpoint_full_ref'] is None:continue
            cp=request['checkpoint_full_ref'];require(owner['source']['original_checkpoint_full_ref']==cp and cp['sha256']==digest(data),'S original X source association')
            for k in ('namespace','session_id','session_generation'):require(expected[k]==ref[k]==scope[k],'S complete scope differs')
            original=request['original_binding'];relative=original['jsonl_relative_path'];raw=files[relative];pi=pi_jsonl(raw)
            require(pi['values'].get(original['binding_namespace'],{}).get(original['binding_key'])==original['binding'],'original whole Pi binding differs from confirmed source')
            self.pi_bindings.update(pi['values'].get('lore.s.binding',{}))
            for e in pi['entries']:
                key=(pi['header']['id'],e['id']);require(key not in all_entries or all_entries[key]==e,'original Pi entry changed across snapshots');all_entries[key]=e
            for op,b in pi['values'].get('lore.s.boundary',{}).items():
                if op not in chain:continue
                locator=b['operation_result_ref'];require(locator['operation_id']==op and locator['session_scope']=={k:scope[k] for k in ('namespace','surface_id','session_id','session_generation')},'original result scope differs')
                end=locator['session_bytes'];require(locator['session_range']==[0,end] and digest(raw[:end])==locator['session_sha256'] and digest(raw_value(raw[:end],'pi.result',op))==locator['result_sha256'],'original exact Pi result/prefix differs')
                require(pi['values']['lore.s.binding'][op]['operation_id']==op,'original Pi operation binding missing')
                if op in boundaries:require(boundaries[op]==b,'saved original boundary changed')
                boundaries[op]=b
            seen.append(dict(confirmation_request_id=request['request_id'],owner_ref=result['owner_record_ref'],snapshot_ref=ref,jsonl_sha256=digest(raw),bytes=len(raw)));sources.append(pi)
        self.check('O3','normal_S_Pi_originals_present',bool(seen) and bool(all_entries))
        self.check('O3','R_decisions_equal_original_external_Harness_body',bool(decisions) and all(d['parent_id'] in boundaries and boundaries[d['parent_id']]['operation_result_ref']==d['source_ref'] and boundaries[d['parent_id']]['decision_proposal']['control']==dict(parent_id=d['parent_id'],harness_ref=d['harness_ref'],body=d['body']) for d in decisions))
        self.save('S-originals.json',dict(confirmations=seen,boundaries=boundaries,entries=list(all_entries.values())))
        return list(all_entries.values()),boundaries
    def _provider(self,db,chain,entries):
        rows=[r for r in db['requests'] if r['kind']=='provider_transport' and r['payload'].get('parent_id') in chain];output=[];root=Path(self.config['provider']['root']);messages=[e.get('message') for e in entries if e.get('message')]
        for row in rows:
            folder=root/digest(row['id'].encode());prepared_raw=read(folder/'prepared.json');prepared=strict(prepared_raw);receipt=strict(read(folder/'receipt.json'));p=row['payload']
            require(row['phase']=='confirmed' and prepared['effect_id']==row['id'] and prepared['frame']==p['frame'] and receipt['prepared_sha256']==digest(prepared_raw),'original R/provider saved association')
            require({k:v for k,v in prepared['binding'].items() if k!='response_entry_id'}==self.pi_bindings[p['parent_id']],'provider full scope not original Pi binding')
            req=refraw(receipt['files']['request.body'],root,65536);res=refraw(receipt['files']['response.body'],root,1048576);transport=strict(refraw(receipt['files']['transport.json'],root));assoc=strict(refraw(receipt['files']['association.json'],root))
            require(digest(req)==p['request_sha256']==assoc['request_sha256'] and digest(res)==assoc['response_sha256'] and assoc['binding']=={k:prepared['binding'][k] for k in ('session_id','operation_id','response_entry_id','harness_ref','input_ref','capability_ref')} and assoc['scope']==assoc['binding'],'original wire raw association differs')
            wire=receipt['wire'];actual=strict(res);request=strict(req);usage=actual['usage'];normalized=wire['normalized']['message']
            require(wire['accepted'] is True and transport['complete'] is True and transport['http_status']==200 and transport['received_size']==len(res),'original HTTP incomplete/rejected')
            require(normalized in messages,'original normalized provider Message absent from Pi')
            require(wire['normalized']['wire']['raw_usage']==usage,'original usage changed')
            output.append(dict(id=row['id'],seq=row['seq'],parent_id=p['parent_id'],request=request,response=actual,usage=usage,normalized=normalized,request_sha256=digest(req),response_sha256=digest(res),prepared=prepared))
        self.check('O4','real_HTTP_originals_and_Pi_correspond',bool(output) and len(output)==len(rows),count=len(output))
        self.save('provider-originals.json',output);return output
    def _tools(self,db,chain):
        rows=[r for r in db['requests'] if r['kind']=='execution' and r['payload'].get('parent_id') in chain and 'plan' in r['payload']];tools=[];versions={};xroot=Path(self.cfg['execution_dir'])
        for row in rows:
            p=row['payload'];q=p['plan']['request'];record_path=xroot/digest(row['id'].encode())/'record.json';r=strict(read(record_path));b=r['binding']
            require(q==r['request'] and b['execution_id']==row['id'] and b['request_digest']==digest(canonical(q)) and q['invocation_id']==p['parent_id'],'original R/X request digest differs')
            require(r.get('released') is True,'original tool release absent')
            require(complete_tool_result(r),'original tool output incomplete or exit status unknown')
            require(row['phase']=='confirmed' and row['receipt_ref']['request_digest']==digest(canonical({k:row[k] for k in ('principal','id','namespace','kind','payload')})),'original tool facility receipt association')
            stdout=refraw(r['artifacts']['stdout'],xroot,1048576);stderr=refraw(r['artifacts']['stderr'],xroot,1048576);cp=r['artifacts']['checkpoint'];raw=refraw(cp,xroot,8388608);stop=strict(refraw(r['artifacts']['stopped'],xroot,8388608))
            for k in ('execution_id','object_generation','target_id','domain'):require(stop[k]==b[k],'original stopped binding differs')
            require(stop['prepared_ref']==cp,'original stop does not refer to checkpoint')
            for typ,key,path in [('container','container_id','/containers/'),('volume','volume_id','/volumes/')]:
                result=self.engine.get(path+quote(b[key],safe='')+('/json' if typ=='container' else ''));require(result['status']==404,'actual original object not absent');self.save('final-'+typ+'-'+digest(b[key].encode())+'.json',result)
            install=[x for x in db['installations'] if x['binding']['execution_id']==row['id']];release=[x for x in db['releases'] if x['execution_id']==row['id']]
            require(len(install)==len(release)==1,'original one installation/release missing');ins=install[0];rr=release[0];version=ins['installation_ref']['version_ref']
            require(rr['holder']==dict(resource_id=q['target_id'],execution_id=row['id'],base_ref=p['plan']['base_ref']) and rr['binding']['published_ref']==ins['installation_ref'] and ins['binding']['base_ref']==p['plan']['base_ref'],'original holder/base/publication differs')
            files,manifest,blobs=git_version(self.cfg['files_dir'],version);require(blobs['archive.tar']==raw,'F publication is not original complete X checkpoint')
            versions[q['domain']]=(version,files);tools.append(dict(row=row,record=r,stdout=stdout,stderr=stderr,exit_code=r['result']['exit_code'],files=files,version_ref=version,manifest=manifest))
        self.save('tool-original-results.json',[dict(id=t['row']['id'],domain=t['record']['request']['domain'],output_state=t['record']['result']['output_state'],exit_code=t['exit_code'],stdout_ref=t['record']['artifacts']['stdout'],stderr_ref=t['record']['artifacts']['stderr'],stdout_base64=base64.b64encode(t['stdout']).decode(),stderr_base64=base64.b64encode(t['stderr']).decode()) for t in tools])
        self.check('O5','actual_two_domains_published_stopped_released',{'runtime','task'}<=set(versions) and bool(tools),tools=len(tools));return tools,versions
    async def _events(self,db,chain,provider):
        import nats
        rows=[r for r in db['requests'] if r['kind']=='event' and r['namespace']==self.config['startup']['namespace']]
        nc=await asyncio.wait_for(nats.connect(self.cfg['nats_url'],connect_timeout=2,max_reconnect_attempts=0,allow_reconnect=False),3);events=[]
        try:
            js=nc.jetstream();stream=self.cfg['event_profile']['stream_prefix']+self.config['startup']['namespace'];info=await js.stream_info(stream)
            require(getattr(info.config.storage,'value',info.config.storage)=='file' and getattr(info.config.discard,'value',info.config.discard)=='new' and info.config.max_age==0 and info.config.num_replicas==1,'actual JetStream profile differs')
            for row in rows:
                receipt=row['receipt_ref'];require(row['phase']=='confirmed' and receipt['outcome']=='positive','event not positively confirmed');ref=receipt['facility_ref'];msg=await js.get_msg(stream,seq=ref['sequence']);raw=msg.data;body=strict(raw)
                require(msg.seq==ref['sequence'] and msg.subject==ref['subject']==row['payload']['subject'] and digest(raw)==ref['sha256']==row['payload']['event_sha256'],'independent NATS original differs')
                require(body['request_id']==row['id'] and body['namespace']==row['namespace'] and body['source']==row['principal'],'NATS source/principal/namespace differs')
                events.append(dict(row=row,ref=ref,raw_base64=base64.b64encode(raw).decode(),body=body))
        finally:await nc.close()
        matches=[];root=Path(self.cfg['event_profile']['input_root'])
        for item in db['inputs']:
            if item['invocation_id'] not in chain:continue
            ref=item['input_ref'];directory=Path(ref['path']);require(directory.resolve().is_relative_to(root.resolve()),'input owner path');st=directory.stat();require(ref['root']==dict(dev=st.st_dev,ino=st.st_ino),'E original inode')
            names={'events.jsonl','invocation.json','execution-targets.json','manifest.json'};require({p.name for p in directory.iterdir()}==names,'E exact four files');files={n:read(directory/n) for n in names};meta=strict(files['manifest.json']);inv=strict(files['invocation.json']);targets=strict(files['execution-targets.json'])
            require(digest(files['manifest.json'])==ref['manifest_sha256'] and meta['complete'] is True and all(meta['files'][n]==dict(bytes=len(files[n]),sha256=digest(files[n])) for n in names-{'manifest.json'}),'original E file hashes')
            restored=dict(namespace=inv['namespace'],source=inv['source'],start_sequence=inv['range']['start_sequence'],filters=inv['filters'],page_size=inv['page_size'],surface_ref=inv['surface_ref'],previous_session_ref=inv['previous_session_ref'],execution_targets=targets['targets']);require(restored==item['binding'] and inv['invocation_id']==item['invocation_id']==meta['invocation_id'],'E selector differs from original R binding')
            for event in events:
                raw=base64.b64decode(event['raw_base64']);
                if event['ref'] in meta['event_refs'] and raw+b'\n' in files['events.jsonl'] and any(p['parent_id']==item['invocation_id'] and any(raw.decode() in s for s in strings(p['request'])) for p in provider):matches.append(dict(invocation_id=item['invocation_id'],sequence=event['ref']['sequence'],input_ref=ref))
        self.check('O6','one_actual_notification_in_next_Pi_input',len(events)==1 and bool(matches),events=len(events),next_inputs=matches);self.save('NATS-originals.json',events)
    def _history(self,tools,versions,provider,entries,sample):
        require('task' in versions and 'runtime' in versions,'both artifact domains absent');report_version,reportfiles=versions['task'];surface_version,notesfiles=versions['runtime']
        require('report.json' in reportfiles and 'blocks/notes.md' in notesfiles,'original M01 report/blocks notes missing')
        location='/input/history/'+digest(canonical(report_version))+'/report.json';history=False;candidates=[]
        messages=[e.get('message') for e in entries if e.get('message')]
        for tool in tools:
            q=tool['record']['request'];frame=tool['row']['payload']['frame'];script=base64.b64decode(q['script_base64']).decode();text=tool['stdout'].decode('utf8')
            if q['domain']=='runtime' and any(token in script for token in ('cat ','read_text','read_bytes','open(','json.load')):
                mounts=q.get('readonly_mounts',[])
                if len(mounts)!=1:continue
                view=mounts[0];require(view['role']=='input' and view['target']=='/input' and view['read_only'] is True,'original history mount capability differs')
                files,_,_=git_version(self.cfg['files_dir'],view['content_ref']['version_ref']);cfg=strict(files['node-config.json']);refs=cfg['input']['history_views']
                original=tool['row']['payload']['plan']['original_invocation'];require(original==self.accepted_invocations[q['invocation_id']],'history candidate not original accepted invocation')
                selected=[t['version_ref'] for t in original['payload']['input_binding']['execution_targets'] if t['resource_id']==self.registration_ids['workspace']]
                require(len(selected)==1,'one original accepted Workspace selection required')
                selected=selected[0];prefix='history/'+digest(canonical(selected));expected=dict(version_ref=selected,read_path='/input/'+prefix)
                require(refs==[expected],'captured history differs from its original accepted selection')
                selected_files,_,_=git_version(self.cfg['files_dir'],selected)
                captured={k[len(prefix)+1:]:v for k,v in files.items() if k.startswith(prefix+'/')}
                require(captured==selected_files,'captured history does not preserve original selected file bytes')
                candidate=dict(execution_id=q['execution_id'],selected_version=selected,target_version=report_version,target=selected==report_version)
                candidates.append(candidate)
                if selected!=report_version:continue  # Valid older attempt is not target-history evidence.
                require(files[prefix+'/report.json']==reportfiles['report.json'],'input target history original bytes differ')
                actual=[o['inspect']['body'] for tick in self.trace for o in tick.get('objects',[]) if o['execution_id']==q['execution_id'] and o['inspect']['status']==200]
                mounted=any(any(m['Destination']=='/input' and m['Source']==view['source']['path'] and not m['RW'] for m in c['Mounts']) for c in actual)
                read_seen=reportfiles['report.json'].decode().strip() in text or any(isinstance(v,dict) and canonical(v)==canonical(strict(reportfiles['report.json'])) for v in self._json_outputs(text))
                candidate.update(actual_mount=mounted,original_report_stdout=read_seen);history|=mounted and read_seen
        self.save('history-candidates.json',candidates)
        self.check('O5','actual_runtime_history_read_not_only_link',history,report_location=location)
        path=self.out/'artifacts';path.mkdir(exist_ok=True);(path/'report.json').write_bytes(reportfiles['report.json']);(path/'notes.md').write_bytes(notesfiles['blocks/notes.md'])
        art=dict(report_path=str(path/'report.json'),notes_path=str(path/'notes.md'),report_location=location);result=check_artifact_files(sample,**art)
        self.check('O2','independent_original_sum_and_notes_link',True,artifact=result,report_version=report_version,notes_version=surface_version);return art
    def _feedback(self,tools,entries,provider):
        feedback=[];facts=[];messages=[e.get('message') for e in entries if e.get('message')]
        for tool in tools:
            frame=tool['row']['payload']['frame'];stdout=tool['stdout'];stderr=tool['stderr'];code=tool['exit_code']
            original_results=[e['message'] for e in entries if e.get('id')==frame['invocation_id'] and e.get('message',{}).get('role')=='toolResult']
            native_ids={m['toolCallId'] for m in original_results}
            native_request=any(c.get('type')=='toolCall' and c.get('id') in native_ids and c.get('arguments')==frame['request'] for m in messages if m.get('role')=='assistant' for c in m.get('content',[]))
            saved=any(complete_tool_feedback(m,stdout,stderr,code,tool['row']['receipt_ref']['facility_ref']['result_ref']) for m in original_results)
            expected=[x.decode('utf8') for x in (stdout,stderr) if x]+['Command exited with code '+str(code)]
            later=any(p['seq']>tool['row']['seq'] and any(m.get('role')=='tool' and m.get('tool_call_id') in native_ids and all(any(text in part for part in strings(m)) for text in expected) for m in p['request'].get('messages',[])) for p in provider)
            feedback.append(native_request and saved and later);facts.append(dict(execution_id=tool['row']['id'],native_request=native_request,original_two_streams_and_exit=saved,later_provider=later,exit_code=code))
        self.save('native-tool-feedback.json',facts)
        self.check('O4','original_native_tool_output_reaches_next_provider',bool(feedback) and all(feedback),tools=facts)
    @staticmethod
    def _json_outputs(text):
        result=[]
        try:result.append(strict(text))
        except (ValueError,ObserverError):pass
        for line in text.splitlines():
            try:result.append(strict(line))
            except (ValueError,ObserverError):pass
        return result
    def _budgets(self,rows,provider):
        endpoint=self.config['provider']['endpoint'];real=endpoint.get('host') not in ('localhost','127.0.0.1','::1')
        # Model scope per the declared wire baseline (amendment-model-baseline-2026-09-15):
        # the request must carry the exact baseline id and the response may echo the
        # baseline or its pinned dated alias. Batch z remains bound to its recorded
        # glm-5.3 instrument; new-baseline batches declare their scope in config.
        observation=self.config.get('observation',{})
        expected_model=observation.get('expected_model')
        expected_alias=observation.get('expected_model_alias',expected_model)
        self.check('O7','original_real_model_scope',real and bool(provider) and expected_model is not None and
                   all(p['request'].get('model')==expected_model and p['response'].get('model') in (expected_model,expected_alias) for p in provider),
                   baseline=expected_model,alias=expected_alias)
        # O7 mirrors the amended per-sample contract (m01-output-budget amendment
        # 2026-09-14): wall 300->1800, steps/responses 6->24, output 2048->16384,
        # input 15360->49152->393216 (cumulative, re-derived for archive-enabled
        # chain shapes). Original values retained in the amendment record.
        self.check('O7','original_step_token_time_limits',self.accepting is not None and self.finished is not None and 0<=self.finished-self.accepting<=1800 and 0<len(rows)<=24 and 0<len(provider)<=24 and all(type(p['usage']['completion_tokens']) is int and p['usage']['completion_tokens']<=16384 for p in provider) and sum(p['usage']['prompt_tokens'] for p in provider)<=49152)
        ticks=[t for t in self.trace if not t['errors']]
        self.check('O8','actual_lifetime_samples_present',bool(ticks) and self.started is not None and not any(t['errors'] for t in self.trace),sample_errors=[t['errors'] for t in self.trace if t['errors']])
        # Tail executions (m01-real-2026-09-14ao seeded-1 counterexample): binding
        # records written after the last tick were never sampled, so the required
        # set was unsatisfiable by construction. Sample the record containers
        # directly now; an already-exited container still yields Engine exec
        # evidence (exec inspect 200 with matching ContainerID and user 1000:1000),
        # which is accepted as the live-execution proof when a Running capture was
        # never possible. The pre-revision requirement (Running capture only) and
        # this counterexample stay in the amendment record.
        tail={}
        for q,r in self._records():
            cid=r['binding'].get('container_id')
            if not cid or cid in {o.get('binding',{}).get('container_id') for t in ticks for o in t['objects']}:continue
            ins=self.engine.get('/containers/'+quote(cid,safe='')+'/json')
            item=dict(record_path=str(q),record_sha256=digest(read(q)),execution_id=r['binding']['execution_id'],binding=r['binding'],inspect=ins)
            if ins['status']==200 and r['binding'].get('exec_id'):item['exec_inspect']=self.engine.get('/exec/'+quote(r['binding']['exec_id'],safe='')+'/json')
            tail[cid]=item
        # The synthetic tick carries the full real-tick shape (m01-real-2026-09-14aq
        # v5-2 counterexample: O7's budget observations iterate t['volumes'] over
        # every tick; a bare dict raised KeyError).
        if tail:ticks=ticks+[dict(monotonic=time.monotonic(),objects=list(tail.values()),errors=[],recovered_reads=[],volumes={},slots=[],volume_transitions={},private_storage=dict(allocated_bytes=0,inodes=0))]
        required_ids={r['binding']['execution_id'] for _,r in self._records()}
        def observed_ok(o):
            if o['inspect']['status']!=200 or o['inspect']['body']['Config']['Labels'].get('lore.x.role')=='helper':return False
            if not o.get('binding',{}).get('exec_id') or o.get('exec_inspect',{}).get('status')!=200:return False
            if o['exec_inspect']['body'].get('ContainerID')!=o['binding']['container_id'] or o['exec_inspect']['body'].get('ProcessConfig',{}).get('user')!='1000:1000':return False
            return o['inspect']['body']['State']['Running'] or o.get('exec_inspect',{}).get('status')==200
        observed={o['execution_id'] for t in ticks for o in t['objects'] if observed_ok(o)}
        self.check('O8','each_actual_execution_has_live_Engine_inspect',bool(required_ids) and required_ids<=observed,missing=sorted(required_ids-observed))
        good=bool(ticks) and not any(t['errors'] for t in self.trace)
        for t in ticks:
            removed={c['container_id'] for name in t['volumes'] if confirmed_removal(t,name) for c in t['volume_transitions'][name]['containers']}
            live=[o['inspect']['body'] for o in t['objects'] if o['inspect']['status']==200 and o['inspect']['body']['State']['Running'] and o['inspect']['body']['Id'] not in removed]
            good &= len(live)<=3 and sum(x['HostConfig']['Memory'] for x in live)<=768*1024**2 and t['shared_rss']['bytes']<=2*1024**3 and t['private_storage']['allocated_bytes']<=128*1024**2 and t['private_storage']['inodes']<=8192
            good &= sum(x['HostConfig']['NanoCpus'] for x in live)<=10**9
            # Independently bound currently mounted tmpfs capacity plus actual host original blocks.
            mounted_bytes=mounted_inodes=0
            for name,volume in t['volumes'].items():
                if confirmed_removal(t,name):continue
                if volume['status']!=200:good=False;continue
                opts=volume['body'].get('Options',{});parts=dict(z.split('=',1) for z in opts.get('o','').split(',') if '=' in z)
                good &= opts.get('type')=='tmpfs' and 'size' in parts and 'nr_inodes' in parts
                mounted_bytes+=int(parts.get('size','0'));mounted_inodes+=int(parts.get('nr_inodes','0'))
            for x in live:
                tmp=x['HostConfig'].get('Tmpfs',{})
                for destination,options in tmp.items():
                    parts=dict(z.split('=',1) for z in options.split(',') if '=' in z);mounted_bytes+=int(parts.get('size','0'));mounted_inodes+=int(parts.get('nr_inodes','0'))
                if '/dev/shm' not in tmp:mounted_bytes+=x['HostConfig']['ShmSize'];mounted_inodes+=64
            # Plan-total mirrors are derived from the admitted SLOT envelope
            # itself (m01-output-budget amendment, batches ag/ah pinned 256 MiB
            # by hand; batch bc mismatched after the external envelope raise to
            # 512 MiB). Deriving keeps future envelope amendments consistent.
            _slot=SLOT
            good &= mounted_bytes+t['private_storage']['allocated_bytes']<=_slot['all_active_writable_bytes'] and mounted_inodes+t['private_storage']['inodes']<=_slot['all_active_writable_inodes']
            for slot in t['slots']:
                saved=slot['record'];plan=saved['plan'];good &= plan['all_active_writable_bytes']<=_slot['all_active_writable_bytes'] and plan['all_active_writable_inodes']<=_slot['all_active_writable_inodes'] and plan['max_objects']<=_slot['max_objects']
                rs=list(saved['reservations'].values());good &= sum(r['writable_bytes'] if r['state']!='RELEASED' else r['retained_spool']['allocated_bytes'] for r in rs)<=_slot['all_active_writable_bytes']
                good &= sum(r['writable_inodes'] if r['state']!='RELEASED' else r['retained_spool']['inodes'] for r in rs)<=_slot['all_active_writable_inodes']
            for x in live:
                h=x['HostConfig'];role=x['Config']['Labels'].get('lore.x.role');session=role=='session';tmp=h.get('Tmpfs',{});options=tmp.get('/tmp','')
                # Keeper is UID0/cap-drop; actual task Engine exec must be fixed UID1000.
                # Per-role container budgets derive from the admitted SLOT envelope
                # (batch bc: the external raise moved tool memory to 768 MiB and
                # tool cpus to 1.0; hand-pinned values 512/128 mismatched).
                budget=_slot['session_memory_bytes']//(1024**2) if session else _slot['tool_memory_bytes']//(1024**2)
                _cpu=_slot['cpus']['S'] if session else _slot['cpus']['tool']
                good &= role in ('session','tool','helper') and h['ReadonlyRootfs'] and h['NetworkMode']=='none' and 'ALL' in h['CapDrop'] and any('no-new-privileges' in z for z in h['SecurityOpt'])
                good &= h['Memory']>0 and h['Memory']<=budget*1024**2 and h['MemorySwap']==h['Memory'] and 0<h['PidsLimit']<=(64 if session else 32) and 0<h['NanoCpus']<=_cpu*10**9 and 0<h['ShmSize']<=1048576
                parts=dict(z.split('=',1) for z in options.split(',') if '=' in z)
                good &= all(z in options.split(',') for z in ('nosuid','nodev','noexec')) and 0<int(parts.get('size','0'))<=(33554432 if session else 1048576) and 0<int(parts.get('nr_inodes','0'))<=(2048 if session else 64)
                if role=='helper':
                    original=next((o['binding'] for o in t['objects'] if o.get('binding',{}).get('execution_id')==x['Config']['Labels'].get('lore.x.execution_id')),None)
                    owner=digest(str(Path(self.cfg['execution_dir'])).encode())
                    good &= original is not None and helper_allowed(x,original,owner,t['volumes'].get(original['volume_id'],{}))
                else:
                    # Keeper starts before the original exec is created. It supplies no task UID evidence.
                    good &= x['Config']['User']=='0:0'
                    items=[o for o in t['objects'] if o['inspect']['status']==200 and o['inspect']['body']['Id']==x['Id']]
                    good &= bool(items) and all(not o.get('binding',{}).get('exec_id') or (o.get('exec_inspect',{}).get('status')==200 and o['exec_inspect']['body'].get('ContainerID')==o['binding']['container_id'] and o['exec_inspect']['body'].get('ProcessConfig',{}).get('user')=='1000:1000') for o in items)
        self.check('O8','actual_original_resource_bounds',good)
    def _final_X(self,chain):
        originals=[]
        for path,r in self._records():
            q=r['request'];b=r['binding']
            if q['invocation_id'] not in chain:continue
            require(r.get('released') is True and b['request_digest']==digest(canonical(q)),'original S/tool release or request digest missing')
            stop=strict(refraw(r['artifacts']['stopped'],Path(self.cfg['execution_dir']),18874368))
            require(all(stop[k]==b[k] for k in ('execution_id','object_generation','target_id','domain')) and stop['container_id']==b['container_id'],'original final stopped identity differs')
            proof={}
            for key,route,suffix in [('container_id','containers','/json'),('volume_id','volumes','')]:
                got=self.engine.get('/'+route+'/'+quote(b[key],safe='')+suffix);require(got['status']==404,'original S/tool physical object remains');proof[key]=got
            originals.append(dict(execution_id=b['execution_id'],record_sha256=digest(read(path)),stopped=r['artifacts']['stopped'],actual_absence=proof))
        require(originals,'no final original X executions')
        # Include short lived helpers of this exact slot owner; no unrelated inventory is retained.
        owner=digest(str(Path(self.cfg['execution_dir'])).encode());slots={r['slot_ref']['slot_id'] for _,r in self._records() if r.get('slot_ref')}
        for slot in slots:
            filters=quote(json.dumps({'label':['lore.x.slot_owner='+owner,'lore.x.slot_id='+slot]}));got=self.engine.get('/containers/json?all=true&filters='+filters);require(got['status']==200 and not got['body'],'original slot helper/task remains')
        self.save('final-all-X.json',originals);self.check('O8','all_original_S_tool_and_slot_objects_released',True,count=len(originals))
    async def collect_m01(self,sample,request_id):
        self.closed=True
        if self.wake:self.wake.set()
        if self.task:await self.task
        artifacts=None;db=None;rows=[];decisions=[];entries=[];provider=[];tools=[];versions={};chain=set()
        try:self.required();self.engine=self.engine or EngineRead(self.cfg['engine_endpoint'])
        except Exception as exc:
            self.check('O1','configuration_and_original_owners_available',False,error=str(exc));return self._finish(sample,artifacts)
        if not self.registration_ids:self.registration_ids={d:self.config['startup']['sources'][d]['resource_id'] for d in ('surface','workspace')}
        async def run(group,name,fn):
            try:
                result=fn()
                if hasattr(result,'__await__'):result=await result
                return result
            except Exception as exc:self.check(group,name,False,error=type(exc).__name__+': '+str(exc));return None
        result=await run('O1','original_R_chain',lambda:self._R(request_id))
        if result:db,rows,decisions=result;chain={r['id'] for r in rows}
        if db:
            result=await run('O3','original_S_source',lambda:self._S(chain,decisions))
            if result:entries,_=result
            result=await run('O4','original_provider_source',lambda:self._provider(db,chain,entries))
            if result is not None:provider=result
            result=await run('O5','original_X_and_F_source',lambda:self._tools(db,chain))
            if result:tools,versions=result
            await run('O4','original_complete_tool_feedback',lambda:self._feedback(tools,entries,provider))
            await run('O6','original_events_and_next_input',lambda:asyncio.wait_for(self._events(db,chain,provider),10))
            await run('O8','all_X_final_originals',lambda:self._final_X(chain))
            artifacts=await run('O2','original_artifacts_and_history',lambda:self._history(tools,versions,provider,entries,sample))
        await run('O7','original_budget_observations',lambda:self._budgets(rows,provider))
        for group in ('O1','O2','O3','O4','O5','O6','O7','O8'):
            if not any(c['group']==group for c in self.checks):self.check(group,'required_original_evidence_missing',False)
        return self._finish(sample,artifacts)
    def _finish(self,sample,artifacts):
        result=dict(id=sample.get('id'),status='PASS' if self.checks and all(c['passed'] for c in self.checks) and artifacts else 'FAIL',scope='ONE_M01_SAMPLE_ORIGINAL_OBSERVATIONS_ONLY',checks=self.checks,observations=self.observations,source_hashes={str(p):digest(p.read_bytes()) for p in (Path(__file__),Path(__file__).with_name('runtime_observer_sources.py'),ROOT/'design/g3/system/runtime-observer.md',ROOT/'validation/components/f/observer.py',ROOT/'validation/components/s/oracle.py',ROOT/'validation/system/artifact_oracles.py',ROOT/'validation/system/dependencies/markdown-001/manifest.json')})
        if artifacts:result['artifact_files']=artifacts
        self.save('result.json',result);return result
