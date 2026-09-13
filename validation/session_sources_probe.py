"""Finite real R/normal S original-byte resolver checks; explicit NoEngine Facts."""
import argparse, copy, hashlib, io, json, os, shutil, subprocess, sys, tarfile, traceback
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ORIGINAL = Path('/path/to/loom/validation/session_service/evidence/real-proxy-repair-001/actual')
ACTIVE = False
FORBIDDEN = []
def audit(event, args):
    if ACTIVE and ((event == 'open' and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)) or event in ('os.remove','os.rename','os.mkdir','os.rmdir','os.truncate') or event.startswith(('socket.','subprocess.'))):
        FORBIDDEN.append(event); raise RuntimeError('readonly resolver attempted '+event)
sys.addaudithook(audit)
def digest(b): return hashlib.sha256(b).hexdigest()
def save(p,v): p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def need(v,m):
    if not v: raise AssertionError(m)
def denied(fn):
    try: fn()
    except Exception: return True
    return False

def exercise(Candidate, out):
    from lore_control import ControlStore
    from lore_control.values import encode
    from lore_runtime.session_delivery import SessionDelivery, execution_id, confirmation_id
    from lore_runtime.session_plan_files import compact
    from lore_session.snapshots import SnapshotStore
    from lore_session.snapshot_files import canonical, decode, read_ref
    from lore_session.references import resolve_original
    invocations=json.loads((ORIGINAL/'invocations.json').read_bytes())
    manifest=json.loads((ORIGINAL/'fixture/peer-state/f-port/fixture-manifest.json').read_bytes())
    callbacks=[]; facts_calls=[]; sources={}; models={}
    def bound(p): sources[str(p)]=digest(p.read_bytes()); return p.read_bytes()
    bound(ORIGINAL/'invocations.json');bound(ORIGINAL/'fixture/peer-state/f-port/fixture-manifest.json')
    store=SnapshotStore(out/'S','s-original-component-001',lambda *a:callbacks.append(a))
    scope=None
    for op,action in [('op-text','drive'),('op-tool','drive'),('op-text','accept')]:
        item=next(v for v in invocations if v['action']==action and v['request']['operation_id']==op)
        old=item['result']; request_path=Path(old['original_session_snapshot_ref']['owner_record_ref']['path']).parent/'request.json'
        request=json.loads(bound(request_path));raw=bound(Path(old['original_session_snapshot_ref']['snapshot_ref']['archive_path']))
        node=copy.deepcopy(item['request']);binding=request['original_binding']['binding'];scope=binding['session_scope']
        H=manifest['harnesses'][node['harness_ref']['id']]['full_ref'];C=manifest['capabilities'][node['capability_ref']['id']]['full_ref']
        need(compact(H)==node['harness_ref'] and compact(C)==node['capability_ref'],'actual original full/compact refs differ')
        source=out/(op+'-'+action+'-source.tar');source.write_bytes(raw)
        full=copy.deepcopy(request['checkpoint_full_ref']);full['path']=str(source)
        cid=confirmation_id(execution_id(op,action))
        bundle=store.confirm(cid,request['expected_scope'],full,request['original_binding'])
        ref=old['frame'].get('operation_result_ref')
        # Independent lexical oracle for these two fixed original Pi transactions.
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tar:
            member=next(m for m in tar if m.name.removeprefix('./')==request['original_binding']['jsonl_relative_path']);jsonl=tar.extractfile(member).read()
        tokens=[]
        for line in jsonl.splitlines():
            tx=json.loads(line)
            selected=[v for v in (tx if type(tx) is list else [tx]) if v.get('namespace')=='pi.result' and v.get('key')==op and v.get('op')=='set']
            if selected:
                marker='"namespace":"pi.result","key":'+json.dumps(op,separators=(',',':'))+',"value":'
                text=line.decode();need(len(selected)==1 and text.count(marker)==1,'fixed original token marker ambiguous');begin=text.index(marker)+len(marker);parsed,end=json.JSONDecoder().raw_decode(text,begin);need(parsed==selected[0]['value'],'fixed lexical token mismatch');tokens.append(text[begin:end].encode())
        need((len(tokens)==1 and digest(tokens[0])==ref['result_sha256']) if action=='drive' else not tokens,'independent original token hash differs')
        models[(op,action)]=dict(node=node,binding=binding,H=H,C=C,cid=cid,bundle=bundle,frame=old['frame'],source=ref,bytes=tokens[0] if tokens else None,request=request,full=full)
    all_models=models;models={op:m for (op,action),m in all_models.items() if action=='drive'}
    c=ControlStore(out/'R.sqlite',{'runtime':{'namespaces':[scope['namespace'],'other-ns'],'roles':['runtime','admin','submit']}},reference_checker=lambda ref,purpose,expected:purpose=='harness')
    class Facts:
        def read(self,facility,node):
            facts_calls.append(node['operation_id'])
            m=all_models[(node['operation_id'],node['action'])]
            need(facility==m['facility'] and node==m['node'],'fixture original full observation differs')
            need(store.query(m['cid'])==m['bundle'],'actual normal SnapshotStore differs')
            if node['action']=='drive':
                actual=resolve_original(store,m['cid'],m['source'],m['binding'])
                need(actual['boundary']=={k:v for k,v in m['frame'].items() if k not in ('type','operation_id')},'actual Pi boundary differs')
            return copy.deepcopy(dict(frame=m['frame'],binding=m['binding'],bundle=m['bundle'],confirmation_request_id=m['cid']))
    service=SimpleNamespace(plans=SimpleNamespace(host={'principal':'runtime'}),snapshots=store,tools=None)
    delivery=SessionDelivery(c,service,Facts())
    c.reference_checker=lambda ref,purpose,expected: purpose=='harness' or delivery.control_reference(ref,purpose,expected)
    surface=out/'surface';surface.mkdir();first=models['op-text'];reg=c.register('runtime','register',scope['surface_id'],scope['namespace'],'surface',str(surface),first['H'],{'runtime':['read','write']})
    initial=dict(owner='S',**scope,confirmation_request_id=None)
    def accept(id,m,source=None,previous=None,**change):
        current=c.resolve('runtime',scope['namespace'],scope['surface_id'],'read')
        if current['harness_ref']!=m['H']: current=c.rebind('runtime','rebind-'+id,scope['surface_id'],current['revision'],m['H'])
        selector=dict(namespace=scope['namespace'],source='runtime',start_sequence=1,filters={},page_size=8,surface_ref={'fixture':'F version'},previous_session_ref=previous,execution_targets=[])
        payload=dict(resource_id=scope['surface_id'],resource_revision=current['revision'],harness_ref=m['H'],capability_ref=m['C'],session_ref=initial if previous is None else previous,source_result_ref=source,input_binding=selector)
        payload.update(change)
        return c.accept('runtime',dict(id=id,namespace=scope['namespace'],kind='invocation',payload=payload))
    def locator(m): return dict(owner='S',kind='confirmation',confirmation_request_id=m['cid'],session_scope=scope)
    for op,m in models.items(): accept(op,m)
    for (op,action),m in all_models.items():
        eid=execution_id(op,action);row=c.accept('runtime',dict(id=eid,namespace=scope['namespace'],kind='execution',payload=dict(parent_id=op,action=action,execution_id=eid,node_request=m['node'])))
        m['facility']=dict(owner='X',kind='session_execution',execution_id=eid,confirmation_request_id=m['cid'],node_request_digest=digest(canonical(m['node'])),session_confirmation=m['bundle'],original_stopped_response={'fixture':'NoEngine association; historical X ID not relabelled'},original_execution_response={'fixture':'NoEngine association'})
        c.mark_dispatched('runtime',eid,'X');c.confirm_delivery('runtime',eid,delivery._wrapper(row,m['facility']))
    resolver=Candidate(c,store,delivery,initial)
    readonly=[]
    def run(ref,purpose,parent,**extra):
        global ACTIVE
        before=(c.db.in_transaction,c.db.total_changes,len(callbacks));ACTIVE=True
        try:return resolver.resolve(copy.deepcopy(ref),purpose,dict(invocation=copy.deepcopy(parent),**extra))
        finally:
            ACTIVE=False;after=(c.db.in_transaction,c.db.total_changes,len(callbacks));readonly.append({'before':before,'after':after});need(before==after,'resolver mutated original R/registry')
    rows=[]
    def group(id,fn):
        try:fn();rows.append(dict(id=id,status='PASS'))
        except Exception as ex:rows.append(dict(id=id,status='FAIL',error=repr(ex),traceback=traceback.format_exc()))
    parents={op:accept('next-'+op,m,m['source'],locator(m)) for op,m in models.items()}
    def first_case():
        parent=accept('initial',first)
        need(run(initial,'session',parent)==dict(scope=scope,confirmation_request_id=None),'true initial differs')
        need(denied(lambda:run(dict(initial,session_generation=2),'session',parent)),'changed initial accepted')
        bad=accept('initial-with-source',first,first['source'])
        need(denied(lambda:run(initial,'session',bad)),'old source treated as empty initial')
        bad=accept('initial-with-previous',first,previous=locator(first),session_ref=initial)
        need(denied(lambda:run(initial,'session',bad)),'actual previous source treated as empty initial')
        changed=copy.deepcopy(parent);changed['payload']['input_binding']['previous_session_ref']=locator(first)
        need(denied(lambda:run(initial,'session',changed)),'caller supplied expected replaced R')
    group('SSRC01',first_case)
    def continuation():
        for op,m in models.items():
            expected=dict(scope=scope,confirmation_request_id=m['cid'])
            need(run(locator(m),'session',parents[op])==expected,'retained continuation differs')
            need(run(locator(m),'session',parents[op])==expected,'repeat continuation differs')
    group('SSRC02',continuation)
    def original_bytes():
        for op,m in models.items():
            actual=run(m['source'],'source-result',parents[op]);need(type(actual) is bytes and actual==m['bytes'],'original result transcribed or replaced')
            (out/(op+'-original-result.bin')).write_bytes(actual)
    group('SSRC03',original_bytes)
    def facility_source():
        for (op,action),m in all_models.items():
            row=c.query('runtime',execution_id(op,action));parent=c.query('runtime',op)
            need(run(row['receipt_ref'],'session-source',parent,facility=row,action=action)==dict(facility_id=row['id'],confirmation_request_id=m['cid']),'facility source differs')
            bad=copy.deepcopy(row['receipt_ref']);bad['namespace']='wrong'
            need(denied(lambda:run(bad,'session-source',parent,facility=row,action=action)),'swapped receipt accepted')
            need(denied(lambda:run(row['receipt_ref'],'session-source',parents[op],facility=row,action=action)),'different parent accepted')
    group('SSRC04',facility_source)
    def faults():
        m=models['op-tool'];parent=parents['op-tool'];loc=locator(m)
        for key,value in [('owner','R'),('confirmation_request_id',first['cid']),('session_scope',dict(scope,session_generation=2))]:
            need(denied(lambda key=key,value=value:run(dict(loc,**{key:value}),'session',parent)),'swapped locator '+key)
        for key,value in [('result_sha256','0'*64),('operation_id','missing-original')]:
            source=dict(m['source'],**{key:value});other=accept('wrong-'+key,m,source,loc)
            need(denied(lambda:run(loc,'session',other)),'wrong actual accepted source '+key)
        badcap=accept('wrong-capability',m,m['source'],loc,capability_ref=dict(m['C'],owner='S'))
        need(denied(lambda:run(loc,'session',badcap)),'different full capability accepted')
        badh=accept('wrong-harness',first,m['source'],loc)
        need(denied(lambda:run(loc,'session',badh)),'different full Harness accepted')
        eid=execution_id('op-tool','drive');old=c.db.execute('SELECT phase FROM requests WHERE id=?',(eid,)).fetchone()[0]
        c.db.execute("UPDATE requests SET phase='issued' WHERE id=?",(eid,))
        try:need(denied(lambda:run(loc,'session',parent)),'issued original became confirmed source')
        finally:c.db.execute('UPDATE requests SET phase=? WHERE id=?',(old,eid))
        # Actual Q original remains a retained raw archive, never a normal source.
        q=store.quarantine('Q-source',m['request']['expected_scope'],m['full'],'fixture terminal retention only')
        qref=dict(loc,confirmation_request_id='Q-source');qparent=accept('quarantined',m,m['source'],qref)
        need(denied(lambda:run(qref,'session',qparent)),'quarantine selected as normal source')
    group('SSRC05',faults)
    def readonly_case():
        with c._tx(False):
            need(run(locator(first),'session',parents['op-text'])['scope']==scope,'nested original readonly query differs')
            need(run(first['source'],'source-result',parents['op-text'])==first['bytes'],'nested original bytes differ')
        need(not FORBIDDEN and all(v['before']==v['after'] for v in readonly),'readonly side effect')
    group('SSRC06',readonly_case)
    save(out/'fixture-boundaries.json',dict(scope='Real unchanged Pi bytes / real SnapshotStore and R; new R facility and Facts are explicit NoEngine fixtures',original_sources=sources,facts_calls=facts_calls,readonly=readonly,callbacks_setup=len(callbacks),forbidden=FORBIDDEN))
    (out/'R.sql').write_text('\n'.join(c.db.iterdump()));c.close()
    return rows,sources

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--mode',choices=['bad']);p.add_argument('--actual',action='store_true');p.add_argument('--out');a=p.parse_args();assert a.batch and all(c.isalnum() or c in '-_' for c in a.batch)
    out=Path(a.out) if a.out else ROOT/'validation/session-sources-evidence'/a.batch
    if not a.actual:
        out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';workspace.mkdir()
        paths=[p for package in ['lore_control','lore_session','lore_files','lore_execution'] for p in (ROOT/package).glob('*.py')]
        paths += [ROOT/'lore_runtime'/n for n in ['__init__.py','session_delivery.py','session_plan_files.py','session_sources.py'] if (ROOT/'lore_runtime'/n).exists()]
        paths += [ROOT/'lore_execution/profile.json',Path(__file__),ROOT/'design/g3/system/session-sources.md']
        hashes={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in paths}
        for name in hashes:
            dest=workspace/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
        save(out/'sources.json',hashes)
        command=[sys.executable,'-B',str(workspace/'validation/session_sources_probe.py'),'--actual','--batch',a.batch,'--out',str(out)]
        if a.mode:command += ['--mode',a.mode]
        child=subprocess.run(command,cwd=workspace,capture_output=True,text=True);(out/'stdout').write_text(child.stdout);(out/'stderr').write_text(child.stderr)
        result=json.loads((out/'result.json').read_bytes()) if (out/'result.json').exists() else dict(status='FAIL',error='child result absent')
        intact=all(digest((ROOT/n).read_bytes())==h and digest((workspace/n).read_bytes())==h for n,h in hashes.items());result.update(source_unchanged=intact,source_count=len(hashes),exit_code=child.returncode)
        if not intact:result['status']='FAIL'
        save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 2 if result['status']=='MISSING' else 1
    product=ROOT/'lore_runtime/session_sources.py';result=dict(status='MISSING',cases=[],tests_run=0)
    if product.exists():
        try:
            from lore_runtime.session_sources import SessionSources
            Candidate=SessionSources
            if a.mode:
                class Bad(SessionSources):
                    def resolve(self,ref,purpose,expected):
                        if purpose=='source-result': return b'{}'
                        return super().resolve(ref,purpose,expected)
                Candidate=Bad
            checks,sources=exercise(Candidate,out);intact=all(digest(Path(p).read_bytes())==h for p,h in sources.items())
            result.update(cases=checks,tests_run=len(checks),original_sources_unchanged=intact,status='PASS' if len(checks)==6 and all(c['status']=='PASS' for c in checks) and intact else 'FAIL')
        except Exception as ex:result.update(status='FAIL',error=repr(ex),traceback=traceback.format_exc())
    save(out/'result.json',result);return 0 if result['status']=='PASS' else 2 if result['status']=='MISSING' else 1
if __name__=='__main__':raise SystemExit(main())
