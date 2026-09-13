"""Case-local trusted fixture setup and direct existing-port assertions."""
from pathlib import Path
import base64,copy,importlib.util,json,os,shutil,socket,uuid
from artifacts import canonical,file_fact,read_ref,require,save,sha_bytes,strict_json
from fixtures import Fixture,FInputs,register,readonly_manifest,tree
from actions import Experiment
ROOT=Path(__file__).resolve().parents[3]

def replace_readonly_root(root):
    """Replace only the root inode; restore original object even if a move fails."""
    root=Path(root);parent=root.parent;before=root.stat();parent_before=parent.stat()
    mode=before.st_mode&0o7777;parent_mode=parent_before.st_mode&0o7777
    retired=root.with_name(root.name+'-original-'+uuid.uuid4().hex)
    def move(item,target):
        original=item.lstat();directory=item.is_dir()and not item.is_symlink()
        if directory:item.chmod((original.st_mode&0o7777)|0o300)
        try:item.rename(target)
        finally:
            if directory:
                actual=target if target.exists()and target.stat().st_ino==original.st_ino else item
                actual.chmod(original.st_mode&0o7777);os.utime(actual,ns=(original.st_atime_ns,original.st_mtime_ns))
    def undo():
        parent.chmod(parent_mode|0o300)
        try:
            if retired.exists():
                retired.chmod(mode|0o300)
                if root.exists():
                    root.chmod(mode|0o300)
                    for item in list(root.iterdir()):
                        target=retired/item.name
                        require(not target.exists()and not target.is_symlink(),'fixture recovery refuses to overwrite original member')
                        move(item,target)
                    root.rmdir()
                retired.rename(root)
            require((root.stat().st_dev,root.stat().st_ino)==(before.st_dev,before.st_ino),'original fixture root identity not restored')
            root.chmod(mode);os.utime(root,ns=(before.st_atime_ns,before.st_mtime_ns))
        finally:
            parent.chmod(parent_mode);os.utime(parent,ns=(parent_before.st_atime_ns,parent_before.st_mtime_ns))
    # The recovery path exists before the first permission change or rename.
    try:
        parent.chmod(parent_mode|0o300);root.rename(retired);retired.chmod(mode|0o300)
        root.mkdir(mode=mode|0o300)
        for item in list(retired.iterdir()):move(item,root/item.name)
        root.chmod(mode);os.utime(root,ns=(before.st_atime_ns,before.st_mtime_ns));retired.chmod(mode)
        return undo
    except BaseException:
        undo();raise

def allocated_originals(root,pids=()):
    """External lstat/FD accounting including original directory blocks, deduplicated by inode."""
    root=Path(root);seen={}
    for path in [root,*sorted(root.rglob('*'))]:
        st=path.lstat();seen[(st.st_dev,st.st_ino)]={'path':str(path),'allocated_bytes':st.st_blocks*512,'dev':st.st_dev,'ino':st.st_ino}
    for pid in pids:
        folder=Path('/proc')/str(pid)/'fd'
        if not folder.exists():continue
        for fd in folder.iterdir():
            try:
                target=os.readlink(fd)
                if target.startswith(str(root)+'/')and target.endswith(' (deleted)'):
                    st=fd.stat();seen[(st.st_dev,st.st_ino)]={'path':target,'fd':str(fd),'allocated_bytes':st.st_blocks*512,'dev':st.st_dev,'ino':st.st_ino}
            except FileNotFoundError:pass
    st=root.lstat()
    return {'path':str(root),'root':{'dev':st.st_dev,'ino':st.st_ino},'allocated_bytes':sum(row['allocated_bytes']for row in seen.values()),'inodes':len(seen),'objects':list(seen.values())}

class Context:
    def __init__(self,case,argv,out,deps):
        self.case=case;self.variants=case['negative_variants'];self.argv=argv;self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.deps=deps;self.active=[];self.marked=[];self.n=0;self.peers=[]
    def mark(self,name):
        require(name not in self.marked,'duplicate case action marker:'+name);self.marked.append(name)
        (self.out/'observed-variants.json').write_bytes(canonical(self.marked)+b'\n')
    def make_fixture(self,mode='channel',large=False,namespace=None,session_id='prep-session'):
        self.n+=1;return Fixture(self.out/('fixture-'+str(self.n)),self.deps,mode,large=large,namespace=namespace,session_id=session_id)
    def launch(self,fx):
        self.n+=1;e=Experiment(fx,self.argv,self.out/('actual-'+str(self.n)));self.active.append(e);return e
    def new(self,mode,large=False,network_peer=False):
        fx=self.make_fixture(mode,large)
        if network_peer:self.make_peer(fx)
        e=self.launch(fx)
        if network_peer:e.observer.baseline_containers=[x for x in e.observer.baseline_containers if x!=self.peers[-1]['cid']]
        return e
    def config_revision(self,fx,principal=None):
        config=copy.deepcopy(fx.config)
        if principal:config['transport_principal']=principal
        config['grants'].append(fx.authority['grant_ref'])
        fx.config_path=fx.root/('trusted-config-'+uuid.uuid4().hex+'.json');save(fx.config_path,config)
    def rejected(self,e,method,args,code):
        before=e.observer.inventory();state={str(p.relative_to(e.fx.state)):file_fact(p)[0]['sha256']for p in e.fx.state.rglob('*')if p.is_file()}
        value=e.rpc.call(method,args);require(value.get('error',{}).get('code')==code,'wrong rejection '+str(value))
        e.observer.no_new_objects(before)
        after={str(p.relative_to(e.fx.state)):file_fact(p)[0]['sha256']for p in e.fx.state.rglob('*')if p.is_file()}
        require(state==after,'rejected request rewrote original X facts')
        save(e.out/('rejection-'+str(len(list(e.out.glob('rejection-*.json'))))+'.json'),{'method':method,'code':code,'response':value,'state_before':state,'state_after':after,'physical_before':before})
    def generic_negatives(self,only_mutations=False,exclude=()):
        for variant in self.variants:
            if variant['name']in exclude or 'mutate'not in variant:continue
            fx=self.make_fixture('channel',large=variant['name']in('missing_large_member','wrong_large_file_hash'))
            original=copy.deepcopy(fx.request);mutation=variant['mutate'];where=mutation['where'];path=mutation['path'];value=mutation['value'];restore=None;extra={};principal=None
            try:
                if where=='request':
                    values={'@fixture.other_session_id':'other-Session','@fixture.unauthorized_root':str(fx.root/'control'),
                            '@fixture.owned_host_socket':str(fx.root/'control/owned.sock'),'@fixture.canary':fx.canary.decode()}
                    value=values.get(value,value)if isinstance(value,str)else value
                    target=fx.request;parts=path.split('/')
                    for part in parts[:-1]:target=target[int(part)]if isinstance(target,list)else target[part]
                    if isinstance(target,list):target[int(parts[-1])]=value
                    else:target[parts[-1]]=value
                    if variant['expected_code']=='INVALID_REQUEST':fx.authority['grant_ref']=fx.grant(fx.request)
                    self.config_revision(fx)
                elif where=='peer_params':extra[path]=value
                elif where=='trusted_route':principal='model-origin';self.config_revision(fx,principal)
                elif where=='filesystem':
                    if path=='dependencies_root':
                        restore=replace_readonly_root(Path(fx.mounts[0]['source']['path']))
                    else:
                        if path.startswith('dependencies/'):
                            manifest=strict_json(read_ref(fx.mounts[0]['manifest_ref'],2097152)[1]);name=min((n for n,v in manifest['entries'].items()if v['kind']=='file'),key=lambda n:manifest['entries'][n]['byte_length']);target=Path(fx.mounts[0]['source']['path'])/name
                        elif path=='snapshot_archive':target=Path(fx.snapshot_ref['archive_path'])
                        elif path=='input/escape':target=Path(fx.mounts[2]['source']['path'])/'escape'
                        else:
                            root=Path(fx.mounts[3]['source']['path']);target=next(p for p in sorted(root.rglob('*'))if p.is_file())
                        existed=target.exists();raw=target.read_bytes()if existed else None;mode=(target.stat().st_mode&0o7777)if existed else 0o644;parent_mode=target.parent.stat().st_mode&0o7777;parent_mtime=target.parent.stat().st_mtime_ns;file_mtime=target.stat().st_mtime_ns if existed else None
                        def undo(target=target,raw=raw,mode=mode,existed=existed,parent_mode=parent_mode,parent_mtime=parent_mtime,file_mtime=file_mtime):
                            target.parent.chmod(parent_mode|0o300)
                            if target.exists()or target.is_symlink():target.unlink()
                            if existed:target.write_bytes(raw);target.chmod(mode);os.utime(target,ns=(file_mtime,file_mtime))
                            target.parent.chmod(parent_mode);os.utime(target.parent,ns=(parent_mtime,parent_mtime))
                        restore=undo
                        target.parent.chmod(0o755)
                        if existed:target.chmod(0o600)
                        if value=='delete':target.unlink()
                        elif value=='symlink-outside':target.symlink_to(fx.root/'control')
                        elif value=='empty-origin-with-file':
                            from snapshot_fixtures import EMPTY,regular,tar_bytes
                            target.write_bytes(tar_bytes({**EMPTY,'hidden':regular(b'x')},{'hidden':b'x'}))
                        else:target.write_bytes((b'X'if raw[:1]!=b'X'else b'Y')+raw[1:])
                        if target.exists()and not target.is_symlink():target.chmod(mode)
                elif where=='F_fixture':continue
                else:raise ValueError('unhandled preregistered mutation '+where)
                e=self.launch(fx);self.rejected(e,'execute',e.args(**extra),variant['expected_code']);self.mark(variant['name'])
            finally:
                if restore:restore()
    def owner(self,e):
        from owner_fixture import OwnerFixture
        if not hasattr(e,'owner'):e.owner=OwnerFixture(e.fx.root/'S-originals',e.fx.authority_root,e.fx.namespace)
        return e.owner
    def confirm(self,e,checkpoint,name):
        from owner_fixture import EXEC
        paths=[k for k in checkpoint['files']if k.startswith('sessions/')and k.endswith('.jsonl')]
        require(len(paths)==1,'actual unique original Pi JSONL absent')
        expected={**e.fx.request['session_binding'],'original_execution':{**{k:checkpoint['ref']['source_binding'][k]for k in EXEC},'state':checkpoint['ref']['state']}}
        # Scope source is the previously accepted request/binding, not the owner receipt.
        require(all(expected['original_execution'][k]==e.binding[k]for k in EXEC if k!='freeze_generation'),'checkpoint differs from original accepted execution')
        value=self.owner(e).confirm(name,expected,checkpoint['ref'],{'binding':{'harness':'h1','input':'in1','source':None},'jsonl_relative_path':paths[0],'metadata_relative_path':'metadata.json'})
        return value,expected
    def restore(self,e,checkpoint,mode):
        retained,expected=self.confirm(e,checkpoint,'restore-source')
        original_query=e.call('query');stdout_ref=copy.deepcopy(original_query['artifacts']['stdout'])
        record_root=Path(stdout_ref['path']).parent;record_identity=record_root.stat()
        old_spool={'execution_id':e.binding['execution_id'],'object_generation':e.binding['object_generation'],'request_digest':e.binding['request_digest'],'reservation_id':e.binding['slot_reservation_id'],'path':str(record_root),'root':{'dev':record_identity.st_dev,'ino':record_identity.st_ino},'stdout_ref':stdout_ref,'stdout_raw':read_ref({'path':stdout_ref['path'],'sha256':stdout_ref['sha256'],'bytes':stdout_ref['size']},1048576)[1],'old_pid':e.rpc.p.pid}
        e.observer.stopped(e.binding)
        receipt=self.owner(e).receipt('restore-sealed-transfer',checkpoint['ref'],retained,sealed=True)
        e.call('release_checkpoint',release_id='restore-release-original',original_full_ref=checkpoint['ref'],owner_receipt_ref=receipt)
        require(not Path(checkpoint['ref']['path']).exists()and Path(retained['snapshot_ref']['archive_path']).read_bytes()==checkpoint['raw'],'restore handoff lost owner bytes or retained X debt')
        e.call('await_exit');released=e.call('release')
        old_spool['retained_spool']=self.verify_retained_spool(e,old_spool,'before-restore')
        repeated=e.call('release');require(repeated['artifacts']['slot']==released['artifacts']['slot'],'same release fabricated new slot receipt')
        self.verify_retained_spool(e,old_spool,'same-release')
        require(e.observer.inspect(e.binding['container_id'])is None and e.binding['volume_id']not in e.observer.ids('volume'),'old restore execution/volume was not actually released')
        ns=e.observer.namespaces[e.binding['execution_id']]
        require(not e.observer.process_facts(0,ns,0)['namespace_pids'],'old restore namespace survives')
        e.rpc.stop()  # New connection may acquire the original single-owner journal only now.

        fx=copy.copy(e.fx);fx.request=copy.deepcopy(e.fx.request);fx.authority=copy.deepcopy(e.fx.authority)
        fx.request.update(execution_id='exec-'+uuid.uuid4().hex,snapshot_ref=retained['snapshot_ref'],base_version=sha_bytes(canonical(retained['snapshot_ref'])))
        fx.request['command_argv'][4]=mode;fx.execution_ids.add(fx.request['execution_id']);fx.authority['grant_ref']=fx.grant(fx.request)
        restored=self.launch(fx);restored.prior_spool=old_spool;return restored
    def verify_restore_spool(self,e):
        self.verify_retained_spool(e,e.prior_spool,'after-new-execution')
    def verify_retained_spool(self,e,original,phase):
        query=e.call('query');ref=query['artifacts']['slot']
        slot=strict_json(read_ref({'path':ref['path'],'sha256':ref['sha256'],'bytes':ref['size']},2097152)[1])
        reservation=slot['reservations'][original['reservation_id']]
        require(reservation['state']=='RELEASED'and all(reservation[key]==original[key]for key in ('execution_id','object_generation','request_digest')),'old original reservation binding lost after release')
        debt=reservation['retained_spool'];actual=allocated_originals(original['path'],[original['old_pid'],e.rpc.p.pid])
        require(debt['path']==original['path']and debt['root']==actual['root']==original['root']and actual['allocated_bytes']>0 and actual['inodes']>0,'old retained spool root/physical debt absent')
        require(debt['allocated_bytes']>=actual['allocated_bytes']and debt['inodes']>=actual['inodes'],'old spool actual blocks/inodes undercharged')
        if 'retained_spool'in original:require(debt==original['retained_spool'],'original released spool debt changed on retry/restart')
        raw=read_ref({'path':original['stdout_ref']['path'],'sha256':original['stdout_ref']['sha256'],'bytes':original['stdout_ref']['size']},1048576)[1]
        require(raw==original['stdout_raw'],'old confirmed stdout lost after release')
        rows=list(slot['reservations'].values());live=[x for x in rows if x['state']not in('RELEASED','RECLAIMED')];retired=[x for x in rows if x['state']in('RELEASED','RECLAIMED')]
        for row in retired:
            saved=row['retained_spool'];measured=allocated_originals(saved['path'],[original['old_pid'],e.rpc.p.pid])
            require(Path(saved['path']).is_relative_to(e.fx.state)and saved['root']==measured['root']and saved['allocated_bytes']>=measured['allocated_bytes']and saved['inodes']>=measured['inodes'],'released original spool outside state or undercharged')
        controls=allocated_originals(e.fx.state/'.slots',[e.rpc.p.pid]);physical=allocated_originals(e.fx.state,[original['old_pid'],e.rpc.p.pid])
        charged_bytes=sum(x['writable_bytes']for x in live)+sum(x['retained_spool']['allocated_bytes']for x in retired)+max(0,controls['allocated_bytes']-1048576)
        charged_inodes=sum(x['writable_inodes']for x in live)+sum(x['retained_spool']['inodes']for x in retired)+max(0,controls['inodes']-128)
        require(charged_bytes<=134217728 and charged_inodes<=8192 and physical['allocated_bytes']<=134217728 and physical['inodes']<=8192,'actual retained+active+slot storage exceeds original total')
        save(e.out/('retained-spool-'+phase+'.json'),{'slot_ref':ref,'old_reservation':reservation,'old_actual':actual,'slot_control_actual':controls,'whole_state_actual':physical,'charged_bytes':charged_bytes,'charged_inodes':charged_inodes})
        return copy.deepcopy(debt)
    def finish(self):
        errors=[]
        for e in reversed(self.active):
            try:e.cleanup()
            except Exception as exc:errors.append(repr(exc))
        for peer in reversed(self.peers):
            import subprocess
            subprocess.run(['docker','rm','-f',peer['cid']],capture_output=True,timeout=10)
            subprocess.run(['docker','network','rm',peer['network']],capture_output=True,timeout=10)
        require(not errors,'actual cleanup failed:'+repr(errors))
    def complete(self):
        expected=[v['name']for v in self.variants];require(sorted(self.marked)==sorted(expected),'declared variants not all executed:'+repr(sorted(set(expected)-set(self.marked))))

    def make_peer(self,fx):
        import subprocess
        def run(argv):
            p=subprocess.run(argv,capture_output=True,timeout=10);require(p.returncode==0,'actual peer facility command failed:'+p.stderr.decode());return p.stdout
        env=json.loads((ROOT/'design/g3/x/environment.json').read_text());network='xn-peer-'+uuid.uuid4().hex
        run(['docker','network','create','--internal',network])
        code="import socket;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('0.0.0.0',23456));s.listen();print('ready',flush=True)\nwhile True:\n c,a=s.accept();c.sendall(b'peer-original\\n');c.close()"
        cid=run(['docker','create','--network',network,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','.25','--log-driver','none',env['image'],'python','-c',code]).decode().strip()
        run(['docker','start',cid]);actual=json.loads(run(['docker','inspect',cid]))[0];ip=actual['NetworkSettings']['Networks'][network]['IPAddress']
        self.peers.append({'cid':cid,'network':network,'ip':ip,'before':actual,'run':run})
        # Bounded live server self-connect; not a sleep or stopped-peer negative.
        witness="import socket;s=socket.create_connection((IP,23456),timeout=2);print(s.recv(100).decode());s.close()".replace('IP',repr(ip))
        raw=run(['docker','exec',cid,'python','-c',witness]);require(raw==b'peer-original\n\n','actual live endpoint unavailable')
        self.peers[-1]['witness']=witness
        fx.request['command_argv'] += [ip,'23456'];fx.authority['grant_ref']=fx.grant(fx.request);self.config_revision(fx)
    def peer_witness(self,e):
        p=self.peers[-1];raw=p['run'](['docker','exec',p['cid'],'python','-c',p['witness']]);after=json.loads(p['run'](['docker','inspect',p['cid']]))[0]
        require(raw==b'peer-original\n\n'and after['State']['Running']and not after['State']['Paused']and after['State']['Pid']==p['before']['State']['Pid']and after['State']['StartedAt']==p['before']['State']['StartedAt'],'original live peer changed')
        save(e.out/'actual-live-peer.json',{'before':p['before'],'after':after,'received_base64':base64.b64encode(raw).decode()})
    def owner_lifecycle(self,e,one,two):
        from owner_fixture import verify_receipt
        retained,expected=self.confirm(e,one,'owner-old');successor,_=self.confirm(e,two,'owner-new')
        owner=self.owner(e);receipt=owner.receipt('active-old',one['ref'],retained,two['ref'],successor)
        verify_receipt(receipt,expected,one['ref'])
        from checkpoint_pin_probe import run as read_pin_probe
        read_pin_probe(e,one,receipt)
        live_physical=e.observer.binding(e.binding,live=True);save(e.out/'actual-live-before-sealed-transfer.json',live_physical)
        live_transfer=owner.receipt('live-final-transfer',two['ref'],successor,sealed=True)
        self.rejected(e,'release_checkpoint',e.args(release_id='live-final-rejected',original_full_ref=two['ref'],owner_receipt_ref=live_transfer),'INCOMPLETE_OBSERVATION')
        # Bad refs are actual semantically mutated copies; X must keep the original archive/debt.
        e.seal(two)
        foreign_fx=self.make_fixture('channel',namespace=e.fx.namespace,session_id='prep-session-two')
        foreign=self.launch(foreign_fx);foreign.execute();foreign.ready();foreign.nonce('foreign-original');foreign_cp=foreign.freeze('foreign-original');foreign.seal(foreign_cp)
        foreign_retained,foreign_expected=self.confirm(foreign,foreign_cp,'foreign-owner')
        register(e.fx.authority_root,'snapshot',foreign_retained['snapshot_ref'],foreign_expected)
        variants=[v for v in self.variants if 'owner_receipt_mutation'in v]
        for v in variants:
            bad=copy.deepcopy(receipt);name=v['name']
            if name=='wrong_existing_owner_association':
                # A separately authorized real second Session is prepared by owner_controls and registered here as a foreign fact.
                bad['retained_original_ref']=foreign_retained['snapshot_ref'];bad['retained_owner_record_ref']=foreign_retained['owner_record_ref'];bad['storage_charge_ref']=foreign_retained['storage_charge_ref']
            elif name=='owner_only_flag':bad['retained_original_ref']['archive_path']=str(e.fx.root/'missing-owner-original')
            elif name=='owner_hardlink_alias':
                alias=e.fx.root/'hardlinked-owner';os.link(one['ref']['path'],alias);bad['retained_original_ref']['archive_path']=str(alias)
            elif name=='unconfirmed_successor':bad['successor_owner_record_ref']=None
            elif name=='only_original':bad['retained_original_ref']['archive_path']=one['ref']['path']
            else:raise ValueError('unknown owner mutation')
            # Preserve a real body whose semantic fields match the submitted outer ref.
            body={k:value for k,value in bad.items()if k!='actual_owner_receipt_path_sha_bytes'};path=e.fx.root/('bad-owner-'+name+'.json');save(path,body);bad['actual_owner_receipt_path_sha_bytes']=file_fact(path)[0]
            register(e.fx.authority_root,'owner-receipt',bad,expected)
            self.rejected(e,'release_checkpoint',e.args(release_id='bad-'+name,original_full_ref=one['ref'],owner_receipt_ref=bad),v['expected_code']);self.mark(name)
        e.call('release_checkpoint',release_id='release-old',original_full_ref=one['ref'],owner_receipt_ref=receipt)
        require(not Path(one['ref']['path']).exists(),'original X checkpoint not actually reclaimed')
        require(Path(retained['snapshot_ref']['archive_path']).read_bytes()==one['raw'],'S original bytes lost')
        duplicate=e.call('release_checkpoint',release_id='release-old',original_full_ref=one['ref'],owner_receipt_ref=receipt)
        history=e.call('query_checkpoint',original_full_ref=one['ref']);require(history.get('checkpoint',{}).get('owner_receipt_ref')==receipt,'released checkpoint original ownership history missing')
        e.seal(two);final=owner.receipt('final-transfer',two['ref'],successor,sealed=True)
        e.call('release_checkpoint',release_id='release-final',original_full_ref=two['ref'],owner_receipt_ref=final)
        require(not Path(two['ref']['path']).exists()and Path(successor['snapshot_ref']['archive_path']).read_bytes()==two['raw'],'final sealed ownership transfer lost bytes/retained X debt')
    def alternate(self,e,variant):
        fx=copy.copy(e.fx);fx.request=copy.deepcopy(e.fx.request);fx.authority=copy.deepcopy(e.fx.authority);fx.request['execution_id']='exec-'+uuid.uuid4().hex
        fx.execution_ids={fx.request['execution_id']}
        name=variant['name'];directory=self.out/('alternate-'+name);directory.mkdir()
        # A legal new-ID positive need not own the old journal. Keep only namespace/profile/reference authority shared.
        fx.root=directory;fx.state=directory/'state';fx.state.mkdir();fx.cache=directory/'cache';fx.cache.mkdir()
        (directory/'control').mkdir();(directory/'control/control-canary').write_bytes(fx.canary)
        fx.slot=copy.deepcopy(e.fx.slot);fx.slot['state_root']=str(fx.state)
        fx.config=copy.deepcopy(e.fx.config);fx.config['state_root']=str(fx.state)
        fx.config['slots']=[{**copy.deepcopy(slot),'state_root':str(fx.state)}for slot in fx.config['slots']]
        if name=='Node_manifest':
            old=fx.request['readonly_mounts'][0]['manifest_ref'];path=directory/'manifest.json';path.write_bytes(read_ref(old,2097152)[1]+b'\n')
            fx.request['readonly_mounts'][0]['manifest_ref']=file_fact(path)[0]
        elif name=='command_args':fx.request['command_argv'][4]='read-files'
        else:
            source=directory/'source';source.mkdir();role='harness'if name=='Harness_ref'else 'input'
            old=Path(next(m for m in e.fx.mounts if m['role']==role)['source']['path']);shutil.copytree(old,source,dirs_exist_ok=True)
            (source/'additional-original.txt').write_bytes(b'OTHER_LEGITIMATE_ORIGINAL\n')
            facility=FInputs(directory/'F');mount=facility.view(role,source)
            index=1 if role=='harness'else 2;fx.request['readonly_mounts'][index]=mount
            if role=='harness':fx.request['harness_version']=mount['content_ref']['version_ref']
        for mount in fx.request['readonly_mounts']:register(fx.authority_root,'readonly-view',mount,{'namespace':fx.namespace,'role':mount['role']})
        fx.authority['grant_ref']=fx.grant(fx.request)
        fx.config['grants']=[fx.authority['grant_ref']];fx.config['read_only_roots']=copy.deepcopy(fx.request['readonly_mounts'])
        fx.config_path=directory/'trusted-config.json';save(fx.config_path,fx.config)
        require(fx.state!=e.fx.state and fx.namespace==e.fx.namespace and fx.request['profile_sha256']==e.fx.request['profile_sha256'],'alternate positive fixture changed namespace/profile or reused old state')
        save(directory/'independent-positive-binding.json',{'old_state':str(e.fx.state),'new_state':str(fx.state),'namespace':fx.namespace,'profile_sha256':fx.request['profile_sha256'],'config_ref':file_fact(fx.config_path)[0],'request':fx.request,'authority':fx.authority})
        return self.launch(fx)
    def shared_tool(self,e):
        spec=importlib.util.spec_from_file_location('xn_original_python_fixture',ROOT/'validation/components/x/fixtures.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        fx=module.create(self.out/'original-python-tool',{'initial':{'script':'heartbeat'}},{'domain':'task','cpu':.25})
        request=fx['request'];e.fx.execution_ids.add(request['execution_id']);authority={**fx['authority'],'namespace':e.fx.namespace,'state_dir':str(e.fx.state),'slot_ref':{**e.fx.slot_ref,'role':'tool'}}
        authority['grant_ref']=self.tool_grant(e,request,authority)
        value=e.rpc.call('execute',{'request':request,'authority':authority,'binding':{},'state_dir':str(e.fx.state)})
        require('error'not in value and value.get('binding'),'legitimate original tool failed');return {'request':request,'authority':authority,'binding':value['binding'],'response':value}
    def slot_record(self,e):
        value=e.call('query');ref=value.get('artifacts',{}).get('slot');require(ref is not None,'actual original slot record unavailable')
        fact,raw=read_ref({'path':ref['path'],'sha256':ref['sha256'],'bytes':ref['size']},2097152);record=strict_json(raw)
        require(record['slot_id']==e.fx.slot_ref['slot_id']and record['revision']==1 and record['plan']==e.fx.slot['plan']and record['plan_sha256']==e.fx.slot_ref['plan_sha256'],'actual original slot plan differs')
        return record
    def assert_shared_slot(self,e,tool):
        record=self.slot_record(e);rows=list(record['reservations'].values())if isinstance(record['reservations'],dict)else record['reservations']
        active=[x for x in rows if x['state']not in('RELEASED','RECLAIMED')]
        require({'session','tool','helper'}<={x['role']for x in active},'shared roles not actually reserved')
        require(sum(x['memory_bytes']for x in active)<=805306368 and sum(x['cpu']for x in active)<=1,'shared memory/CPU overcommitted')
        require(sum(x['writable_bytes']for x in active)<=134217728 and sum(x['writable_inodes']for x in active)<=8192,'shared storage/inode reservation overflow')
        facts=[e.observer.inspect(e.binding['container_id']),e.observer.inspect(tool['binding']['container_id'])]
        require(all(x['State']['Running']for x in facts)and sorted(x['HostConfig']['Memory']for x in facts)==[134217728,536870912],'actual two original roles absent')
        host=[p for p in e.fx.state.rglob('*')if p.is_file()];allocated=sum(p.stat().st_blocks*512 for p in host)
        fds=[]
        for p in Path('/proc/'+str(e.rpc.p.pid)+'/fd').iterdir():
            try:
                target=os.readlink(p)
                if target.startswith(str(e.fx.state))and target.endswith(' (deleted)'):fds.append({'fd':p.name,'target':target,'bytes':p.stat().st_blocks*512})
            except FileNotFoundError:pass
        require(allocated+sum(x['bytes']for x in fds)<134217728,'actual original host spool over budget')
        save(e.out/'actual-shared-slot.json',{'original_record':record,'actual_engine':facts,'actual_host_allocated':allocated,'deleted_open':fds,'static_worst_overlap_bytes':114425856})
        e.observer.volume_bytes(e.binding['volume_id'])  # Real third128MiB RO helper, serial and within original plan.
    def tool_grant(self,e,request,authority):
        record={'principal':'trusted-S','operations':['execute','query','checkpoint','stop'],'original_request':copy.deepcopy(request),'request_digest':sha_bytes(canonical(request)),'scope':{'namespace':e.fx.namespace},'slot_ref':authority['slot_ref'],'role':'tool'}
        key=record['request_digest'];path=e.fx.authority_root/('tool-grant-'+key+'.json');save(path,record)
        grant={'owner':'trusted-X-configuration','id':key,'record_path':str(path),'sha256':file_fact(path)[0]['sha256']}
        register(e.fx.authority_root,'grant',grant,record['scope']);return grant
    def reject_second_tool(self,e,tool):
        request=copy.deepcopy(tool['request']);request['execution_id']='extra-tool-'+uuid.uuid4().hex
        authority=copy.deepcopy(tool['authority']);authority['grant_ref']=self.tool_grant(e,request,authority)
        self.rejected(e,'execute',{'request':request,'authority':authority,'binding':{},'state_dir':str(e.fx.state)},'SLOT_EXHAUSTED')
    def reject_private_overflow(self,e,kind):
        record=self.slot_record(e);budget=record['plan'];require(budget['all_active_writable_bytes']==134217728 and budget['all_active_writable_inodes']==8192,'registered aggregate bound differs')
        # No reserve_spool API: use the original admitted object limits plus exact actual reservation boundary.
        require(114425856<budget['all_active_writable_bytes'],'fixed-profile overlap cannot fit original slot')
        request=copy.deepcopy(e.fx.request);request['execution_id']='over-'+kind+'-'+uuid.uuid4().hex
        field='archive_bytes'if kind=='bytes'else 'archive_entries';request['budgets'][field]=budget['all_active_writable_bytes']+1 if kind=='bytes'else budget['all_active_writable_inodes']+1
        grant=e.fx.grant(request);self.rejected(e,'execute',e.args(request=request,authority={**e.fx.authority,'grant_ref':grant}),'INVALID_REQUEST')
        require(self.slot_record(e)==record,'rejected overflow changed original shared budget')
    def reservation_cut(self,e):
        request=copy.deepcopy(e.fx.request);request['execution_id']='reservation-cut-'+uuid.uuid4().hex;grant=e.fx.grant(request)
        args=e.args(request=request,authority={**e.fx.authority,'grant_ref':grant},test_context={'requested_barrier':'slot_reserved_before_engine_create'})
        # Stop/release existing roles must happen first to leave a legal reservation; no fourth object requested.
        current=e.checkpoints[-1];e.observer.stopped(e.binding)
        retained,_=self.confirm(e,current,'reservation-final-owner')
        receipt=self.owner(e).receipt('reservation-final-transfer',current['ref'],retained,sealed=True)
        e.call('release_checkpoint',release_id='reservation-final-release',original_full_ref=current['ref'],owner_receipt_ref=receipt)
        e.call('await_exit');e.call('release')
        require(e.observer.inspect(e.binding['container_id'])is None and e.binding['volume_id']not in e.observer.ids('volume'),'released original container/volume still exists')
        ns=e.observer.namespaces[e.binding['execution_id']];require(not e.observer.process_facts(0,ns,0)['namespace_pids'],'released namespace still has live tasks')
        record=self.slot_record(e);rows=list(record['reservations'].values())if isinstance(record['reservations'],dict)else record['reservations']
        require(not any(row['role']=='session'and row['state']not in('RELEASED','RECLAIMED')for row in rows),'old Session reservation still occupied')
        arrived=e.rpc.call('execute',args,barrier='slot_reserved_before_engine_create');require(arrived.get('test_barrier')=='slot_reserved_before_engine_create','actual reservation cut missing')
        e.rpc.stop();e.rpc.start();query_args=copy.deepcopy(args);query_args.pop('test_context',None)
        value=e.rpc.call('query',query_args)
        require(value.get('binding',{}).get('execution_id')==request['execution_id']and value.get('result',{}).get('execution_state')in('PREPARING','UNKNOWN','CREATED'),'original reserved responsibility not queryable')
    def owner_release_cuts(self,e,one,two):
        old=one;current=two
        for index,barrier in enumerate(['checkpoint_release_persisted_before_unlink','checkpoint_unlinked_before_ack']):
            retained,expected=self.confirm(e,old,'cut-old-'+str(index));successor,_=self.confirm(e,current,'cut-successor-'+str(index))
            receipt=self.owner(e).receipt('cut-owner-'+str(index),old['ref'],retained,current['ref'],successor)
            release_id='release-cut-'+str(index)
            args=e.args(release_id=release_id,original_full_ref=old['ref'],owner_receipt_ref=receipt,test_context={'requested_barrier':barrier})
            value=e.rpc.call('release_checkpoint',args,barrier=barrier);require(value.get('test_barrier')==barrier,'actual release cut missing')
            if barrier.endswith('before_unlink'):require(Path(old['ref']['path']).read_bytes()==old['raw'],'source absent before unlink')
            else:require(not Path(old['ref']['path']).exists(),'source still present after unlink')
            e.rpc.stop();e.rpc.start();result=e.rpc.call('query_checkpoint',e.args(original_full_ref=old['ref']))
            require('error'not in result and Path(retained['snapshot_ref']['archive_path']).read_bytes()==old['raw'],'owner handoff query lost original bytes')
            e.call('release_checkpoint',release_id=release_id,original_full_ref=old['ref'],owner_receipt_ref=receipt)
            require(not Path(old['ref']['path']).exists(),'release did not physically reclaim original source')
            original_record=self.slot_record(e)
            e.call('release_checkpoint',release_id=release_id,original_full_ref=old['ref'],owner_receipt_ref=receipt)
            require(self.slot_record(e)==original_record,'same release returned duplicate reservation credit')
            if index==0:
                before=copy.deepcopy(e.binding);original_calls=copy.deepcopy(e.calls)
                # Resume only the original keeper namespace. The lost Node attach is never recreated.
                e.call('resume',receipt=current['ref'])
                third=e.freeze('third-after-release')
                require(all(e.binding[k]==before[k]for k in ('container_id','exec_id','object_generation','channel_id')),'new checkpoint replaced original physical execution')
                require(third['ref']['freeze_generation']>current['ref']['freeze_generation'],'new checkpoint lacks an actual newer freeze')
                require(third['files']==current['files']and e.calls==original_calls,'lost-owner checkpoint changed original Session bytes or replayed channel input')
                e.compare_channel(third,['one','two'])
                save(e.out/'actual-capacity-after-release.json',{'original_binding':before,'new_checkpoint':third['ref'],'original_files_sha256':{k:sha_bytes(v)for k,v in current['files'].items()},'channel_calls_unchanged':True,'scope':'new physical freeze and capacity reuse only; no reattachment or semantic progress'})
                old,current=current,third
        e.seal(current)
    def default_F_limit(self):
        from lore_files import FileStore,FileError
        large=self.make_fixture('read-files',True);source=Path(large.mounts[3]['source']['path']);facility=FInputs(self.out/'default-F-fixture')
        facility.store=FileStore(facility.root/'default-control',facility.auth,facility.ref)
        try:facility.view('workspace',source)
        except FileError as exc:require(exc.code=='LIMIT_EXCEEDED','wrong actual F default failure')
        else:raise ValueError('actual default F silently accepted oversized complete set')
