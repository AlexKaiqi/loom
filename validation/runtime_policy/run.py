"""Execute the actual external policy mapping, without Node/Pi drive or facilities."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
NODE=Path('/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node')
LOADER=ROOT/'research/repos/pi/node_modules/tsx/dist/loader.mjs'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--control',choices=['always-green']);a=p.parse_args()
 assert a.batch and all(c.isalnum() or c in '-_' for c in a.batch)
 out=HERE/'evidence'/a.batch;out.mkdir(parents=True)
 candidate=ROOT/'harnesses/runtime/index.mts'
 files=[HERE/'run.py',HERE/'probe.mts',HERE/'fixtures.json',ROOT/'design/g3/s/runtime-policy-contract.md',ROOT/'harnesses/minimal/index.mts',ROOT/'harnesses/minimal/projection.mts',ROOT/'lore_session/node/common.mts']
 if candidate.exists():files.append(candidate)
 before={str(p):sha(p) for p in files};fixture=json.loads((HERE/'fixtures.json').read_bytes())
 record={'status':'MISSING','tests_run':0,'source_before':before,'original_sources':fixture['original_sources']}
 assert all(sha(p)==h for p,h in fixture['original_sources'].items())
 if not candidate.exists():
  record['missing']='harnesses/runtime/index.mts';(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('MISSING 0');return 2
 argv=[str(NODE),'--import',str(LOADER),str(HERE/'probe.mts'),str(HERE/'fixtures.json'),str(out/'probe-result.json'),str(candidate),a.control or 'normal']
 (out/'command.json').write_text(json.dumps(argv,indent=2)+'\n')
 result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':str(NODE.parent)+':/usr/bin:/bin','LANG':'C.UTF-8'},timeout=30)
 (out/'stdout.txt').write_bytes(result.stdout);(out/'stderr.txt').write_bytes(result.stderr)
 if (out/'probe-result.json').exists():record.update(json.loads((out/'probe-result.json').read_bytes()))
 else:record.update(status='FAIL',error='actual candidate produced no probe result')
 after={str(p):sha(p) for p in files};record.update(exit_code=result.returncode,source_after=after,source_unchanged=before==after,original_sources_unchanged=all(sha(p)==h for p,h in fixture['original_sources'].items()))
 if result.returncode or record.get('tests_run')!=6 or not record['source_unchanged'] or not record['original_sources_unchanged']:record['status']='FAIL'
 (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:record[k] for k in ('status','tests_run')}));return 0 if record['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
