"""Twelve fixed scenario bodies. All product operations go through the original X port."""
from pathlib import Path
import base64,copy,json,os,signal,time
from artifacts import canonical,file_fact,read_ref,require,save,sha_bytes,strict_json
from rpc import ShortPeerBridge
from observer import ENV

def channel(ctx):
    e=ctx.new('channel');e.execute();e.ready();return e

def readonly(ctx,large=False):
    e=ctx.new('read-files',large=large);e.execute();facts=e.ready('read-files')
    require(facts['uid']==1000 and facts['gid']==1000 and facts['node_version']=='v24.21.0','actual Node identity/version differs')
    require(all(not item['wrote']and item['code']in('EROFS','EACCES')for item in facts['attempts']),'ordinary task wrote readonly mount')
    require(not facts['forbidden'],'task read forbidden original')
    for role in ('input','workspace'):
        mount=next(m for m in e.fx.mounts if m['role']==role)
        manifest=strict_json(read_ref(mount['manifest_ref'],2097152)[1])
        expected={n:(v['byte_length'],v['sha256'])for n,v in manifest['entries'].items()if v['kind']=='file'}
        actual={v['path']:(v['bytes'],v['sha256'])for v in facts[role]if v['kind']=='file'}
        require(actual==expected,'actual Node omitted/changed original '+role+' files')
    expected_mounts={'/work':(16777216,512),'/tmp':(33554432,2048),'/dev/shm':(1048576,64)}
    require({x['mount']:(x['bytes'],x['inodes'])for x in facts['mounts']}==expected_mounts,'actual Node writable mounts differ')
    e.write(b'release\n');e.call('await_exit');checkpoint=e.freeze('read-files-final');e.seal(checkpoint)
    return e,facts

def XN01(ctx):
    e=ctx.new('pi-accept');e.execute(live=False);first=e.call('await_exit');cp=e.freeze('pi-accept')
    require(e.observer.exec_inspect(e.binding['exec_id'])['ExitCode']==0,'actual accept Node exit differs')
    outputs=[strict_json(line)for line in e.stream_original().splitlines()]
    require(outputs[-1]['accepted']['ok']is True and outputs[-1]['providerCalls']==0,'actual accept failed or drove provider')
    require(not cp['files'].get('provider.jsonl',b'')and not cp['files'].get('effects.jsonl',b''),'accept dispatched actual provider/effect')
    original=[v for k,v in cp['files'].items()if k.startswith('sessions/')and k.endswith('.jsonl')]
    require(len(original)==1 and b'op-1'in original[0],'original accepted operation identity absent')
    e.seal(cp);e2=ctx.restore(e,cp,'pi-query');e2.execute(live=False);ctx.verify_restore_spool(e2);e2.call('await_exit');again=e2.freeze('pi-query')
    require(not again['files'].get('effects.jsonl',b'')and not again['files'].get('provider.jsonl',b''),'restored query dispatched provider/effect')
    restored=[v for k,v in again['files'].items()if k.startswith('sessions/')and k.endswith('.jsonl')]
    require(restored==original,'query changed the original Session JSONL')
    require(e2.observer.exec_inspect(e2.binding['exec_id'])['ExitCode']==0,'actual query Node exit differs')
    outputs=[strict_json(line)for line in e2.stream_original().splitlines()]
    require(outputs[-1]['providerCalls']==0,'actual query invoked provider')
    e2.seal(again);ctx.generic_negatives()

def XN02(ctx):
    e=channel(ctx);e.nonce('source-positive');cp=e.freeze('source-positive');e.compare_channel(cp,['source-positive']);e.seal(cp)
    ctx.generic_negatives()

def XN03(ctx):
    readonly(ctx);ctx.generic_negatives()

def XN04(ctx):
    e=channel(ctx);e.nonce('authorized-session');cp=e.freeze('authorized-session');e.compare_channel(cp,['authorized-session']);e.seal(cp)
    ctx.generic_negatives()

def XN05(ctx):
    e=ctx.new('isolation',network_peer=True);e.execute();facts=e.ready('read-files')
    require(not facts['forbidden'],'Node read forbidden host path')
    require(not facts['connection']['connected']and facts['connection']['code']=='ENETUNREACH','actual isolated Node reached real peer')
    require(all(not x['wrote']for x in facts['attempts']),'actual readonly confinement failed')
    require('LORE_TEST_CONTROL_CANARY'not in base64.b64decode(facts['environment']).decode(errors='replace'),'host environment canary leaked')
    require(not any('control-canary'in x['target']for x in facts['fd']),'host original control FD leaked')
    ctx.peer_witness(e);e.write(b'release\n');e.call('await_exit');cp=e.freeze('isolated-final');e.seal(cp);ctx.generic_negatives()

def XN06(ctx):
    readonly(ctx)
    for name,mode in [('work_bytes','quota-bytes'),('work_unlinked','quota-unlinked'),('work_inodes','quota-inodes')]:
        e=ctx.new(mode);e.execute();value=e.ready('quota-full');volume=e.observer.volume_bytes(e.binding['volume_id'])
        require(value['error']['code']=='ENOSPC','actual Node quota did not fail ENOSPC')
        require(volume['inodes_free']==0 if mode=='quota-inodes'else volume['bytes_free']==0,'independent quota fullness absent')
        e.write(b'release\n');e.call('await_exit');cp=e.freeze(name);e.seal(cp);ctx.mark(name)
    e=ctx.new('output-flood');e.execute();e.ready('flood-ready');e.write(b'release\n');value=e.call('await_exit')
    require(value['result']['reason']=='OUTPUT_LIMIT'and value['result']['output_state']=='INCOMPLETE_LIMIT','output-limit original result differs')
    e.observer.stopped(e.binding)
    streams={name:read_ref({'path':ref['path'],'sha256':ref['sha256'],'bytes':ref['size']},1048576)[1]for name,ref in value['artifacts'].items()if name in('stdout','stderr')}
    require(set(streams)=={'stdout','stderr'}and 0<sum(map(len,streams.values()))<=2097152,'original bounded partial output absent')
    ctx.mark('output_flood')

def XN07(ctx):
    e=channel(ctx);e.bridge=ShortPeerBridge(e.rpc,e.out/'peers')
    writes=[]
    for n in ['first','second','third']:
        value,fields,args=e.nonce(n,call_id='nonce-'+n,transport=e.bridge);writes.append((value,fields,args))
    require(len({row['pid']for row in e.bridge.rows})==3,'three actual short peers did not execute')
    original,fields,args=writes[0]
    retry=e.rpc.call('channel_write',args);require(retry['call_ref']==original['call_ref'],'known duplicate call changed original receipt')
    query=e.rpc.call('query_call',e.args(**fields));require(query['call_ref']==original['call_ref'],'direct X query differs from bridge original call')
    for name,key,value,code in [('changed_call_bytes','data_base64',base64.b64encode(b'different\n').decode(),'ID_CONFLICT'),('changed_cursor','byte_offset',999,'ID_CONFLICT'),('wrong_channel','channel_id','foreign-original-channel','UNAUTHORIZED')]:
        bad=copy.deepcopy(args);bad[key]=value;ctx.rejected(e,'channel_write',bad,code);ctx.mark(name)
    cp=e.freeze('short-peers');entries=e.compare_channel(cp,['first','second','third'])
    require(len({x['pid']for x in entries})==1,'short peers restarted the actual Node')
    e.seal(cp)

def XN08(ctx):
    for name,barrier in [('lost_ack','channel_written_before_ack'),('partial_write','channel_prefix_written_before_ack'),('bridge_restart','channel_written_before_ack')]:
        e=channel(ctx);fields=e.call_fields('channel_write','original-'+name,0)
        payload={'nonce':name}
        if name=='partial_write':payload['padding']='p'*131072
        data=canonical(payload)+b'\n';args=e.args(**fields,data_base64=base64.b64encode(data).decode(),test_context={'requested_barrier':barrier})
        arrived=e.rpc.call('channel_write',args,barrier=barrier);require(arrived.get('test_barrier')==barrier,'actual write barrier missing')
        require(arrived.get('binding')==e.binding,'barrier changed original object')
        barrier_record=e.call_record(arrived,fields,data)
        written=barrier_record['written_bytes'];require(type(written)is int and 0<written<=len(data),'actual saved write prefix missing')
        if name=='partial_write':require(written<len(data),'physical send did not leave a strict prefix')
        else:require(written==len(data),'full write barrier lacks complete original input')
        # Actual X receipt/store original at its physical-write boundary, not a bridge ledger.
        current=e.rpc.p.pid;physical=e.observer.binding(e.binding,live=True)
        require(physical['exec']['Running'],'original Node missing at ACK cut')
        # The external observer reads the actual task-owned files while the original writer is at its cut.
        # It does not require a new owner to recover the old stdout attach.
        probe=r"""import pathlib,time,json,base64,sys
expected=base64.b64decode(sys.argv[1]);partial=sys.argv[2]=='partial';full_length=int(sys.argv[3]);deadline=time.monotonic()+5
while time.monotonic()<deadline:
 received=pathlib.Path('/work/received.bin').read_bytes();channel=pathlib.Path('/work/channel.jsonl').read_bytes()
 if partial and received==expected and 0<len(received)<full_length and not channel:break
 if not partial and received==expected and channel.endswith(b'\n') and [json.loads(x)['nonce']for x in channel.splitlines()]==[json.loads(expected)['nonce']]:break
 time.sleep(.01)
else:raise SystemExit('actual Node input prefix/nonce did not become durable')
print(json.dumps({'received_base64':base64.b64encode(received).decode(),'channel_base64':base64.b64encode(channel).decode()}))
"""
        observed,helper=e.observer.helper(['--user','1000:1000','--mount','type=volume,src='+e.binding['volume_id']+',dst=/work,readonly,volume-nocopy',ENV['image'],'python','-c',probe,base64.b64encode(data[:written]).decode(),'partial'if name=='partial_write'else 'complete',str(len(data))],limit=2097152)
        node_original=strict_json(observed);actual_received=base64.b64decode(node_original['received_base64'],validate=True)
        save(e.out/'node-input-before-owner-cut.json',{'original':node_original,'helper':helper})
        e.rpc.stop();e.rpc.start();value=e.rpc.call('query_call',e.args(**fields))
        require('error'not in value or value['error']['code']=='INCOMPLETE_OBSERVATION','unknown call converted to unrelated error')
        record=e.call_record(value,fields,data)
        require(record['written_bytes']==written,'original recovered call changed physical write prefix')
        require(record['state']in('ISSUED','UNKNOWN','CONFIRMED'),'original unknown history missing')
        if name=='partial_write':require(record['state']=='UNKNOWN'and 0<record['written_bytes']<len(data),'actual partial prefix not retained')
        before=e.observer.exec_inspect(e.binding['exec_id']);again=e.rpc.call('query_call',e.args(**fields));require(again['call_ref']==value['call_ref'],'read-only query fabricated new original receipt')
        e.call('request_stop',stop_id='stop-'+name)
        cp=e.freeze('ack-cut-'+name);received=cp['files'].get('received.bin',b'')
        require(received==actual_received==data[:record['written_bytes']]and len(received)>0,'actual Node received prefix differs from original write record')
        if name=='partial_write':require(len(received)<len(data)and not cp['files'].get('channel.jsonl',b''),'partial request was completed or replayed')
        else:e.compare_channel(cp,[name]);require(received==data,'complete call did not reach actual Node exactly once')
        e.seal(cp)
        require(before['ContainerID']==e.binding['container_id'],'owner restart substituted a new object')
        save(e.out/'actual-ack-cut.json',{'killed_adapter_pid':current,'original_physical':physical,'original_record':record})
        e.cleanup();ctx.active.remove(e)  # Each successful independent cut releases its own physical scope.
        ctx.mark(name)

def XN09(ctx):
    e=channel(ctx);e.nonce('before');one=e.freeze('old');e.resume(one);e.nonce('after');two=e.freeze('new')
    e.compare_channel(two,['before','after'])
    old_jsonl=[v for k,v in one['files'].items()if k.startswith('sessions/')and k.endswith('.jsonl')]
    new_jsonl=[v for k,v in two['files'].items()if k.startswith('sessions/')and k.endswith('.jsonl')]
    require(len(old_jsonl)==len(new_jsonl)==1 and new_jsonl[0].startswith(old_jsonl[0])and len(new_jsonl[0])>len(old_jsonl[0]),'actual same-object Pi original JSONL did not grow')
    ctx.owner_lifecycle(e,one,two);ctx.generic_negatives(only_mutations=True)

def XN10(ctx):
    e=channel(ctx);e.nonce('original');cp=e.freeze('original');e.seal(cp)
    for variant in ctx.variants:
        other=ctx.alternate(e,variant);other.execute();other.ready()if other.fx.request['command_argv'][4]=='channel'else other.ready('read-files')
        if other.fx.request['command_argv'][4]=='channel':other.nonce('other')
        else:other.write(b'release\n');other.call('await_exit')
        changed=other.freeze('legal-other');other.seal(changed)
        other.cleanup()  # Seal and remove only this positive fixture's own physical objects before the next variant.
        ctx.active.remove(other)  # Cleanup succeeded; failures remain owned by the outer finally.
        request=copy.deepcopy(other.fx.request);request['execution_id']=e.fx.request['execution_id'];grant=e.fx.grant(request)
        args=e.args(request=request,authority={**e.fx.authority,'grant_ref':grant})
        ctx.rejected(e,'execute',args,'ID_CONFLICT');ctx.mark(variant['name'])

def XN11(ctx):
    e=channel(ctx);tool=ctx.shared_tool(e);ctx.assert_shared_slot(e,tool)
    ctx.reject_second_tool(e,tool);ctx.mark('fourth_object')
    ctx.reject_private_overflow(e,'bytes');ctx.mark('over_private_bytes')
    ctx.reject_private_overflow(e,'inodes');ctx.mark('over_private_inodes')
    ctx.rejected(e,'register_slot',e.args(slot={'slot_id':'new','max_objects':999}),'INVALID_REQUEST');ctx.mark('peer_register_slot')
    e.nonce('one');one=e.freeze('slot-one');e.resume(one);e.nonce('two');two=e.freeze('slot-two')
    ctx.rejected(e,'checkpoint',e.args(checkpoint_id='slot-three-before-release',purpose='checkpoint'),'SLOT_EXHAUSTED');ctx.mark('third_checkpoint_without_release')
    ctx.owner_release_cuts(e,one,two);ctx.mark('checkpoint_release_crash')
    ctx.reservation_cut(e);ctx.mark('crash_reserved_before_create')

def XN12(ctx):
    e,facts=readonly(ctx,large=True)
    require(len([x for x in facts['workspace']if x['kind']=='file'])==513,'large Node input omitted original files')
    ctx.default_F_limit();ctx.mark('default_F_limits');ctx.generic_negatives(only_mutations=True,exclude={'default_F_limits'})

CASES={name:globals()[name]for name in ['XN01','XN02','XN03','XN04','XN05','XN06','XN07','XN08','XN09','XN10','XN11','XN12']}
