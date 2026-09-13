"""Copy all finite observer-control inputs, then execute their copies. No Docker."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);a=ap.parse_args()
 if not a.batch.replace('-','').isalnum():raise ValueError('fresh batch required')
 out=Path(__file__).parent/'evidence'/a.batch;out.mkdir(exist_ok=False);ws=out/'workspace';ws.mkdir();files=set(Path(__file__).parent.glob('*.py'))|set((ROOT/'design/g3/x').glob('*.json'))|set((ROOT/'design/g4/x-validation-repair-001/prior').rglob('*'))
 evidence=json.loads((ROOT/'design/g4/x-validation-repair-001/evidence-index.json').read_text());files|={ROOT/p for p in evidence};files.add(ROOT/'design/g4/x-validation-repair-001/protocol.md');rows=[]
 for p in sorted(files):
  if not p.is_file():continue
  q=ws/p.relative_to(ROOT);q.parent.mkdir(exist_ok=True,parents=True);q.write_bytes(p.read_bytes());rows.append({'original':str(p),'copy':str(q),'sha256':sha(q)})
 rec={'scope':'X_VALIDATION_REPAIR_PREPARATION_NOT_COMPONENT_PASS','inputs':rows};(out/'before.json').write_text(json.dumps(rec,indent=2)+'\n')
 argv=[sys.executable,'-B',str(ws/'validation/components/x/runtime_repair_controls.py'),str(out/'controls')];rec['argv']=argv
 with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
  p=subprocess.run(argv,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout,stderr=stderr,timeout=30)
 rec['exit']=p.returncode;rec['source_unchanged']=all(sha(Path(x[k]))==x['sha256'] for x in rows for k in ('original','copy'));rec['status']='PASS_PREPARATION_ONLY' if p.returncode==0 and rec['source_unchanged'] else 'FAIL';rec['logs']={x.name:sha(x) for x in (out/'stdout',out/'stderr')};(out/'assessment.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps({'status':rec['status'],'exit':p.returncode,'source_unchanged':rec['source_unchanged']}));return 0 if rec['status']=='PASS_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
