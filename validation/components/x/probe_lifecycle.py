from pathlib import Path
import subprocess,sys,json,datetime,hashlib,shutil,time
R=Path(__file__).resolve().parents[3];V=Path(__file__).parent;out=V/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False);(out/'empty-home').mkdir();env={'PATH':'/usr/bin:/bin','HOME':str(out/'empty-home'),'LANG':'C.UTF-8'}
image='python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea';protocol=R/'design/g3/x/lifecycle-probe-protocol.json';profile=R/'research/docker-linux/seccomp.json';res={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs':{},'commands':[],'observations':{},'errors':[]};ids=[];volume='lore-x-'+sys.argv[1];start=time.monotonic()
for p in [Path(__file__),protocol,profile]:shutil.copy2(p,out/p.name);res['inputs'][str(p.relative_to(R))]=hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,ok=True):
 assert time.monotonic()-start<60
 n=len(res['commands']);p=subprocess.run(['docker',*args],env=env,capture_output=True,timeout=10);assert len(p.stdout)+len(p.stderr)<=1048576
 for name,data in [('stdout',p.stdout),('stderr',p.stderr)]: (out/f'{n:03d}.{name}').write_bytes(data)
 res['commands'].append({'argv':['docker',*args],'exit_code':p.returncode,'stdout':f'{n:03d}.stdout','stderr':f'{n:03d}.stderr'})
 if ok and p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
 return p
opt=['--label','lore.g3.xprobe='+sys.argv[1],'--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--security-opt','seccomp='+str(profile),'--network','none','--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','0.5','--shm-size','1m','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64,mode=1777','--log-driver','none']
def inspect(x):return json.loads(run(['inspect',x]).stdout)[0]
try:
 run(['volume','create','--label','lore.g3.xprobe='+sys.argv[1],'--driver','local','--opt','type=tmpfs','--opt','device=tmpfs','--opt','o=size=4m,nr_inodes=128,uid=1000,gid=1000,mode=0700,nosuid,nodev',volume]);res['volume']=json.loads(run(['volume','inspect',volume]).stdout)[0]
 keeper=run(['create',*opt,'--mount','type=volume,src='+volume+',dst=/work,volume-nocopy',image,'sleep','30']).stdout.decode().strip();ids.append(keeper);run(['start',keeper])
 code="import os,signal,json;from pathlib import Path;p=Path('/work/locked.bin');p.write_bytes(b'preserved-after-command-exit');os.chmod(p,0);error=None\ntry:os.kill(1,signal.SIGKILL)\nexcept OSError as e:error=e.errno\nprint(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'kill_keeper_errno':error,'status':Path('/proc/self/status').read_text()}))"
 res['observations']['task']=json.loads(run(['exec','--user','1000:1000',keeper,'python','-c',code]).stdout);res['observations']['after_task_exit']=inspect(keeper);run(['pause',keeper]);res['observations']['paused']=inspect(keeper)
 code="import os,sys,json;error=None\ntry:open('/work/forbidden-write','wb').write(b'not-allowed')\nexcept OSError as e:error=e.errno\nprint(json.dumps({'uid':os.getuid(),'write_errno':error}),file=sys.stderr,flush=True);os.execvp('tar',['tar','--format=pax','--numeric-owner','--pax-option=delete=atime,delete=ctime','-cpf','-','-C','/work','.'])"
 helper=run(['create',*opt,'--cap-add','DAC_OVERRIDE','--mount','type=volume,src='+volume+',dst=/work,readonly,volume-nocopy',image,'python','-c',code]).stdout.decode().strip();ids.append(helper);res['observations']['helper_before']=inspect(helper);p=run(['start','-a',helper]);(out/'after-exit.tar').write_bytes(p.stdout);res['observations']['helper_write']=json.loads(p.stderr.splitlines()[0]);res['observations']['helper_after']=inspect(helper);run(['rm',helper]);ids.remove(helper);run(['kill',keeper]);res['observations']['stopped']=inspect(keeper);run(['rm',keeper]);ids.remove(keeper)
except Exception as e:res['errors'].append(repr(e))
finally:
 for cid in ids:
  try:run(['rm','-f',cid],False)
  except Exception as e:res['errors'].append('cleanup '+repr(e))
 try:run(['volume','rm',volume],False)
 except Exception as e:res['errors'].append('cleanup volume '+repr(e))
 res['status']='OBSERVED' if not res['errors'] else 'INVESTIGATE';res['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'result.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':res['status'],'errors':res['errors']}))
raise SystemExit(bool(res['errors']))
