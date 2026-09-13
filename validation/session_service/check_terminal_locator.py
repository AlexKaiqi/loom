"""Check preallocated terminal identities against actual confirmed owner files."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from lore_session.snapshots import SnapshotStore
from lore_session.snapshot_files import canonical,read_ref

def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rows=[]
    for case in ['accept','drive','query_saved','export_read']:
        observed=json.loads((a.evidence/case/'observed.json').read_text());result=observed['result'];envelope=result['original_session_snapshot_ref']
        owner=json.loads(read_ref(envelope['owner_record_ref'])[1]);full=owner['source']['original_checkpoint_full_ref'];eid=full['execution_id']
        expected='s-'+hashlib.sha256(canonical([eid,'s-service-final'])).hexdigest()
        actual=owner['confirmation_request_id'];calls=[];store=SnapshotStore(Path(envelope['owner_record_ref']['path']).parent.parent,owner['scope']['namespace'],lambda *v:calls.append(v),global_budget_bytes=67108864)
        try:found=store.query(expected);passed=actual==expected and found['owner_record_ref']==envelope['owner_record_ref'] and not calls
        except Exception as e:passed=False
        rows.append(dict(case=case,actual=actual,expected=expected,passed=passed,original_execution_id=eid))
    result=dict(status='PASS' if all(r['passed'] for r in rows) else 'FAIL',scope='four real SnapshotStore owners from explicit NoEngine service fixtures; original bytes/shape unchanged',checks=rows)
    assert not a.output.exists();a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(rows)}));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
