"""Prepare original M05 three repeats; --execute requires a separate root window."""
import argparse,asyncio,ast,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from validation.runtime_recovery.run import sources as prior_sources
from validation.runtime_recovery.fixtures import prepare as ordinary
from validation.runtime_security.fixtures import save,sha

def sources():
    return sorted(set(prior_sources())|set((ROOT/'validation/runtime_trim').glob('*.py'))|{ROOT/'validation/runtime_trim/cases.json',ROOT/'validation/runtime_trim/plan.md'})
def capture(out):
    rows=[];(out/'source-before').mkdir()
    for i,p in enumerate(sources()):
        q=out/'source-before'/str(i);q.write_bytes(p.read_bytes());rows.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size,copy=str(q)))
    save(out/'source-before.json',dict(actual_execution='shared source with before/after identity, not copied execution',files=rows));return rows
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--execute',action='store_true');ap.add_argument('--evidence-root',default=None);a=ap.parse_args()
    if not a.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.batch):ap.error('simple finite batch name required')
    evidence_root=Path(a.evidence_root) if a.evidence_root else ROOT/'validation/runtime_trim/evidence';out=evidence_root/a.batch;out.mkdir(parents=True,exist_ok=False);bound=capture(out)
    for p in (ROOT/'validation/runtime_trim').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
    spec=json.loads((ROOT/'validation/runtime_trim/cases.json').read_bytes());assert spec['repeats']==3 and [x['id'] for x in spec['cases']]==['M05-TRIM','M05-CORRUPT','M05-JOINT','M05-OVERFLOW']
    save(out/'original-M05.json',next(x for x in json.loads((ROOT/'design/g3/system/cases.json').read_bytes())['cases'] if x['id']=='M05'))
    samples=[dict(id=c['id'],status='NOT_RUN') for c in spec['cases']]
    from lore_runtime.startup_assets import StartupAssets
    available=callable(getattr(StartupAssets,'open_existing',None))
    if not a.execute or not available:
        result=dict(status='MISSING_EXECUTION_ADMISSION' if not a.execute else 'MISSING_STARTUP_REENTRY',tests_run=0,Engine=0,HTTP=0,NATS=0,credential_reads=0,prepared_cases=4,open_existing_available=available,samples=samples)
    else:
        from validation.runtime_trim.execute import run as run_all
        actual=asyncio.run(run_all(out,spec));result=dict(status='PASS' if actual and all(x['status']=='PASS' for x in actual) else 'FAIL',samples=actual,tests_run=sum(x['status']!='NOT_RUN' for x in actual))
    known={r['path'] for r in bound};changed=[r['path'] for r in bound if not Path(r['path']).is_file() or sha(r['path'])!=r['sha256']]+[str(p) for p in sources() if str(p) not in known]
    result['source_changed']=sorted(set(changed))
    if changed:result['status']='FAIL_SOURCE_CHANGED'
    save(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='samples'}));return 0 if result['status']=='PASS' else 2 if result['status'].startswith('MISSING') else 1
if __name__=='__main__':raise SystemExit(main())
