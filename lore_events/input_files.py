"""Exactly four original input files; manifest is not a second progress ledger."""
import os,shutil,uuid
from pathlib import Path
from .values import encode,decode,sha,same,fail,EventError
from .persistence import read_file,save_once,sync_directory

NAMES={'events.jsonl','invocation.json','execution-targets.json','manifest.json'}
def packet(id,binding,span,records,event_refs):
    invocation={'schema_version':1,'invocation_id':id,'namespace':binding['namespace'],'source':binding['source'],'range':span,'filters':binding['filters'],'page_size':binding['page_size'],'surface_ref':binding['surface_ref'],'previous_session_ref':binding['previous_session_ref']}
    targets={'schema_version':1,'targets':binding['execution_targets']}
    files={'events.jsonl':b''.join(msg.data+b'\n' for msg,obj in records),'invocation.json':encode(invocation)+b'\n','execution-targets.json':encode(targets)+b'\n'}
    manifest={'schema_version':1,'complete':True,'invocation_id':id,'namespace':binding['namespace'],'source':binding['source'],'range':span,'filters':binding['filters'],'event_refs':event_refs,'files':{name:{'bytes':len(raw),'sha256':sha(raw)} for name,raw in files.items()}}
    return {**files,'manifest.json':encode(manifest)+b'\n'}

def publish(root,id,files):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink():fail('input_invalid','input publication parent cannot be symlink')
    final=root/sha(id.encode());temporary=root/('.preparing-'+uuid.uuid4().hex);temporary.mkdir(mode=0o700)
    try:
        for name,raw in files.items():save_once(temporary/name,raw)
        sync_directory(temporary)
        if final.exists():
            if final.is_symlink() or set(p.name for p in final.iterdir())!=NAMES or any(read_file(final/n)!=raw for n,raw in files.items()):
                fail('input_invalid','existing input publication differs; no implicit repair')
        else:os.rename(temporary,final)
        sync_directory(final);sync_directory(root)
    finally:
        if temporary.exists():shutil.rmtree(temporary);sync_directory(root)
    st=final.stat()
    return {'owner':'E','kind':'input','id':id,'path':str(final),'root':{'dev':st.st_dev,'ino':st.st_ino},'manifest_sha256':sha(files['manifest.json'])}

def validate(ref,binding,configured_root):
    try:
        path=Path(ref['path']);base=Path(configured_root).resolve()
        if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(base):fail('input_invalid','original input path not in owned root')
        st=path.stat()
        if ref['root']!={'dev':st.st_dev,'ino':st.st_ino} or set(p.name for p in path.iterdir())!=NAMES:fail('input_invalid','original input directory identity or collection changed')
        files={name:read_file(path/name) for name in NAMES};raw=files['manifest.json'];meta=decode(raw);inv=decode(files['invocation.json']);targets=decode(files['execution-targets.json'])
        if sha(raw)!=ref['manifest_sha256'] or meta.get('complete') is not True or meta.get('schema_version')!=1:fail('input_invalid','original manifest changed or incomplete')
        if set(meta.get('files',{}))!=NAMES-{'manifest.json'}:fail('input_invalid','manifest file collection differs')
        if any(meta['files'][name]!={'bytes':len(files[name]),'sha256':sha(files[name])} for name in meta['files']):fail('input_invalid','original file length or digest mismatch')
        restored={'namespace':inv['namespace'],'source':inv['source'],'start_sequence':inv['range']['start_sequence'],'filters':inv['filters'],'page_size':inv['page_size'],'surface_ref':inv['surface_ref'],'previous_session_ref':inv['previous_session_ref'],'execution_targets':targets['targets']}
        if not same(restored,binding) or ref['id']!=inv['invocation_id'] or ref['id']!=meta['invocation_id']:fail('input_invalid','original selector or invocation changed')
        if meta['namespace']!=binding['namespace'] or meta['source']!=binding['source'] or meta['range']!=inv['range'] or meta['filters']!=binding['filters']:fail('input_invalid','manifest and invocation associations differ')
        for name in ['manifest.json','invocation.json','execution-targets.json']:
            if encode(decode(files[name]))+b'\n'!=files[name]:fail('input_invalid','original metadata encoding differs')
        if targets.get('schema_version')!=1 or inv.get('schema_version')!=1:fail('input_invalid','unsupported input metadata version')
        return files,meta
    except (OSError,ValueError,TypeError,KeyError) as exc:
        if isinstance(exc,EventError) and exc.code=='input_invalid':raise
        fail('input_invalid','original input unavailable or invalid: '+str(exc))
