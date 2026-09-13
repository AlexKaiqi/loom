"""Copy before execution for the preregistered external-F facility controls."""
import json,os,subprocess,sys,time
from pathlib import Path
from source_closure import copy_f,AUDIT,sha,python_children
ROOT=Path(__file__).resolve().parents[3]
def main():
 batch=sys.argv[1]
 if not batch.replace('-','').isalnum():raise ValueError('fresh batch')
 out=ROOT/'validation/components/x/evidence'/batch;out.mkdir();ws=out/'workspace';ws.mkdir();rows=[]
 for p in [*Path(__file__).parent.glob('*.py'),*list((ROOT/'design/g3/x').glob('*.json')),ROOT/'research/docker-linux/seccomp.json',ROOT/'design/g4/x-independent-preparation-001/protocol.md']:
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());rows.append({'original':str(p),'copy':str(q),'sha256':sha(q)})
 f=copy_f(ws);rows+=f['implementation']+[f['gate']];audit=ws/'sitecustomize.py';audit.write_text(AUDIT);generated={str(audit):sha(audit),str(ws/'f-source-equivalence.json'):sha(ws/'f-source-equivalence.json')}
 rec={'scope':'PREREGISTERED_X016_FIXTURE_PREPARATION_NOT_X','inputs':rows,'F_source_equivalence':f,'generated':generated};(out/'before.json').write_text(json.dumps(rec,indent=2))
 argv=[sys.executable,'-B',str(ws/'validation/components/x/handoff_probe.py'),str(out/'actual')];rec['argv']=argv
 with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
  p=subprocess.run(argv,cwd=ws,env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'},stdout=stdout,stderr=stderr,timeout=120)
 rec['exit']=p.returncode;rec['source_unchanged']=all(sha(x[k])==x['sha256'] for x in rows for k in ('original','copy')) and all(sha(p)==h for p,h in generated.items())
 events=[json.loads(line) for p in sorted((out/'imports').glob('*.jsonl')) for line in p.read_text().splitlines()];rec['observed_execution']=events;rec['python_child_closure']=python_children(events,ws);known={**generated,**{x['copy']:x['sha256'] for x in rows}};execs=[x for x in events if x['kind']=='exec'];rec['all_executed_source_bound']=bool(execs) and all(known.get(x['filename'])==x['sha256'] for x in execs);rec['F_execution_pids']=sorted({x['pid'] for x in execs if '/lore_files/' in x['filename']})
 actual=json.loads((out/'actual/assessment.json').read_text());rec['actual']={'path':str(out/'actual/assessment.json'),'sha256':sha(out/'actual/assessment.json'),'status':actual['status']};rec['status']='PASS' if p.returncode==0 and rec['source_unchanged'] and rec['all_executed_source_bound'] and rec['python_child_closure']['pass'] and len(rec['F_execution_pids'])==2 and actual['status']=='PASS' else 'FAIL';(out/'result.json').write_text(json.dumps(rec,indent=2));print(json.dumps({'status':rec['status'],'exit':rec['exit'],'actual':rec['actual']}));return 0 if rec['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
