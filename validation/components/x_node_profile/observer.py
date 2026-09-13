"""External Engine/kernel/file observations for the fixed Node profile, no X import."""
from pathlib import Path
import copy,json,sys
from artifacts import archive_bytes,canonical,file_fact,read_ref,require,save,sha_bytes,strict_json
from fixtures import tree as readonly_tree
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/x'))
from collector import Collector,ENV

class NodeObserver(Collector):
    def __init__(self,out,fixture):
        Path(out).mkdir(parents=True,exist_ok=False)
        self.fixture=fixture;self.limit_objects=3;self.limit_memory=805306368
        self.known_helpers=set();self.helper_owner=fixture.request['execution_id']
        super().__init__(out,fixture.mapping())
    def options(self,network='none'):
        return ['--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true',
                '--security-opt','seccomp='+str(ROOT/ENV['seccomp']['path']),'--network',network,
                '--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','.25','--shm-size','1m',
                '--tmpfs','/dev/shm:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64',
                '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64','--log-driver','none']
    def helper(self,args,limit=20*1024*1024):
        owned=[cid for cid in self.ids('container')if cid not in self.baseline_containers]
        actual=[self.inspect(cid)for cid in owned]
        actual=[x for x in actual if x['State']['Status']not in('exited','dead')]
        require(len(actual)<self.limit_objects and sum(x['HostConfig']['Memory']for x in actual)+134217728<=self.limit_memory,'fixed Node shared helper slot exhausted')
        cid=self.run(['docker','create',*self.options(),'--label','lore.validation.xn_owner='+self.helper_owner,*args])[1].decode().strip()
        self.known_helpers.add(cid)
        try:
            before=self.inspect(cid);rc,raw,err=self.run(['docker','start','-a',cid],limit=limit,check=False);after=self.inspect(cid)
            require(rc==0 and after['State']['ExitCode']==0,'external observer helper failed')
            return raw,{'before':before,'after':after}
        finally:
            self.run(['docker','rm','-f',cid],check=False)
            require(self.cleanup_inspect('container',cid)is None,'original observer helper remains after removal')
            self.known_helpers.discard(cid)
    def binding(self,binding,live=False):
        required=json.loads((ROOT/'design/g3/x-node-profile/interface.json').read_text())['binding_return']['required']
        require(all(k in binding for k in required),'complete actual Node binding absent')
        request=self.fixture.request
        for key in ['execution_id','object_generation']:
            require(binding[key]==request[key],'original request binding differs:'+key)
        for key in ['namespace','session_id','session_generation']:
            require(binding[key]==request['session_binding'][key],'original Session differs:'+key)
        require(binding['request_digest']==sha_bytes(canonical(request)),'complete request digest differs')
        require(binding['profile_sha256']==request['profile_sha256'],'profile binding differs')
        before=self.inspect(binding['container_id']);ex=self.exec_inspect(binding['exec_id'])
        require(before is not None and ex is not None and ex['ContainerID']==before['Id'],'actual original Engine objects absent')
        require(ex['ProcessConfig']['entrypoint']==request['command_argv'][0] and ex['ProcessConfig']['arguments']==request['command_argv'][1:],'actual ordinary Node argv differs')
        require(str(ex['ProcessConfig']['user'])in('1000','1000:1000'),'actual Node exec user differs')
        h=before['HostConfig'];require(h['Memory']==536870912 and h['MemorySwap']==536870912 and h['NanoCpus']==500000000,'actual Node memory/CPU differs')
        require(h['NetworkMode']=='none' and h['ReadonlyRootfs'] and 'ALL'in h['CapDrop'],'actual Node confinement differs')
        mounts={x['Destination']:x for x in before['Mounts']}
        for item in request['readonly_mounts']:
            got=mounts.get(item['target']);require(got is not None and got['Source']==item['source']['path'] and got['RW']is False,'actual readonly source/mount differs')
            manifest=strict_json(read_ref(item['manifest_ref'],2097152)[1])
            require(readonly_tree(Path(item['source']['path']))==manifest['entries'],'registered readonly source changed')
        work=mounts.get('/work');require(work is not None and work['Type']=='volume' and work['Name']==binding['volume_id'],'actual work volume differs')
        info=json.loads(self.run(['docker','volume','inspect',work['Name']])[1])[0]
        require(info['Driver']=='local'and info['Mountpoint']==work['Source'],'actual volume source differs')
        if live:
            require(before['State']['Running']and ex['Running'],'actual Node not live')
            process=self.process_facts(before['State']['Pid'],None,ex['Pid']);self.namespaces[binding['execution_id']]=process['namespace']
            require(process['task_status'].get('Uid','').split()==['1000']*4,'actual /proc Node UID differs')
            require(int(process['task_status']['CapEff'].strip(),16)==0,'actual Node capabilities nonzero')
        else:
            process=self.process_facts(before['State']['Pid'],None,ex.get('Pid',0))
            self.namespaces[binding['execution_id']]=process['namespace']
        return {'binding':copy.deepcopy(binding),'container':before,'exec':ex,'volume':info,'process':process}
    def checkpoint(self,api,binding,tag):
        physical=self.binding(binding);require(physical['container']['State']['Paused'],'checkpoint requires actually paused original object')
        ref=api['artifacts']['checkpoint'];fact,raw=file_fact(ref['path'])
        require(ref['sha256']==fact['sha256']and ref['size']==fact['bytes']and ref['source_binding']==binding,'original checkpoint ref differs')
        entries,files,logical=archive_bytes(raw)
        args=['--user','0:0','--cap-add','DAC_OVERRIDE','--mount','type=volume,src='+binding['volume_id']+',dst=/work,readonly,volume-nocopy',ENV['image'],'tar','--format=pax','--acls','--xattrs','--numeric-owner','--pax-option=delete=atime,delete=ctime','-cpf','-','-C','/work','.']
        independent,helper=self.helper(args);other,otherfiles,otherlogical=archive_bytes(independent)
        require(entries==other and files==otherfiles and logical==otherlogical,'actual paused private tree differs from original checkpoint')
        (self.out/(tag+'-independent.tar')).write_bytes(independent)
        observation={'physical':physical,'archive_fact':fact,'entries':entries,'logical_bytes':logical,'helper':helper}
        save(self.out/(tag+'-actual.json'),observation)
        return {'ref':copy.deepcopy(ref),'raw':raw,'entries':entries,'files':files,'physical':physical}
    def stopped(self,binding):
        st=self.inspect(binding['container_id']);ex=self.exec_inspect(binding['exec_id'])
        require(st is not None and not st['State']['Running']and not st['State']['Paused'],'original keeper not stopped')
        require(ex is None or not ex['Running'],'original Node exec remains running')
        ns=self.namespaces.get(binding['execution_id'])
        require(ns is not None,'original namespace observation missing')
        process=self.process_facts(0,ns,0);require(not process['namespace_pids'],'original namespace tasks survive')
        return {'container':st,'exec':ex,'namespace':process}
    def no_new_objects(self,before):
        after={'containers':self.ids('container'),'volumes':self.ids('volume')}
        require(after==before,'rejected request changed physical inventory');return after
    def inventory(self):return {'containers':self.ids('container'),'volumes':self.ids('volume')}

    def cleanup_inspect(self,kind,name):
        require(isinstance(name,str)and name,'missing original cleanup identity')
        if kind=='container':require(len(name)==64 and all(c in '0123456789abcdef'for c in name),'non-full original cleanup CID')
        argv=['docker','inspect',name]if kind=='container'else['docker','volume','inspect',name]
        rc,raw,err=self.run(argv,check=False)
        if rc:
            message=err.decode(errors='replace').lower()
            require(name.lower()in message and any(x in message for x in ('no such object','no such container','no such volume')),
                    'cleanup inspect failed without original not-found proof:'+message)
            return None
        value=strict_json(raw);require(isinstance(value,list)and len(value)==1,'invalid original cleanup inspect')
        return value[0]
    def cleanup_owned(self,bindings,execution_ids):
        facts={'attempts':[],'namespaces':{},'failures':[]};known={'container':set(self.known_helpers),'volume':set()}
        for binding in bindings:
            if binding.get('execution_id')in execution_ids:
                for kind,key in [('container','container_id'),('volume','volume_id')]:
                    if binding.get(key):known[kind].add(binding[key])
        def attempt(kind,name):
            row={'kind':kind,'id':name};facts['attempts'].append(row)
            try:
                before=self.cleanup_inspect(kind,name);row['before']=before
                if before is not None:
                    labels=(before.get('Config',{}).get('Labels')if kind=='container'else before.get('Labels'))or{}
                    require(labels.get('lore.x.execution_id')in execution_ids or(kind=='container'and labels.get('lore.validation.xn_owner')==self.helper_owner),
                            'cleanup identity is not owned by this fixture')
                    argv=['docker','rm','-f',name]if kind=='container'else['docker','volume','rm',name]
                    rc,raw,err=self.run(argv,check=False);row.update(remove_exit=rc,remove_stdout=raw.decode(errors='replace'),remove_stderr=err.decode(errors='replace'))
                after=self.cleanup_inspect(kind,name);row['absent']=after is None
                require(after is None,'original '+kind+' remains after cleanup')
            except Exception as exc:row['error']=repr(exc);facts['failures'].append({'kind':kind,'id':name,'error':repr(exc)})
        # Known exact identities are attempted before any container/volume listing.
        for kind in ('container','volume'):
            for name in sorted(known[kind]):attempt(kind,name)
        for kind in ('container','volume'):
            selectors=['lore.x.execution_id='+value for value in sorted(execution_ids)]
            if kind=='container':selectors.append('lore.validation.xn_owner='+self.helper_owner)
            discovered=set()
            for selector in selectors:
                try:
                    argv=['docker','ps','-aq','--no-trunc']if kind=='container'else['docker','volume','ls','-q']
                    names=self.run([*argv,'--filter','label='+selector])[1].decode().split();discovered.update(names)
                except Exception as exc:facts['failures'].append({'phase':'label-discovery','kind':kind,'selector':selector,'error':repr(exc)})
            for name in sorted(discovered):attempt(kind,name)
        # Keep independent full PID namespace/descendant checks after removing exact objects.
        for execution_id,namespace in sorted(self.namespaces.items()):
            if execution_id not in execution_ids:continue
            try:
                observed=self.process_facts(0,namespace,0);facts['namespaces'][execution_id]=observed
                require(not observed['namespace_pids'],'original namespace descendants remain after cleanup')
            except Exception as exc:facts['failures'].append({'phase':'namespace','execution_id':execution_id,'error':repr(exc)})
        return facts
