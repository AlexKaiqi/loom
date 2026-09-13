from pathlib import Path
import subprocess,json,hashlib,os,sys,argparse,platform
p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args();r=Path(__file__).resolve().parents[2];d=r/'research/harbor';e=d/'evidence'/a.batch;e.mkdir(parents=True,exist_ok=False);(e/'home').mkdir()
env={'HOME':str(e/'home'),'PATH':str(r/'research/.venvs/harbor/bin')+':/usr/local/bin:/usr/bin:/bin','HARBOR_TELEMETRY':'0','LITELLM_LOCAL_MODEL_COST_MAP':'True','DOCKER_CONFIG':str(e/'home/.docker')}
records=[]
for mode in ['correct','wrong','missing-reward','invalid-reward']:
 cmd=[str(r/'research/.venvs/harbor/bin/harbor'),'run','--path',str(d/'fixtures'/mode),'--agent','oracle','--env','docker','--jobs-dir',str(e/'jobs'),'--job-name',mode,'--n-concurrent','1','--max-retries','0']
 try:
  q=subprocess.run(cmd,cwd=r,env=env,capture_output=True,text=True,timeout=180);out,err,code=q.stdout,q.stderr,q.returncode
 except subprocess.TimeoutExpired as x:out=(x.stdout or b'').decode() if isinstance(x.stdout,bytes) else x.stdout or '';err=str(x);code='TIMEOUT'
 (e/(mode+'.stdout')).write_text(out);(e/(mode+'.stderr')).write_text(err);records.append({'case':mode,'command':cmd,'exit_code':code});print(mode,code,flush=True)
summary={'protocol_sha256':hashlib.sha256((d/'protocol.json').read_bytes()).hexdigest(),'platform':platform.platform(),'commands':records,'scope':'Raw candidate run; independent artifact assessment saved separately'}
summary['input_sha256']={str(x.relative_to(r)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [d/'run-experiment.py',*sorted((d/'fixtures').rglob('*'))] if x.is_file()}
for name,cmd in [('docker-version',['docker','version','--format','{{json .}}']),('image',['docker','image','inspect','python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea','--format','{{.Id}} {{json .RepoDigests}}']),('dependencies',[str(r/'research/.venvs/harbor/bin/python'),'-m','importlib.metadata'])]:
 q=subprocess.run(cmd,env=env,capture_output=True,text=True);(e/(name+'.txt')).write_text(q.stdout+q.stderr)
(e/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
