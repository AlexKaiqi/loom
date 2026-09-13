from pathlib import Path
import subprocess,json,hashlib,sys,argparse,platform,sqlite3
p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args();r=Path(__file__).resolve().parents[2];d=r/'research/openclaw';e=d/'evidence'/a.batch;e.mkdir(parents=True,exist_ok=False);(e/'home').mkdir()
node='/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node';env={'HOME':str(e/'home'),'OPENCLAW_HOME':str(e/'home'),'OPENCLAW_STATE_DIR':str(e/'state'),'PATH':'/usr/bin:/bin','OPENCLAW_LOG_LEVEL':'silent'}
path=e/'state/cron/jobs.json';records=[];obs={};snap=e/'snapshot.json';snap2=e/'snapshot-runtime.json'
for label,mode,ss in [('seed','seed',snap),('restart','read',snap),('capture','capture',snap),('change','change',snap),('stale','stale',snap),('post-stale','read',snap),('capture-runtime','capture',snap2),('runtime','runtime',snap2),('repair','repair',snap2),('unsafe','unsafe',snap2)]:
 cmd=[node,str(d/'experiment.mjs'),mode,str(path),str(ss)];q=subprocess.run(cmd,cwd=r,env=env,text=True,capture_output=True,timeout=30)
 (e/(label+'.stdout')).write_text(q.stdout);(e/(label+'.stderr')).write_text(q.stderr);records.append({'case':label,'command':cmd,'exit_code':q.returncode})
 if q.returncode:raise RuntimeError(label+': '+q.stderr[-2000:])
 obs[label]=json.loads(q.stdout)
 dbpath=e/'state/state/openclaw.sqlite'
 if dbpath.exists():
  con=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
  data={t:[dict(v) for v in con.execute('SELECT * FROM '+t)] for t in ['cron_jobs','cron_job_runtime_states'] if con.execute("SELECT 1 FROM sqlite_master WHERE name=?",(t,)).fetchone()};con.close();(e/(label+'-sqlite.json')).write_text(json.dumps(data,indent=2))
checks={}
try:
 checks['restart-exact']=obs['seed']['store']==obs['restart']['store'] and obs['restart']['store']['jobs'][0]['state']['queuedAtMs']==2000
 checks['stale-refused']=obs['stale'].get('error_type')=='CronJobsStoreChangedError'
 checks['stale-no-overwrite']=obs['post-stale']['store']['jobs'][0]['name']=='competing-definition'
 checks['repair-keeps-responsibility']=obs['repair']['store']['jobs'][0]['state']=={'queuedAtMs':4000,'runningAtMs':4001,'nextRunAtMs':5000} and obs['repair']['store']['jobs'][0]['enabled']==False
 checks['unsafe-control-loses-running']='runningAtMs' not in obs['unsafe']['store']['jobs'][0]['state']
 checks['sqlite-authority-not-json']=dbpath.exists() and not path.exists()
except Exception as ex:checks['observer-complete']=False;checks['observer-error']=str(ex)
summary={'protocol_sha256':hashlib.sha256((d/'protocol.json').read_bytes()).hexdigest(),'platform':platform.platform(),'commands':records,'observations':obs,'checks':checks,'all_checks':all(x is True for x in checks.values())}
summary['input_hashes']={str(x.relative_to(r)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [d/'experiment.mjs',d/'run-experiment.py',d/'build.mjs',r/'research/.cache/openclaw-build/cron-store.mjs',r/'research/.cache/openclaw-build/metafile.json']}
(e/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'checks':checks,'seed':obs['seed']},indent=2));sys.exit(0 if summary['all_checks'] else 1)
