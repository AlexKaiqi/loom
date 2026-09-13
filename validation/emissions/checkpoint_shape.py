"""Read actual TS04 original R/X/F data. No Engine, NATS or synthetic publication."""
import argparse,asyncio,copy,hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from lore_runtime.emissions import EmitService

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def original():
 base=ROOT/'validation/tool-service-evidence/engine-independent-001/actual/TS04'
 with sqlite3.connect('file:'+str(base/'R.sqlite')+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row;row=dict(db.execute("SELECT * FROM requests WHERE kind='execution'").fetchone())
 payload=json.loads(row['payload_json']);plan=payload['plan'];result=json.loads((base/'original-first-response.json').read_text())
 directory=Path(plan['directory']);record=json.loads((Path(plan['authority']['state_dir'])/hashlib.sha256(row['id'].encode()).hexdigest()/'record.json').read_text());cp=record['artifacts']['checkpoint']
 archive=Path(plan['F']['bundle']['archive_path'])
 source=dict(principal=row['principal'],namespace=row['namespace'],domain=plan['request']['domain'],emit_allowed=True,execution_id=row['id'],effect_id=row['id'],binding=payload['binding'],frame=payload['frame'],base_archive_ref=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive)),output_archive_ref=cp,publication_ref=result['publication_ref'])
 return source,base
class NoSubmit:
 def __init__(self):self.calls=[]
 async def submit(self,*args):self.calls.append(args);raise AssertionError('TS04 had no ordinary outbox')
async def run(out):
 source,base=original();paths=[p for p in base.rglob('*') if p.is_file()];before={str(p):sha(p) for p in paths};events=NoSubmit()
 (out/'source.json').write_text(json.dumps(source,indent=2)+'\n');assert 'namespace' not in source['output_archive_ref']['source_binding']
 try:
  result=await EmitService(events,lambda *args:copy.deepcopy(source)).publish(source['effect_id'],source['binding'],source['publication_ref'])
  status='PASS' if result==[] and not events.calls else 'FAIL';error=None
 except Exception as exc:status='FAIL';result=None;error=dict(type=type(exc).__name__,code=getattr(exc,'code',None),message=str(exc))
 value=dict(status=status,result=result,error=error,E_calls=len(events.calls),source_original_unchanged=before=={str(p):sha(p) for p in paths},watched_files=len(paths),implementation_sha256=sha(ROOT/'lore_runtime/emissions.py'),scope='Actual TS04 original refs/data, no dispatch or new publication')
 (out/'result.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value));return 0 if status=='PASS' and value['source_original_unchanged'] else 1
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--batch',required=True);a=parser.parse_args();out=ROOT/'validation/emissions/schema1-compatibility'/a.batch;out.mkdir();raise SystemExit(asyncio.run(run(out)))
