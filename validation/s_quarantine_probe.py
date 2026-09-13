"""Nine preregistered S quarantine file cases. Copied source; no Engine/network.
Synthetic X IDs bind trusted fixtures, never assert a real stopped execution.
"""
from pathlib import Path
import argparse, copy, hashlib, json, os, shutil, stat, subprocess, sys, time, traceback

ROOT = Path(__file__).resolve().parents[1]
IDS = ['SQ%02d' % n for n in range(1, 10)]
NS = 'quarantine-fixture'

def digest(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded(value)+b'\n'); stream.flush(); os.fsync(stream.fileno())
def inventory(root):
    result = {}
    for path in [Path(root), *sorted(Path(root).rglob('*'))]:
        st = path.lstat()
        result[str(path)] = dict(dev=st.st_dev, ino=st.st_ino, bytes=st.st_size,
            blocks=st.st_blocks*512, mode=st.st_mode, mtime_ns=st.st_mtime_ns,
            sha256=digest(path.read_bytes()) if stat.S_ISREG(st.st_mode) else None)
    return result

def copied_environment(out):
    target = out/'source'; files = []
    paths = [ROOT/'validation/s_quarantine_probe.py', ROOT/'design/g3/s/quarantine-retention.md',
             ROOT/'design/g3/x-node-profile/profile.json']
    for package in ['lore_session', 'lore_execution', 'lore_provider']:
        paths += [p for p in (ROOT/package).glob('*') if p.is_file() and p.suffix in ('.py', '.json') and '__pycache__' not in p.parts]
    paths += [ROOT/'validation/components/x_node_profile'/n for n in ['artifacts.py','snapshot_fixtures.py','fixtures.py']]
    for path in sorted(set(paths)):
        dest = target/path.relative_to(ROOT); dest.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes(); dest.write_bytes(raw)
        files.append(dict(source=str(path), copy=str(dest), sha256=digest(raw), bytes=len(raw)))
    sources = [ROOT/'validation/components/s/evidence/public-preparation-001/single-state/metadata.json',
        ROOT/'design/g4/s-author-design-preparation/sb04-public-api/evidence/public-002/BA01/work/metadata.json']
    actual = []
    for i, path in enumerate(sources):
        metadata = path.read_bytes(); jp = Path(json.loads(metadata)['path']); raw = jp.read_bytes()
        base = out/'inputs'/str(i); base.mkdir(parents=True)
        (base/'metadata.json').write_bytes(metadata); (base/'original.jsonl').write_bytes(raw)
        actual += [dict(source=str(old), copy=str(new), sha256=digest(data), bytes=len(data))
                   for old, new, data in [(path,base/'metadata.json',metadata),(jp,base/'original.jsonl',raw)]]
    before = dict(case_ids=IDS, source_files=files, actual_Pi_originals=actual,
        limits=dict(seconds=60, engine_calls=0, network_calls=0, model_calls=0, fixture_bytes=33554432),
        scope='Ordinary quarantine ownership only. No stop/pin/unlink or healthy restore assertion.')
    write(out/'before.json', before)
    return target, before

def setup_imports():
    sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'validation/components/x_node_profile'))
    # All sockets and external executables are forbidden. Only this copied query worker may spawn.
    events = []
    def audit(event, args):
        if event in ('socket.connect','socket.bind','socket.sendto'):
            events.append(event); raise RuntimeError('NoEngine probe forbids network')
        if event == 'subprocess.Popen':
            argv = args[1]
            if not (args[0] == sys.executable and isinstance(argv,list) and '--query-child' in argv and
                    str(Path(__file__).resolve()) in argv):
                events.append(event); raise RuntimeError('NoEngine probe forbids external executable')
    sys.addaudithook(audit)
    return events

def query_child(out, request_id):
    setup_imports()
    from lore_session.snapshots import SnapshotStore
    calls = []
    store = SnapshotStore(out/'owner', NS, lambda *a: calls.append(a))
    result = store.query_quarantine(request_id)
    print(json.dumps(dict(pid=os.getpid(), result=result, registry_calls=len(calls))))
    return 0

def worker(out):
    forbidden = setup_imports()
    from artifacts import canonical, file_fact, read_ref, snapshot, strict_json, InvalidEvidence
    from snapshot_fixtures import EMPTY, original, regular, scope, tar_bytes
    from fixtures import register
    from lore_session.snapshots import SnapshotStore
    from lore_session.snapshot_files import SnapshotError
    from lore_session.execution import session_reference
    from lore_execution.node_profile import NodeProfile
    from lore_execution.errors import ExecutionError
    rows, rejections, fsyncs, registry_calls = [], [], [], []
    real_fsync = os.fsync
    def traced_fsync(fd):
        st = os.fstat(fd); real_fsync(fd)
        fsyncs.append(dict(dev=st.st_dev,ino=st.st_ino,mode=st.st_mode,path=os.readlink('/proc/self/fd/'+str(fd))))
    os.fsync = traced_fsync
    authority = out/'authority'; authority.mkdir()
    def registry(*args): registry_calls.append(copy.deepcopy(args)); register(authority,*args)
    store = SnapshotStore(out/'owner',NS,registry)
    profile_path = ROOT/'design/g3/x-node-profile/profile.json'
    state = out/'x-state'; state.mkdir()
    config = dict(schema='lore-x-trusted-node-test-config/v1',state_root=str(state),transport_principal='trusted-S',
        dynamic_reference_authorities=[dict(root=str(authority),namespace=NS,
            allowed_kinds=['snapshot','storage-charge','owner-receipt'],rule='immutable-full-ref-registration/v1')],
        profiles=[dict(id=json.loads(profile_path.read_text())['id'],path=str(profile_path),sha256=digest(profile_path.read_bytes()))])
    write(out/'trusted-config.json',config)
    profile = NodeProfile(out/'trusted-config.json',digest((out/'trusted-config.json').read_bytes()),state)
    def check(value, message):
        if not value: raise AssertionError(message)
    def rejected(fn, codes=None):
        try: fn()
        except (SnapshotError,ExecutionError) as exc:
            check(codes is None or exc.code in codes,'wrong rejection code '+exc.code)
            rejections.append(dict(code=exc.code,message=str(exc))); return
        raise AssertionError('required rejection accepted')
    def confirmed_files():
        return {str(p):digest(p.read_bytes()) for p in (out/'owner').rglob('*') if p.is_file() and p.name in ('result.json','owner.json','charge.json')}
    def unchanged_reject(fn, codes=None):
        before = confirmed_files(); rejected(fn,codes); check(before == confirmed_files(),'rejection changed confirmed facts')
    fixtures = {}
    def make(label, which=0, kind='healthy', generation=1, contents=None, declared_size=None):
        base = out/'inputs'/str(which); meta_raw = (base/'metadata.json').read_bytes(); meta=json.loads(meta_raw)
        raw=(base/'original.jsonl').read_bytes(); jp=Path(meta['path']).relative_to(meta['cwd']).as_posix()
        parsed=[]
        for line in raw.splitlines()[1:]:
            value=json.loads(line); parsed.extend(value if isinstance(value,list) else [value])
        binding=[r for r in parsed if r.get('kind')=='value' and r.get('namespace') in ('lore.prep.binding','lore.s.binding') and r.get('op')=='set'][-1]
        if kind=='invalid': raw += b'{"complete_invalid":}\n'
        elif kind=='torn': raw += b'{"torn":'
        elif kind=='unaccepted': raw = raw.splitlines(keepends=True)[0]
        files={jp:raw,'metadata.json':meta_raw} if contents is None else contents
        entries=copy.deepcopy(EMPTY)
        for name,data in files.items():
            for parent in reversed(Path(name).parents):
                if str(parent)!='.': entries[parent.as_posix()]=copy.deepcopy(EMPTY['.'])
            entries[name]=regular(data)
        execution=dict(execution_id='fixture-exec-'+str(which),object_generation=1,request_digest=digest(canonical({'source':which})),
            container_id=str(which+1)*64,exec_id=str(which+3)*64,volume_id='fixture-volume-'+str(which),freeze_generation=generation,state='PREPARED')
        expected=scope(meta['id'],execution); expected['namespace']=NS
        ref=original(out/'originals'/label,expected,entries,files)
        full=dict(owner='X',path=ref['archive_path'],sha256=ref['archive_sha256'],size=ref['archive_bytes'],
            **{k:execution[k] for k in ('execution_id','object_generation','freeze_generation','state')},
            source_binding={**{k:v for k,v in execution.items() if k!='state'},**{k:expected[k] for k in ('namespace','session_id','session_generation')}})
        if declared_size is not None: full['size']=declared_size
        descriptor=dict(binding=binding['value'],jsonl_relative_path=jp,metadata_relative_path='metadata.json',binding_namespace=binding['namespace'],binding_key=binding['key'])
        fixtures[label]=dict(expected_scope=expected,fullref=full,descriptor=descriptor,kind=kind,source=which)
        write(out/'fixture-facts'/(label+'.json'),fixtures[label])
        return expected,full,descriptor
    def record(f):
        e,x,_=f; return dict(request=dict(session_binding={k:e[k] for k in ('namespace','surface_id','session_id','session_generation')}),binding=x['source_binding'])
    healthy=make('healthy'); invalid=make('invalid',kind='invalid'); torn=make('torn',kind='torn'); unaccepted=make('unaccepted',which=1,kind='unaccepted')
    def observed(f,result,quarantine=False):
        e,x,_=f; ref=result['quarantine_ref' if quarantine else 'snapshot_ref']; actual=snapshot(ref,e)
        check(file_fact(ref['archive_path'])[1]==Path(x['path']).read_bytes(),'retained raw bytes differ')
        source=file_fact(x['path'])[0]; fact=actual['archive_fact']
        check(fact['root']!=source['root'],'archive did not obtain independent inode')
        owner=strict_json(read_ref(result['owner_record_ref'])[1]); charge=strict_json(read_ref(result['storage_charge_ref'])[1])
        check(owner['source']==dict(kind='checkpoint',original_checkpoint_full_ref=x),'owner original binding differs')
        check(owner['scope']=={k:e[k] for k in ('namespace','surface_id','session_id','session_generation')},'owner scope differs')
        check(charge['archive_fact']==fact and charge['snapshot_ref']==ref,'actual storage charge differs')
        group=Path(result['owner_record_ref']['path']).parent; physical=inventory(group)
        unique={(r['dev'],r['ino']):r for r in physical.values()}
        check(sum(r['blocks'] for r in unique.values())<=charge['reserved_bytes'] and len(unique)<=charge['reserved_inodes'],'charge does not cover physical files')
        check(charge['reserved_bytes']==((fact['bytes']+4095)//4096)*4096+2097152 and charge['reserved_inodes']==16,'original reservation changed')
        check(charge['global_budget_bytes']==20*1024**3,'original global quota changed')
        synced={(r['dev'],r['ino']) for r in fsyncs}
        paths=[ref['archive_path'],ref['manifest_path'],ref['record_path'],result['owner_record_ref']['path'],result['storage_charge_ref']['path']]
        for path in paths:
            st=Path(path).stat(); parent=Path(path).parent.stat()
            check((st.st_dev,st.st_ino) in synced and (parent.st_dev,parent.st_ino) in synced,'real file/directory fsync absent')
        if quarantine:
            check(set(result)=={'quarantine_ref','owner_record_ref','storage_charge_ref'},'quarantine is exposed as healthy result')
            check(owner.get('retention_only') is True and owner.get('session_admission')=='NOT_ADMITTED' and owner.get('original_session') is None,'quarantine owner admission differs')
        return dict(archive=fact,owner=owner,charge=charge,physical=physical)
    held={}; receipts={}; details={}
    def sq01():
        for f in (invalid,torn,unaccepted): unchanged_reject(lambda f=f:store.confirm('reject-'+f[1]['sha256'],*f))
        check(not confirmed_files(),'normal rejected source acquired confirmation')
    def sq02():
        held['healthy']=store.confirm('healthy',*healthy); details['healthy']=observed(healthy,held['healthy'])
        receipts['healthy']=store.receipt('healthy-receipt',healthy[1],held['healthy'],sealed=True)
        check(profile.verify_owner_receipt(record(healthy),healthy[1],receipts['healthy'])==receipts['healthy'],'actual NodeProfile failed healthy receipt')
    def retain(label,f,reason):
        held[label]=store.quarantine(label,f[0],f[1],reason); details[label]=observed(f,held[label],True)
        check(details[label]['owner']['quarantine_reason']==reason,'original reason changed')
        receipts[label]=store.receipt(label+'-receipt',f[1],held[label],sealed=True)
        check(profile.verify_owner_receipt(record(f),f[1],receipts[label])==receipts[label],'actual NodeProfile refused original quarantine receipt')
    def sq03(): retain('invalid',invalid,'complete-invalid JSONL')
    def sq04(): retain('unaccepted',unaccepted,'original has no accepted binding')
    def sq05():
        before=(inventory(out/'owner'),inventory(authority))
        check(store.quarantine('invalid',invalid[0],invalid[1],'complete-invalid JSONL')==held['invalid'],'exact retry differs')
        check(before==(inventory(out/'owner'),inventory(authority)),'exact retry rewrote originals')
        unchanged_reject(lambda:store.quarantine('invalid',invalid[0],invalid[1],'other'),{'conflict'})
        unchanged_reject(lambda:store.quarantine('invalid',unaccepted[0],unaccepted[1],'complete-invalid JSONL'),{'conflict'})
        e=copy.deepcopy(invalid[0]); e['original_execution']['exec_id']='9'*64
        unchanged_reject(lambda:store.quarantine('wrongscope',e,invalid[1],'bad'))
        x={**invalid[1],'sha256':'0'*64}; unchanged_reject(lambda:store.quarantine('wronghash',invalid[0],x,'bad'))
        x={**invalid[1],'path':str(out/'absent.tar')}; unchanged_reject(lambda:store.quarantine('missing',invalid[0],x,'bad'))
        for reason in ('','\u754c'*342,17): unchanged_reject(lambda reason=reason:store.quarantine('badreason',invalid[0],invalid[1],reason))
    def sq06():
        before=(inventory(out/'owner'),inventory(authority)); calls=len(registry_calls)
        check(store.query_quarantine('invalid')==held['invalid'],'query differs')
        source=Path(invalid[1]['path']); hidden=source.with_name('held-original.tar'); source.rename(hidden)
        try:
            proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--query-child',str(out),'--request-id','invalid'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
            stdout,stderr=proc.communicate(timeout=10)
            (out/'query-child.stdout').write_bytes(stdout); (out/'query-child.stderr').write_bytes(stderr)
            check(proc.returncode==0,'fresh process query failed '+stderr.decode(errors='replace'))
            body=json.loads(stdout); check(body['pid']==proc.pid and proc.pid!=os.getpid() and body['registry_calls']==0 and body['result']==held['invalid'],'fresh readonly query facts differ')
        finally: hidden.rename(source)
        check(before==(inventory(out/'owner'),inventory(authority)) and len(registry_calls)==calls,'query mutated owner/registry')
        rejected(lambda:store.query('invalid'))
        try: session_reference(held['invalid'])
        except (SnapshotError,KeyError): pass
        else: raise AssertionError('quarantine admitted as normal Session reference')
        unchanged_reject(lambda:store.confirm('invalid',*invalid),{'conflict'})
    def sq07():
        rejected(lambda:store.receipt('not-sealed',invalid[1],held['invalid'],sealed=False))
        check(store.receipt('invalid-receipt',invalid[1],held['invalid'],sealed=True)==receipts['invalid'],'receipt retry differs')
        rejected(lambda:store.receipt('invalid-receipt',unaccepted[1],held['unaccepted'],sealed=True),{'conflict'})
        rejected(lambda:profile.verify_owner_receipt(record(unaccepted),unaccepted[1],receipts['invalid']))
        newer=make('quarantine-successor',generation=2,kind='invalid')
        held['newer']=store.quarantine('newer',newer[0],newer[1],'invalid successor')
        rejected(lambda:store.receipt('healthy-to-quarantine',healthy[1],held['healthy'],newer[1],held['newer'],sealed=False))
    def sq08():
        result=held['invalid']; paths=[('owner-missing',Path(result['owner_record_ref']['path']),'missing'),('owner-bad',Path(result['owner_record_ref']['path']),'bad'),
            ('charge-bad',Path(result['storage_charge_ref']['path']),'bad'),('archive-missing',Path(result['quarantine_ref']['archive_path']),'missing'),('archive-alias',Path(result['quarantine_ref']['archive_path']),'alias')]
        for label,path,mode in paths:
            backup=out/(label+'-original'); path.rename(backup)
            try:
                if mode=='bad': path.write_bytes(b'{}\n')
                elif mode=='alias': os.link(invalid[1]['path'],path)
                rejected(lambda:store.query_quarantine('invalid'))
                rejected(lambda:profile.verify_owner_receipt(record(invalid),invalid[1],receipts['invalid']))
            finally:
                if path.exists(): path.unlink()
                backup.rename(path)
            check(store.query_quarantine('invalid')==held['invalid'],'restored original no longer verifiable')
    def sq09():
        over={**invalid[1],'size':18874369}; unchanged_reject(lambda:store.quarantine('raw-over',invalid[0],over,'oversize'))
        logical=make('logical-over',contents={'over':b'L'*(16777216+1)})
        unchanged_reject(lambda:store.quarantine('logical-over',logical[0],logical[1],'oversize'))
        members=make('members-over',contents={str(i):b'' for i in range(512)})
        unchanged_reject(lambda:store.quarantine('members-over',members[0],members[1],'too many members'))
        small=SnapshotStore(out/'bounded-owner',NS,registry,global_budget_bytes=2097152)
        rejected(lambda:small.quarantine('global-over',invalid[0],invalid[1],'quota'),{'storage_limit'})
        check(not list((out/'bounded-owner').rglob('owner.json')) and not list((out/'bounded-owner').rglob('charge.json')),'global rejection confirmed owner')
    methods=[sq01,sq02,sq03,sq04,sq05,sq06,sq07,sq08,sq09]
    api=callable(getattr(store,'quarantine',None)) and callable(getattr(store,'query_quarantine',None))
    for case,fn in zip(IDS,methods):
        row=dict(id=case,status='FAIL'); start=len(rejections)
        if case not in ('SQ01','SQ02') and not api: row.update(status='MISSING_INCREMENT',error='quarantine/query_quarantine absent')
        else:
            try: fn(); row['status']='PASS'
            except Exception as exc: row.update(error=repr(exc),traceback=traceback.format_exc())
        row['rejections']=rejections[start:]; rows.append(row); write(out/(case+'.json'),row)
    origins=[]
    for name,module in sorted(sys.modules.items()):
        if name.startswith(('lore_session','lore_execution','lore_provider')):
            path=getattr(module,'__file__',None)
            if path:
                p=Path(path).resolve(); check(p.is_relative_to(ROOT),'candidate import escaped copied source')
                origins.append(dict(module=name,path=str(p),sha256=digest(p.read_bytes())))
    write(out/'details.json',details); write(out/'fsync.json',fsyncs); write(out/'registry-calls.json',registry_calls)
    result=dict(status='PASS_FILE_INCREMENT_ONLY' if all(r['status']=='PASS' for r in rows) and not forbidden else 'FAIL',
        case_ids=IDS,tests_run=len(rows),cases=rows,missing=[r['id'] for r in rows if r['status']=='MISSING_INCREMENT'],
        pid=os.getpid(),actual_imports=origins,forbidden_calls=forbidden,scope='NoEngine file ownership; physical seal/release and healthy restore remain outside this runner')
    write(out/'result.json',result); print(json.dumps(dict(status=result['status'],tests_run=len(rows),passed=sum(r['status']=='PASS' for r in rows),missing=result['missing'])))
    return 0 if result['status']=='PASS_FILE_INCREMENT_ONLY' else 1

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--batch'); ap.add_argument('--worker'); ap.add_argument('--query-child'); ap.add_argument('--request-id'); args=ap.parse_args()
    if args.query_child:return query_child(Path(args.query_child),args.request_id)
    if args.worker:return worker(Path(args.worker))
    if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.batch): raise ValueError('fresh bounded batch required')
    out=ROOT/'validation/quarantine-evidence'/args.batch; out.mkdir(parents=True,exist_ok=False)
    source,before=copied_environment(out); start=time.monotonic()
    proc=subprocess.Popen([sys.executable,'-B',str(source/'validation/s_quarantine_probe.py'),'--worker',str(out)],cwd=source,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
    try: stdout,stderr=proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill(); stdout,stderr=proc.communicate()
    (out/'stdout').write_bytes(stdout); (out/'stderr').write_bytes(stderr)
    unchanged=all(digest(Path(r[k]).read_bytes())==r['sha256'] for r in before['source_files']+before['actual_Pi_originals'] for k in ('source','copy'))
    write(out/'wrapper.json',dict(status='PASS' if proc.returncode==0 and unchanged else 'FAIL',exit_code=proc.returncode,pid=proc.pid,
        seconds=time.monotonic()-start,original_and_copy_unchanged=unchanged,worker_reaped=proc.poll() is not None))
    print(stdout.decode(errors='replace')); print(stderr.decode(errors='replace'))
    return 0 if proc.returncode==0 and unchanged else 1

if __name__=='__main__':raise SystemExit(main())
