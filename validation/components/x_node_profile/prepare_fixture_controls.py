from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/x'))
from source_closure import AUDIT,copy_f

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);a=ap.parse_args()
 if not a.batch.replace('-','').isalnum():ap.error('fresh batch')
 out=ROOT/'validation/components/x_node_profile/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);ws=out/'workspace';rows=[]
 paths=[*Path(__file__).parent.glob('*.py'),*Path(__file__).parent.glob('*.mts'),*list((ROOT/'design/g3/x-node-profile').glob('*.json')),ROOT/'validation/components/x/source_closure.py',ROOT/'validation/components/s/probe-public.mts']
 for p in paths:
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());rows.append({'original':str(p),'copy':str(q),'sha256':sha(p)})
 f=copy_f(ws);rows+=f['implementation']+[f['gate']]
 (ws/'sitecustomize.py').write_text(AUDIT)
 known={x['copy']:x['sha256']for x in rows};known[str(ws/'f-source-equivalence.json')]=sha(ws/'f-source-equivalence.json')
 argv=[sys.executable,'-B',str(ws/'validation/components/x_node_profile/fixture_controls.py'),'--out',str(out/'actual')];env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1'}
 with (out/'stdout').open('wb')as so,(out/'stderr').open('wb')as se:p=subprocess.run(argv,cwd=ws,env=env,stdout=so,stderr=se,timeout=120)
 events=[json.loads(l)for q in (out/'imports').glob('*.jsonl')for l in q.read_text().splitlines()];executed=[e for e in events if e['kind']=='exec'];bound=bool(executed)and all(known.get(e['filename'])==e['sha256']for e in executed);unchanged=all(sha(Path(x[k]))==x['sha256']for x in rows for k in ['original','copy']);assessment=out/'actual/assessment.json'
 result={'status':'PASS_PREPARATION_ONLY'if p.returncode==0 and bound and unchanged else 'FAIL','exit_code':p.returncode,'inputs':rows,'F_source_equivalence':f,'argv':argv,'environment':env,'actual_execution':events,'copy_execution_bound':bound,'source_unchanged':unchanged,'assessment':{'path':str(assessment),'sha256':sha(assessment)}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'exit_code':p.returncode}));return 0 if result['status']=='PASS_PREPARATION_ONLY'else 1
if __name__=='__main__':raise SystemExit(main())
