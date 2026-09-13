from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/x'))
from source_closure import AUDIT

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--docker-window',action='store_true');a=ap.parse_args()
 if not a.docker_window or not a.batch.replace('-','').isalnum():ap.error('fresh batch and exclusive Docker window required')
 out=ROOT/'validation/components/x_node_profile/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);ws=out/'workspace';rows=[]
 paths=[Path(__file__),Path(__file__).with_name('mount_bounds_probe.py'),ROOT/'design/g3/x-node-profile/mount-bounds-protocol.json',ROOT/'design/g3/x-node-profile/profile.json',ROOT/'design/g3/x/environment.json',ROOT/'research/docker-linux/seccomp.json',ROOT/'validation/components/x/source_closure.py']
 for p in paths:
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());rows.append({'original':str(p),'copy':str(q),'sha256':sha(p)})
 (ws/'sitecustomize.py').write_text(AUDIT);generated={str(ws/'sitecustomize.py'):sha(ws/'sitecustomize.py')}
 argv=[sys.executable,'-B',str(ws/'validation/components/x_node_profile/mount_bounds_probe.py'),'--out',str(out/'actual'),'--docker-window'];env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1'}
 with (out/'stdout').open('wb') as so,(out/'stderr').open('wb') as se:p=subprocess.run(argv,cwd=ws,env=env,stdout=so,stderr=se,timeout=100)
 events=[json.loads(l) for f in (out/'imports').glob('*.jsonl') for l in f.read_text().splitlines()];known={**{x['copy']:x['sha256'] for x in rows},**generated};executed=[e for e in events if e['kind']=='exec'];bound=bool(executed)and all(known.get(e['filename'])==e['sha256'] for e in executed);unchanged=all(sha(Path(x[k]))==x['sha256']for x in rows for k in ['original','copy']) and all(Path(path).is_file() and sha(Path(path))==h for path,h in generated.items());assessment=out/'actual/assessment.json'
 result={'status':'PASS_PREPARATION_ONLY'if p.returncode==0 and bound and unchanged else 'FAIL','exit_code':p.returncode,'inputs':rows,'generated':generated,'argv':argv,'environment':env,'actual_execution':events,'copy_execution_bound':bound,'source_unchanged':unchanged,'assessment':{'path':str(assessment),'sha256':sha(assessment)}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'exit_code':p.returncode}));return 0 if result['status']=='PASS_PREPARATION_ONLY'else 1
if __name__=='__main__':raise SystemExit(main())
