"""Trusted restore test actions over actual X archives; no restoration implementation."""
from pathlib import Path
import base64,copy,hashlib,json,os,shutil
from fixtures import script_bytes
from oracle import archive,EvidenceError

def saved_json(path,value):
    with path.open('w') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def confined(path,root):
    p=Path(path)
    if not p.is_absolute() or p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):raise EvidenceError('restore fixture path outside exact authority')
    return p

def retain(fx,frames,tag,out):
    frame=frames[tag];api=frame['api'];binding=api['binding'];ref=api['artifacts']['checkpoint']
    path=confined(ref['path'],fx['state']);by=path.read_bytes()
    if len(by)>8388608 or len(by)!=ref['size'] or hashlib.sha256(by).hexdigest()!=ref['sha256']:raise EvidenceError('actual selected checkpoint blob differs')
    members=archive(by,fx['canary'])
    if members['files']!=frame['archive']['files']:raise EvidenceError('candidate checkpoint differs from actual frozen volume members')
    store=fx['root']/'retained-versions';store.mkdir();dest=store/'checkpoint.tar'
    with dest.open('wb') as f:f.write(by);f.flush();os.fsync(f.fileno())
    source={'owner':'X','source_execution_id':fx['request']['execution_id'],'source_object_generation':binding['object_generation'],'freeze_generation':binding['freeze_generation'],'source_binding':copy.deepcopy(binding),'input_manifest':copy.deepcopy(fx['request']['input_manifest']),'metadata_profile':fx['authority']['metadata_profile'],'archive_ref':{'path':str(dest),'sha256':hashlib.sha256(by).hexdigest(),'size':len(by)}}
    saved_json(store/'source-ref.json',source)
    fx.update({'restore_source':source,'original_archive_path':path,'original_request':copy.deepcopy(fx['request']),'original_authority':copy.deepcopy(fx['authority']),'original_binding':copy.deepcopy(binding)})
    frames['retained_snapshot']={'source_ref':source,'actual_archive':members,'candidate_archive_path':str(path)};saved_json(out/'retained-snapshot.json',frames['retained_snapshot'])

def clear_cache(fx):
    cache=confined(str(fx['cache'].resolve()),fx['root'])
    if cache!=fx['root']/'cache':raise EvidenceError('not exact declared cache root')
    before=sorted(str(p.relative_to(cache)) for p in cache.rglob('*'))
    for p in list(cache.iterdir()):
        if p.is_dir() and not p.is_symlink():shutil.rmtree(p)
        else:p.unlink()
    return cache,before

def cold_boundary(fx,adapter,out):
    adapter.stop();dead_pid=adapter.p.pid;dead_code=adapter.p.returncode
    cache,before=clear_cache(fx)
    (fx['target']/'untracked-dependency').unlink();(fx['target']/'input-a').write_bytes(b'changed-live-input');(fx['target']/'config.json').write_bytes(b'{"mode":"changed-live"}\n')
    facts={'cache_root':str(cache),'before_entries':before,'cache_empty':not list(cache.iterdir()),'killed_adapter_pid':dead_pid,'adapter_returncode':dead_code,'live_input_sha256':hashlib.sha256((fx['target']/'input-a').read_bytes()).hexdigest(),'live_dependency_exists':(fx['target']/'untracked-dependency').exists()}
    saved_json(out/'cold-boundary.json',facts);adapter.start();return facts

def fault_source(fx,out):
    # Preserve observation bytes outside all source/cache roots, then fault every
    # explicitly registered authoritative archive replica of this selected source.
    paths=[confined(fx['restore_source']['archive_ref']['path'],fx['root']/'retained-versions'),confined(str(fx['original_archive_path']),fx['state'])]
    records=[]
    for i,p in enumerate(dict.fromkeys(paths)):
        by=p.read_bytes();(out/('fault-preserved-source-'+str(i)+'.tar')).write_bytes(by)
        if fx['params']['restore_fault']=='missing':p.unlink()
        else:
            corrupt=bytearray(by);corrupt[0]^=1
            with p.open('wb') as f:f.write(corrupt);f.flush();os.fsync(f.fileno())
        records.append({'path':str(p),'before_sha256':hashlib.sha256(by).hexdigest(),'after_exists':p.exists(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None})
    saved_json(out/'selected-source-fault.json',records)

def prepare_request(fx):
    req=copy.deepcopy(fx['original_request']);eid=req['execution_id']+'-restored'
    req.update({'execution_id':eid,'invocation_id':'restored-read-only-invocation','step_id':'restore-read-only-step','restore_source':copy.deepcopy(fx['restore_source']),'object_generation':fx['original_binding']['object_generation']+1,'script_base64':base64.b64encode(script_bytes('restore_readonly',fx['params'])).decode()})
    fx['request']=req;fx['execution_ids'].add(eid);fx['authority']=copy.deepcopy(fx['original_authority']);fx['authority']['grants']=list(dict.fromkeys(fx['authority']['grants']+['restore']));fx['authority']['restore_source']=copy.deepcopy(fx['restore_source']);fx['authority']['object_generation']=req['object_generation']

def query_saved(fx,adapter,observer,out,tag):
    args={'request':fx['original_request'],'authority':fx['original_authority'],'binding':fx['original_binding'],'state_dir':str(fx['state']),'test_context':{'cache_dir':str(fx['cache'])}}
    api=adapter.call('query',args);return observer.capture(api,api.get('binding') or fx['original_binding'],tag)
