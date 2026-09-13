from pathlib import Path
import subprocess,json,hashlib,os,sys,argparse,platform,time
p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[2];d=r/'research/codex';e=d/'evidence'/a.batch;e.mkdir(parents=True,exist_ok=False)
node='/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node';tsx=r/'research/.cache/codex-node/node_modules/tsx/dist/cli.mjs'
env={'HOME':str(e/'home'),'PATH':'/usr/bin:/bin'};(e/'home').mkdir()
records=[]
for mode in ['completed','resume','failed','malformed','nonzero','truncated','abort']:
 cmd=[node,str(tsx),str(d/'experiment.mts'),mode,str(e)]
 q=subprocess.run(cmd,cwd=r,env=env,text=True,capture_output=True,timeout=15)
 (e/(mode+'.stdout')).write_text(q.stdout);(e/(mode+'.stderr')).write_text(q.stderr)
 records.append({'case':mode,'command':cmd,'exit_code':q.returncode})
 time.sleep(.1)
checks={};obs={}
for rec in records:
 mode=rec['case'];obs[mode]=json.loads((e/(mode+'.stdout')).read_text())
 logs=[json.loads(x) for x in (e/(mode+'-child.jsonl')).read_text().splitlines()]
 checks[mode+'-process-run']=rec['exit_code']==0 and logs[0]['kind']=='started'
 checks[mode+'-minimal-env']=not any(k.endswith('API_KEY') or k.endswith('TOKEN') for k in logs[0]['env_keys'])
 if mode=='resume':checks['resume-argv']=logs[0]['argv'][-2:]==['resume','fixed-thread'] or ['resume','fixed-thread']==logs[0]['argv'][logs[0]['argv'].index('resume'):logs[0]['argv'].index('resume')+2]
 if mode=='abort':checks['abort-child-termination']=any(x['kind']=='terminated' for x in logs)
checks['normal-result']=obs['completed']['result']['finalResponse']=='fixture-answer' and obs['completed']['result']['usage']['output_tokens']==2
for mode in ['failed','malformed','nonzero','abort']:checks[mode+'-rejected']=obs[mode]['outcome']=='rejected'
checks['nonzero-code']= '17' in obs['nonzero']['error']['message']
checks['truncated-observed']=obs['truncated']['outcome'] in ['rejected','returned']
summary={'protocol_sha256':hashlib.sha256((d/'protocol.json').read_bytes()).hexdigest(),'platform':platform.platform(),'commands':records,'observations':obs,'checks':checks,'all_fixture_and_transport_checks':all(checks.values()),'completion_guard_supported':obs['truncated']['outcome']=='rejected','scope':'Actual SDK; deterministic CLI boundary fixture, not actual Rust session/LLM execution'}
summary['source_sha256']={str(x.relative_to(r)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [d/'experiment.mts',d/'fixture-cli.py',d/'run-experiment.py',*list((r/'research/repos/codex/sdk/typescript/src').glob('*.ts'))]}
(e/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
sys.exit(0 if all(checks.values()) else 1)
