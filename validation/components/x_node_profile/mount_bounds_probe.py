"""Two preregistered one-object Docker facility modes. No X/Node implementation."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys, time, uuid
ROOT = Path(__file__).resolve().parents[3]
CODE = r"""import errno,json,os,pathlib
root=pathlib.Path('/dev/shm')
def fact(p):
 s=os.statvfs(p);return {'bytes':s.f_frsize*s.f_blocks,'bytes_free':s.f_frsize*s.f_bavail,'inodes':s.f_files,'inodes_free':s.f_favail}
initial={'shm':fact('/dev/shm'),'tmp':fact('/tmp'),'mountinfo':pathlib.Path('/proc/self/mountinfo').read_text(),'uid':os.getuid(),'status':pathlib.Path('/proc/self/status').read_text()}
if MODE=='explicit':
 created=[];error=None
 try:
  for i in range(66):
   p=root/('inode-'+str(i));p.touch();created.append(p)
 except OSError as e:error={'errno':e.errno,'name':errno.errorcode.get(e.errno)}
 initial['full']={'shm':fact('/dev/shm'),'created':len(created),'error':error}
 for p in created:p.unlink()
 initial['released']=fact('/dev/shm')
print(json.dumps(initial))
"""
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);parser.add_argument('--docker-window',action='store_true');a=parser.parse_args()
 if not a.docker_window: parser.error('root-exclusive Docker window required')
 out=Path(a.out);out.mkdir(parents=True,exist_ok=False);commands=[];own=[];rows=[]
 environment=json.loads((ROOT/'design/g3/x/environment.json').read_text());seccomp=ROOT/environment['seccomp']['path']
 if sha(seccomp)!=environment['seccomp']['sha256']: raise ValueError('original seccomp differs')
 def run(argv,check=True):
  p=subprocess.run(argv,capture_output=True,timeout=10,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
  if len(p.stdout)+len(p.stderr)>2097152:raise ValueError('facility raw cap')
  n=len(commands);(out/f'raw-{n:03d}.stdout').write_bytes(p.stdout);(out/f'raw-{n:03d}.stderr').write_bytes(p.stderr)
  commands.append({'argv':argv,'exit_code':p.returncode,'stdout':f'raw-{n:03d}.stdout','stderr':f'raw-{n:03d}.stderr'})
  (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
  if check and p.returncode:raise ValueError('actual facility CLI failed: '+p.stderr.decode(errors='replace'))
  return p
 baseline=run(['docker','ps','-aq','--no-trunc']).stdout.decode().split();label='xn-mount-'+uuid.uuid4().hex
 error=None
 try:
  for mode in ('default','explicit'):
   options=['--label','lore.xn.mount_probe='+label,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true',
    '--security-opt','seccomp='+str(seccomp),'--network','none','--memory','128m','--memory-swap','128m','--pids-limit','32',
    '--cpus','.25','--shm-size','1m','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=32m,nr_inodes=2048','--log-driver','none','--user','1000:1000']
   if mode=='explicit': options += ['--tmpfs','/dev/shm:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64']
   code=CODE.replace("MODE",repr(mode));(out/(mode+'-script.py')).write_text(code)
   created=run(['docker','create',*options,environment['image'],'python','-c',code]);cid=created.stdout.decode().strip();own.append(cid)
   before=json.loads(run(['docker','inspect',cid]).stdout)[0]
   p=run(['docker','start','-a',cid]);observed=json.loads(p.stdout)
   after=json.loads(run(['docker','inspect',cid]).stdout)[0]
   checks={'actual_same_object':before['Id']==after['Id']==cid,'actual_exit0':after['State']['ExitCode']==0 and not after['State']['Running'],
    'configured_budget':before['HostConfig']['Memory']==134217728 and before['HostConfig']['NanoCpus']==250000000,
    'uid1000':observed['uid']==1000,'shm1MiB':observed['shm']['bytes']==1048576,
    'tmp32MiB2048inode':observed['tmp']['bytes']==33554432 and observed['tmp']['inodes']==2048}
   if mode=='explicit':checks.update(shm64inode=observed['shm']['inodes']==64,actual_inode_ENOSPC=observed['full']['error']['errno']==28 and observed['full']['shm']['inodes_free']==0,released=observed['released']['inodes_free']==observed['shm']['inodes_free'])
   else:checks['default_not_claimed64']=observed['shm']['inodes']!=64
   for mount in ['/tmp','/dev/shm']:
    lines=[line for line in observed['mountinfo'].splitlines() if line.split()[4]==mount]
    checks['actual_flags_'+mount]=len(lines)==1 and all(flag in lines[0].split()[5].split(',') for flag in ['rw','nosuid','nodev','noexec'])
   rows.append({'mode':mode,'before':before,'after':after,'observed':observed,'checks':checks})
   run(['docker','rm',cid]);own.remove(cid)
 except Exception as exc:error=repr(exc)
 finally:
  cleanup=[]
  for cid in own:
   got=run(['docker','inspect',cid],False)
   if got.returncode==0 and (json.loads(got.stdout)[0]['Config'].get('Labels')or{}).get('lore.xn.mount_probe')==label:run(['docker','rm','-f',cid],False)
  for row in rows:
   cid=row['before']['Id'];cleanup.append({'id':cid,'inspect_exit':run(['docker','inspect',cid],False).returncode})
  remaining=run(['docker','ps','-aq','--no-trunc','--filter','label=lore.xn.mount_probe='+label]).stdout.decode().split()
  final=run(['docker','ps','-aq','--no-trunc']).stdout.decode().split()
  status='PASS_MOUNT_FACILITY_ONLY' if len(rows)==2 and all(all(x['checks'].values()) for x in rows) and not error and not remaining and sorted(final)==sorted(baseline) else 'FAIL'
  report={'status':status,'rows':rows,'error':error,'cleanup':cleanup,'remaining_owned':remaining,'original_inventory_preserved':sorted(final)==sorted(baseline),'scope':'one128MiB object per mode, actual Linux mount options only; no Node/XN component executed'}
  (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':status,'modes':len(rows),'error':error}));return 0 if status=='PASS_MOUNT_FACILITY_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
