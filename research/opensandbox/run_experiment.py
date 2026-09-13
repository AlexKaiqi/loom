from pathlib import Path
import subprocess,os,json,sys,hashlib,platform,datetime
b=Path(__file__).resolve().parent;slug=b.name;o=b/'evidence'/sys.argv[1];o.mkdir(parents=True,exist_ok=False);f=o/'fixture';f.mkdir();home=f/'home';home.mkdir();tmp=f/'tmp';tmp.mkdir();gobin='/home/USER/.local/share/lore-tools/go1.27.1/go/bin'
e={'PATH':gobin+':/usr/bin:/bin','HOME':str(home),'TMPDIR':str(tmp),'LANG':'C.UTF-8','GOCACHE':str(b/'.go-cache'),'GOMODCACHE':str(b/'.go-mod-cache'),'GOTOOLCHAIN':'local','CGO_ENABLED':'0'}
cwd=b.parent/'repos'/slug/('components/execd' if slug=='opensandbox' else 'apps/daemon')
records=[]
def run(cmd,cwd,timeout):
 r=subprocess.run(cmd,cwd=cwd,env=e,text=True,capture_output=True,timeout=timeout);i=len(records);(o/f'{i}.stdout.txt').write_text(r.stdout);(o/f'{i}.stderr.txt').write_text(r.stderr);records.append({'command':cmd,'cwd':str(cwd),'exit_code':r.returncode});return r
try:
 binary=o/'probe';r=run([gobin+'/go','build','-o',str(binary),str(b/'experiment.go')],cwd,300)
 if r.returncode:print(r.stderr[-6000:]);raise RuntimeError('candidate build failed; evidence preserved')
 for mode in ['run','query']:
  r=run([str(binary),str(f),mode,str(b/'worker.py')],f,45);print(r.stdout);print(r.stderr)
  if r.returncode:raise RuntimeError('candidate experiment process failed')
finally:
 (o/'run.json').write_text(json.dumps({'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platform':platform.platform(),'uid':os.getuid(),'commands':records,'input_sha256':{n:hashlib.sha256((b/n).read_bytes()).hexdigest() for n in ['experiment.go','worker.py','protocol.json','run_experiment.py']}},indent=2)+'\n')
