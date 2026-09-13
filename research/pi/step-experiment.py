from pathlib import Path
import subprocess,json,sys,hashlib,datetime,shutil
B=Path(__file__).resolve().parent;ROOT=B.parents[1];out=B/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
node='/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node';tsx=ROOT/'research/repos/pi/node_modules/tsx/dist/loader.mjs'
result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs':{},'runs':[],'checks':{},'errors':[]}
for n in ['protocol-step-002.json','step-worker.mts','step-experiment.py','tsconfig.json']:
 shutil.copy2(B/n,out/n);result['inputs'][n]=hashlib.sha256((B/n).read_bytes()).hexdigest()
source=ROOT/'research/repos/pi/packages/agent/src/harness/agent-harness.ts';result['hook_source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
def run(mode,work):
 work.mkdir(exist_ok=True);env={'PATH':str(Path(node).parent)+':/usr/bin:/bin','LANG':'C.UTF-8','TSX_TSCONFIG_PATH':str(B/'tsconfig.json')};cmd=[node,'--import',str(tsx),str(B/'step-worker.mts'),mode,str(work)]
 r=subprocess.run(cmd,cwd=work,env=env,text=True,capture_output=True,timeout=30);(out/(mode+'.stdout.json')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr)
 result['runs'].append({'mode':mode,'argv':cmd,'exit_code':r.returncode})
 if r.returncode:raise RuntimeError(r.stderr)
 for f in (work/'sessions').rglob('*.jsonl'):shutil.copy2(f,out/(mode+'.session.jsonl'))
 return json.loads(r.stdout)
try:
 w=out/'state';step=run('step',w);query=run('inspect',w);cont=run('continue',w);control=run('control',out/'control-state')
 queries=[json.loads(x) for x in (w/'queries.jsonl').read_text().splitlines()]
 checks={'single_step_saved_before_next_request':step['providerCalls']==1 and step['result'] is not None and 'SAVED_EFFECT_RESULT_雪' in json.dumps(step['entries'],ensure_ascii=False),'fresh_original_query':query['providerCalls']==0 and query['firstResult']==step['firstResult'] and query['pid']!=step['pid'],'continued_original_context':cont['providerCalls']==1 and cont['oldResult']==step['firstResult'] and 'SAVED_EFFECT_RESULT_雪' in json.dumps(queries[-1]['request'],ensure_ascii=False),'one_actual_effect':(w/'effects.txt').read_text()=='effect\n','control_native_continues':control['providerCalls']==2 and (out/'control-state/effects.txt').read_text()=='effect\n' and 'CONTROL_FINAL' in json.dumps(control['entries']),'raw_saved_result_reused':(out/'inspect.session.jsonl').read_bytes()==(out/'step.session.jsonl').read_bytes(),'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==result['hook_source_sha256']}
 result['checks']=checks;result['first_result']=step['firstResult'];result['continued_result']=cont['result']
 if not all(checks.values()):raise AssertionError('step-boundary observations did not all hold')
except Exception as e:result['errors'].append(repr(e))
result['status']='OBSERVED' if not result['errors'] else 'INVESTIGATE';(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if not result['errors'] else 1)
