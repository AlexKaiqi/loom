"""MISSING/control and readonly retrospective observer entry; never starts Runtime."""
import argparse,asyncio,importlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'validation/system/dependencies/markdown-001/source'))
async def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--config');p.add_argument('--sample');p.add_argument('--request-id');a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    try:mod=importlib.import_module('validation.system.runtime_observer')
    except ModuleNotFoundError as exc:
        r=dict(status='MISSING',checks=[],error=str(exc),Runtime_calls=0)
    else:
        if not a.config:
            ob=mod.Observer({},out/'observer')
            try:await ob.begin({},{});r=dict(status='FAIL',reason='missing configuration accepted')
            except mod.ObserverError as exc:r=dict(status='MISSING_REJECTED',reason=str(exc),Runtime_calls=0)
        else:
            cfg=json.loads(Path(a.config).read_text());sample=json.loads(Path(a.sample).read_text())
            ob=mod.Observer(cfg,out/'observer');r=await ob.collect_m01(sample,a.request_id)
    (out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ('observations','checks')}))
    return 0 if r['status']=='MISSING_REJECTED' else 2
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
