"""M05 comparisons over existing independent readers; no new observer."""
import base64,json
from pathlib import Path
from validation.runtime_recovery.facts import snapshot as owner_snapshot
from validation.runtime_security.observations import files,EngineRead
from validation.runtime_security.fixtures import save
from validation.system.runtime_observer_sources import refraw,tar_files,raw_value,digest
from validation.components.s.oracle import pi_jsonl

SUMMARY_PREFIX=b'Earlier conversation archived by the fixed Harness threshold policy ('
def compaction_facts(data):
    rows=[]
    for line in data.split(b"\n"):
        if SUMMARY_PREFIX in line:
            try:
                tx=json.loads(line)
            except Exception:
                continue
            for row in (tx if isinstance(tx,list) else [tx]):
                blob=json.dumps(row,ensure_ascii=False)
                if 'fixed Harness threshold policy' in blob:
                    rows.append(row)
    return rows

def session_bytes(config,bundle,locator,out):
    """The journal lives inside the S container (/work); its durable export is the
    confirmation archive. Read the archive member, then verify the delivered
    locator (session_sha256/session_bytes) as an exact append-only prefix."""
    import hashlib
    root=config['runtime']['session_dir'];full=bundle['snapshot_ref']
    raw=refraw(dict(path=full['archive_path'],sha256=full['archive_sha256'],bytes=full['archive_bytes']),root,18874368)
    members,_=tar_files(raw)
    out=Path(out);out.mkdir()
    for name,member in members.items():
        if name.endswith('.jsonl'):
            (out/'session.jsonl').write_bytes(member)
            if len(member)<locator['session_bytes'] or hashlib.sha256(member[:locator['session_bytes']]).hexdigest()!=locator['session_sha256']:
                raise AssertionError('original transcript prefix lost or altered')
            return member,locator
    raise AssertionError('no session JSONL member in confirmation archive')

def snapshot(config,sample,http,out):
    out=Path(out);value=owner_snapshot(config,sample,http,out)
    value['state']['E_input_files']=files(Path(config['runtime']['event_profile']['input_root']))
    objects=json.loads((out/'original-X-objects.json').read_bytes());engine=EngineRead(config['runtime']['engine_endpoint'])
    for row in objects:
        b=row['record']['binding'];row['volume']=engine.get('/volumes/'+b['volume_id'])
    save(out/'original-X-objects.json',objects);value['objects']=objects;save(out/'facts.json',value);return value

def absent(facts):return bool(facts['objects']) and all(o['record'].get('released') is True and o['container']['status']==o['volume']['status']==404 for o in facts['objects'])
def parent(facts,rid):return next(r for r in facts['state']['R']['requests'] if r['id']==rid)
