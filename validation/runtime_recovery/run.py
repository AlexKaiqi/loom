"""Original M03 five cuts x three: prepare by default, never hide missing startup."""
import argparse,asyncio,ast,hashlib,inspect,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from validation.runtime_security.run import inputs as prior_inputs,capture as prior_capture
from validation.runtime_security.fixtures import save,sha
from validation.runtime_recovery.fixtures import CUTS,prepare

def sources():
    return sorted(set(prior_inputs())|set((ROOT/'validation/runtime_recovery').glob('*.py'))|{ROOT/'validation/runtime_recovery/cases.json',ROOT/'validation/runtime_recovery/README.md'})

def capture(out):
    rows=[];(out/'source-before').mkdir()
    for i,p in enumerate(sources()):
        q=out/'source-before'/str(i);q.write_bytes(p.read_bytes());rows.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size,copy=str(q)))
    save(out/'source-before.json',dict(actual_execution='shared working-tree source, not copy execution',files=rows));return rows

async def execute(samples,spec):
    from validation.runtime_recovery.execute import one
    rows=[];failed=False
    for sample in samples:
        if failed:rows.append(dict(id=sample['id'],status='NOT_RUN',reason='original first failure'));continue
        definition=next(x for x in spec['cases'] if x['cut']==sample['cut'])
        row=await one(sample,definition);rows.append(row);failed=row['status']!='PASS'
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--evidence-root',default=None);a=p.parse_args()
    if not a.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.batch):p.error('simple finite batch ID required')
    evidence_root=Path(a.evidence_root) if a.evidence_root else ROOT/'validation/runtime_recovery/evidence';out=evidence_root/a.batch;out.mkdir(parents=True,exist_ok=False)
    rows=capture(out);spec=json.loads((ROOT/'validation/runtime_recovery/cases.json').read_bytes())
    original=json.loads((ROOT/'design/g3/system/cases.json').read_bytes());save(out/'original-M03.json',next(x for x in original['cases'] if x['id']=='M03'))
    assert spec['repeats']==3 and [c['cut'] for c in spec['cases']]==list(CUTS)
    for path in (ROOT/'validation/runtime_recovery').glob('*.py'):ast.parse(path.read_text(),filename=str(path))
    samples=[prepare(out,cut,repeat) for cut in CUTS for repeat in (1,2,3)];save(out/'prepared-samples.json',samples)
    # Read-only import/introspection; no owner constructor, profile load or facilities.
    from lore_runtime.startup_assets import StartupAssets
    dependency=callable(getattr(StartupAssets,'open_existing',None))
    if not a.execute or not dependency:
        result=dict(status='MISSING_EXECUTION_ADMISSION' if not a.execute else 'MISSING_STARTUP_RESTORE',tests_run=0,Engine=0,HTTP=0,NATS=0,credential_reads=0,prepared_cases=15,open_existing_available=dependency,samples=[dict(id=s['id'],status='NOT_RUN') for s in samples])
    else:
        actual=asyncio.run(execute(samples,spec));result=dict(status='PASS' if len(actual)==15 and all(x['status']=='PASS' for x in actual) else 'FAIL',samples=actual,tests_run=sum(x['status']!='NOT_RUN' for x in actual))
    known={r['path'] for r in rows};changed=[r['path'] for r in rows if not Path(r['path']).is_file() or sha(r['path'])!=r['sha256']]
    changed += [str(p) for p in sources() if str(p) not in known];result['source_changed']=sorted(set(changed))
    if changed:result['status']='FAIL_SOURCE_CHANGED'
    save(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='samples'}))
    return 0 if result['status']=='PASS' else 2 if result['status'].startswith('MISSING') else 1
if __name__=='__main__':raise SystemExit(main())
