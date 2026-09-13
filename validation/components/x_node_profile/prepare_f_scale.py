"""Freeze verified F plus independent scale worker before executing copies."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/components/x'))
from source_closure import copy_f,sha,AUDIT

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);a=ap.parse_args()
 if not a.batch.replace('-','').isalnum():raise ValueError('fresh batch')
 out=Path(__file__).parent/'evidence'/a.batch;out.mkdir(exist_ok=False);ws=out/'workspace';ws.mkdir();equivalence=copy_f(ws);rows=equivalence['implementation']+[equivalence['gate']]
 for p in [Path(__file__).parent/'f_scale_probe.py',Path(__file__).resolve(),ROOT/'validation/components/x/source_closure.py',ROOT/'design/g3/x-node-profile/f-scale-protocol.json']:
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());rows.append({'original':str(p),'copy':str(q),'sha256':sha(q)})
 audit=ws/'sitecustomize.py';audit.write_text(AUDIT);generated={str(audit):sha(audit),str(ws/'f-source-equivalence.json'):sha(ws/'f-source-equivalence.json')};rec={'scope':'REAL_F_SCALE_PREPARATION_NOT_X_OR_S','inputs':rows,'generated':generated};(out/'before.json').write_text(json.dumps(rec,indent=2)+'\n')
 argv=[sys.executable,'-B',str(ws/'validation/components/x_node_profile/f_scale_probe.py'),str(out/'actual')]
 with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
  p=subprocess.run(argv,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout,stderr=stderr,timeout=90)
 rec.update(argv=argv,exit=p.returncode,source_unchanged=all(sha(x[k])==x['sha256'] for x in rows for k in ('original','copy')) and all(sha(q)==h for q,h in generated.items()));events=[json.loads(line) for q in (out/'imports').glob('*.jsonl') for line in q.read_text().splitlines()];rec['observed_execution']=events;known={**generated,**{x['copy']:x['sha256'] for x in rows}};execs=[e for e in events if e['kind']=='exec'];rec['all_executed_sources_bound']=bool(execs) and all(known.get(e['filename'])==e['sha256'] for e in execs);rec['actual_F_executed']=all(any(e['filename']==x['copy'] for e in execs) for x in equivalence['implementation']);rec['status']='PASS_PREPARATION_ONLY' if p.returncode==0 and rec['source_unchanged'] and rec['all_executed_sources_bound'] and rec['actual_F_executed'] else 'FAIL';(out/'assessment.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps({k:rec[k] for k in ['status','exit','source_unchanged','all_executed_sources_bound','actual_F_executed']}));return 0 if rec['status']=='PASS_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
