"""Fixed five M02 families x three repeats. Preparation does not execute facilities."""
import argparse,asyncio,ast,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from validation.runtime_security.fixtures import FAMILIES,prepare,save,sha

def inputs():
    folders=('lore_control','lore_events','lore_execution','lore_files','lore_provider','lore_session','lore_runtime','harnesses')
    paths={p for folder in folders for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.mts')}
    paths.update((ROOT/'validation/system').glob('*.py'))
    paths.update((ROOT/'validation/runtime_security').glob('*.py'))
    paths.update(ROOT/p for p in ('validation/runtime_security/cases.json','validation/runtime_security/README.md',
        'design/g3/system/cases.json','design/g3/system/contract.md','design/g3/system/entry-contract.md',
        'validation/components/e/support.py','validation/session_service/live.py'))
    deps=ROOT/'validation/session-plan-evidence/context-independent-001/workspace/original-host'
    paths.update(deps/name for name in ('profile.json','request-template.json','dependencies-manifest.json'))
    paths.update(p for lib in (ROOT/'research/.venvs/runtime-research/lib').glob('python*/site-packages/nats') for p in lib.rglob('*.py'))
    return sorted(paths)

def capture(out):
    rows=[];(out/'source-before').mkdir()
    for i,path in enumerate(inputs()):
        data=path.read_bytes();copy=out/'source-before'/str(i);copy.write_bytes(data)
        rows.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),copy=str(copy)))
    save(out/'source-before.json',dict(files=rows,actual_execution='shared working-tree imports, not execution from copies',pid=os.getpid(),interpreter=sys.executable))
    return rows

async def execute(samples):
    from validation.runtime_security.exercise import one
    rows=[];failed=False
    for sample in samples:
        if failed:rows.append(dict(id=sample['id'],status='NOT_RUN',reason='first real failure retained'));continue
        row=await one(sample);rows.append(row);failed=row['status']!='PASS'
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--execute',action='store_true')
    a=ap.parse_args()
    if not a.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.batch):ap.error('bounded simple batch ID required')
    out=ROOT/'validation/runtime_security/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
    sources=capture(out);spec=json.loads((ROOT/'validation/runtime_security/cases.json').read_bytes())
    original=json.loads((ROOT/'design/g3/system/cases.json').read_bytes())
    source_case=next(c for c in original['cases'] if c['id']=='M02');save(out/'original-M02.json',source_case)
    assert spec['repeat_per_high_risk_boundary']==3 and [x['family'] for x in spec['families']]==list(FAMILIES)
    for path in (ROOT/'validation/runtime_security').glob('*.py'):ast.parse(path.read_text(),filename=str(path))
    samples=[prepare(out,family,repeat) for family in FAMILIES for repeat in (1,2,3)];save(out/'prepared-samples.json',samples)
    if not a.execute:
        result=dict(status='MISSING_EXECUTION_ADMISSION',tests_run=0,Engine=0,HTTP=0,NATS=0,credential_reads=0,
            prepared_cases=len(samples),note='Fixtures and runnable actions prepared only. No candidate or permission PASS claimed.',samples=[dict(id=s['id'],status='NOT_RUN') for s in samples])
    else:
        result=dict(status='FAIL',samples=asyncio.run(execute(samples)))
        result['tests_run']=sum(s['status']!='NOT_RUN' for s in result['samples'])
        if result['tests_run']==15 and all(s['status']=='PASS' for s in result['samples']):result['status']='PASS'
    recorded={row['path']:row for row in sources}
    changed=[p for p,row in recorded.items() if not Path(p).is_file() or sha(p)!=row['sha256']]
    changed.extend(str(p) for p in inputs() if str(p) not in recorded)
    result['source_changed']=sorted(set(changed))
    if changed:result['status']='FAIL_SOURCE_CHANGED'
    save(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='samples'}))
    return 0 if result['status']=='PASS' else 2 if result['status']=='MISSING_EXECUTION_ADMISSION' else 1
if __name__=='__main__':raise SystemExit(main())
