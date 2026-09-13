from pathlib import Path
import os,sys,json,subprocess,hashlib,platform,datetime
b=Path(__file__).resolve().parent;o=b/'evidence'/sys.argv[1];o.mkdir(parents=True,exist_ok=False);f=o/'fixture';f.mkdir();(f/'home').mkdir();node='/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin'
e={'PATH':str(b/'.tools/root/usr/bin')+':'+node+':/usr/bin:/bin','HOME':str(f/'home'),'LANG':'C.UTF-8','LD_LIBRARY_PATH':str(b/'.tools/root/usr/lib/x86_64-linux-gnu')}
cmd=[node+'/node',str(b/'experiment.mjs'),str(f)];r=subprocess.run(cmd,env=e,cwd=f,capture_output=True,text=True,timeout=90);(o/'stdout.jsonl').write_text(r.stdout);(o/'stderr.txt').write_text(r.stderr)
(o/'run.json').write_text(json.dumps({'command':cmd,'exit_code':r.returncode,'platform':platform.platform(),'uid':os.getuid(),'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs_sha256':{n:hashlib.sha256((b/n).read_bytes()).hexdigest() for n in ['protocol.json','experiment.mjs','worker.py','run_experiment.py']}},indent=2)+'\n');print(r.stdout);print(r.stderr);print('exit',r.returncode)
