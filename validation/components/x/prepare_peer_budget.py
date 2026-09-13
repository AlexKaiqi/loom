"""Source-copy wrapper for the bounded peer facility calibration."""
from pathlib import Path
import json,os,subprocess,sys
from source_closure import sha,AUDIT
ROOT=Path(__file__).resolve().parents[3]
def main():
 batch=sys.argv[1]
 if not batch.replace('-','').isalnum():raise ValueError('fresh batch')
 out=ROOT/'validation/components/x/evidence'/batch;out.mkdir();ws=out/'workspace';ws.mkdir();rows=[]
 paths=[*Path(__file__).parent.glob('*.py'),*list((ROOT/'design/g3/x').glob('*.json')),ROOT/'research/docker-linux/seccomp.json',ROOT/'design/g4/x-peer-budget-repair-001/protocol.json',ROOT/'design/g4/x-peer-budget-repair-001/prior/design/g3/x/cases.json',ROOT/'design/g4/x-peer-budget-repair-001/created_boundary_control.py',ROOT/'design/g4/x-peer-budget-repair-001/created-boundary-protocol.json']
 for p in paths:
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());rows.append({'original':str(p),'copy':str(q),'sha256':sha(q)})
 audit=ws/'sitecustomize.py';audit.write_text(AUDIT);rec={'scope':'X019_FACILITY_PREPARATION_NOT_COMPONENT','inputs':rows,'audit_sha256':sha(audit)};(out/'before.json').write_text(json.dumps(rec,indent=2)+'\n');argv=[sys.executable,'-B',str(ws/'validation/components/x/peer_budget_probe.py'),str(out/'actual')]
 with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:p=subprocess.run(argv,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout,stderr=stderr,timeout=90)
 rec['guard_exit']=None
 if p.returncode==0:
  guard_argv=[sys.executable,'-B',str(ws/'design/g4/x-peer-budget-repair-001/created_boundary_control.py'),str(ws),str(out/'created-guard-controls'),str(out/'actual/network-none')];rec['guard_argv']=guard_argv
  with (out/'guard.stdout').open('wb') as stdout,(out/'guard.stderr').open('wb') as stderr:guard=subprocess.run(guard_argv,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout,stderr=stderr,timeout=10)
  rec['guard_exit']=guard.returncode
 rec.update(argv=argv,exit=p.returncode,source_unchanged=all(sha(x[k])==x['sha256'] for x in rows for k in ('original','copy')) and sha(audit)==rec['audit_sha256']);events=[json.loads(line) for q in (out/'imports').glob('*.jsonl') for line in q.read_text().splitlines()];rec['observed_execution']=events;known={str(audit):sha(audit),**{x['copy']:x['sha256'] for x in rows}};execs=[x for x in events if x['kind']=='exec'];rec['all_executed_sources_bound']=bool(execs) and all(known.get(x['filename'])==x['sha256'] for x in execs);rec['status']='PASS_PREPARATION_ONLY' if p.returncode==0 and rec['guard_exit']==0 and rec['source_unchanged'] and rec['all_executed_sources_bound'] else 'FAIL';(out/'assessment.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps({k:rec[k] for k in ['status','exit','source_unchanged','all_executed_sources_bound']}));return 0 if rec['status']=='PASS_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
