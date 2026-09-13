"""Finite existing-Docker preparation probe only; never imported as the X product."""
from pathlib import Path
import subprocess,sys,os,time,json,hashlib,datetime,selectors,tarfile,shutil,io
ROOT=Path(__file__).resolve().parents[3]; BASE=ROOT/'design/g3/x'; V=Path(__file__).parent
batch=sys.argv[1]; assert batch.replace('-','').isalnum()
out=V/'evidence'/batch;out.mkdir(parents=True,exist_ok=False);(out/'empty-home').mkdir()
env={'PATH':'/usr/bin:/bin','HOME':str(out/'empty-home'),'LANG':'C.UTF-8'}
image='python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea';profile=ROOT/'research/docker-linux/seccomp.json'
protocol=BASE/'storage-probe-protocol.json';deadline=time.monotonic()+150
result={'id':batch,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'type':'G3_CAPABILITY_PREPARATION','inputs':{},'commands':[],'observations':{},'errors':[]};containers=[];volume=None
for p in [protocol,V/'storage_probe_worker.py',Path(__file__),profile]:
 cp=out/p.name;shutil.copy2(p,cp);result['inputs'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,timeout=10,limit=1<<20,check=True):
 if time.monotonic()>deadline:raise TimeoutError('probe total deadline')
 n=len(result['commands']); cmd=['docker',*args];rec={'argv':cmd,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};result['commands'].append(rec)
 p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env);sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ,'stdout');sel.register(p.stderr,selectors.EVENT_READ,'stderr');data={'stdout':bytearray(),'stderr':bytearray()};end=time.monotonic()+timeout
 try:
  while sel.get_map():
   if time.monotonic()>end:raise TimeoutError('command timeout')
   for key,_ in sel.select(.05):
    chunk=os.read(key.fileobj.fileno(),65536)
    if not chunk:sel.unregister(key.fileobj);continue
    data[key.data].extend(chunk)
    if len(data['stdout'])+len(data['stderr'])>limit:raise OverflowError('raw command output cap')
  rc=p.wait(timeout=1)
 except Exception:
  p.kill();p.wait(timeout=2);raise
 finally:
  sel.close()
  for k,by in data.items():q=out/f'{n:03d}.{k}';q.write_bytes(by);rec[k]=q.name
  rec['exit_code']=p.returncode;rec['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 if check and rc:raise RuntimeError(f'command {n} exited {rc}: '+data['stderr'].decode(errors='replace')[:1200])
 return rc,bytes(data['stdout']),bytes(data['stderr'])
def inspect(cid):return json.loads(run(['inspect',cid])[1])[0]
def options(log=True):
 a=['--label','lore.g3.xprobe='+batch,'--user','1000:1000','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--security-opt','seccomp='+str(profile),'--network','none','--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','0.5','--shm-size','1m','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64,mode=1777']
 return a+(['--log-driver','json-file','--log-opt','max-size=64k','--log-opt','max-file=1'] if log else ['--log-driver','none'])
def create(extra,mode,name):
 cid=run(['create','--name','lore-x-'+batch+'-'+name,*options(),*extra,image,'python','-u','-c',(V/'storage_probe_worker.py').read_text(),mode])[1].decode().strip();containers.append(cid);run(['start',cid]);return cid
def ready(cid):
 for _ in range(20):
  by=run(['logs',cid])[1]
  if by.strip():return json.loads(by.splitlines()[0])
  time.sleep(.05)
 raise TimeoutError('complete JSON readiness missing')
def execpy(cid,code):return json.loads(run(['exec',cid,'python','-c',code])[1])
def archmeta(by):
 rows=[]
 with tarfile.open(fileobj=io.BytesIO(by),mode='r:*') as t:
  for m in t:
   row={'name':m.name,'type':m.type.decode('ascii'),'size':m.size,'mode':m.mode,'uid':m.uid,'gid':m.gid,'mtime':m.mtime,'linkname':m.linkname,'pax_headers':m.pax_headers}
   if m.isfile():row['sha256']=hashlib.sha256(t.extractfile(m).read()).hexdigest()
   rows.append(row)
 return rows
statcode="import os,json;from pathlib import Path;p=Path('/work');s=os.statvfs(p);print(json.dumps({'bytes_total':s.f_blocks*s.f_frsize,'bytes_free':s.f_bavail*s.f_frsize,'inodes_total':s.f_files,'inodes_free':s.f_favail,'regular_sizes':{str(x.relative_to(p)):x.stat().st_size for x in (p/'filler').iterdir()},'mountinfo':Path('/proc/self/mountinfo').read_text()}))"
def helper(args,limit=1<<20,check=True):
 hc=run(['create',*args])[1].decode().strip();containers.append(hc);pre=inspect(hc)
 try:
  rc,by,err=run(['start','-a',hc],limit=limit,check=check);post=inspect(hc)
  return rc,by,err,{'before':pre,'after':post}
 finally:
  run(['rm','-f',hc],check=False);containers.remove(hc)
def observe_ns(ns):
 code="import pathlib,os,json;target="+repr(ns)+";found=[]\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit():continue\n try:\n  if os.readlink(p/'ns/pid')==target:found.append(int(p.name))\n except OSError:pass\nprint(json.dumps({'namespace':target,'actual_pids':found}))"
 rc,by,err,record=helper([*options(False),'--pid','host',image,'python','-c',code]);record['observed']=json.loads(by);return record
try:
 result['engine']=json.loads(run(['version','--format','{{json .}}'])[1]); result['docker_info']=json.loads(run(['info','--format','{{json .}}'])[1])
 try:
  cid=create(['--tmpfs','/work:rw,nosuid,nodev,size=4m,nr_inodes=128,uid=1000,gid=1000,mode=0700'],'seed','plain');rd=ready(cid);run(['pause',cid]);st=inspect(cid)
  rc,by,err=run(['cp',cid+':/work/.','-'],limit=8<<20,check=False);ob={'ready':rd,'paused_inspect':st,'cp_returncode':rc,'archive_bytes':len(by)}
  try:ob['archive_members']=archmeta(by)
  except Exception as e:ob['archive_error']=repr(e)
  result['observations']['private_tmpfs_cp']=ob;run(['kill',cid]);run(['rm',cid]);containers.remove(cid)
 except Exception as e:result['observations']['private_tmpfs_cp_error']=repr(e)
 finally:
  for old in list(containers):
   run(['rm','-f',old],check=False);containers.remove(old)
 # Exact named volume only, private to this batch.
 volume='lore-x-'+batch+'-private';run(['volume','create','--label','lore.g3.xprobe='+batch,'--driver','local','--opt','type=tmpfs','--opt','device=tmpfs','--opt','o=size=4m,nr_inodes=128,uid=1000,gid=1000,mode=0700,nosuid,nodev',volume]);result['volume']=json.loads(run(['volume','inspect',volume])[1])[0]
 cid=create(['--mount','type=volume,src='+volume+',dst=/work,volume-nocopy'],'quota','named');rd=ready(cid);ob={'ready':rd,'full_bytes_observer':execpy(cid,statcode)};result['observations']['named_tmpfs']=ob
 inodecode="import os,json,shutil;from pathlib import Path;p=Path('/work');shutil.rmtree(p/'filler');q=p/'inode-fill';q.mkdir();count=0;err=None\nfor i in range(300):\n try:(q/str(i)).touch();count+=1\n except OSError as e:err=e.errno;break\ns=os.statvfs(p);print(json.dumps({'created':count,'errno':err,'inodes_total':s.f_files,'inodes_free':s.f_favail,'bytes_free':s.f_bavail*s.f_frsize}));shutil.rmtree(q)"
 ob['inode_observer']=execpy(cid,inodecode)
 heart="import json;from pathlib import Path;print(json.dumps({'heartbeat':(Path('/work')/'heartbeat').read_text()}))"
 ob['heartbeat_before_pause']=execpy(cid,heart);run(['pause',cid]);ob['paused_inspect_1']=inspect(cid)
 def export(tag,trusted=True):
  extra=['--user','0:0','--cap-add','DAC_OVERRIDE'] if trusted else []
  rc,by,err,record=helper([*options(False),*extra,'--mount','type=volume,src='+volume+',dst=/work,readonly,volume-nocopy',image,'tar','--format=pax','--acls','--xattrs','--numeric-owner','--pax-option=delete=atime,delete=ctime','-cpf','-','-C','/work','.'],limit=8<<20,check=False)
  (out/(tag+'.tar')).write_bytes(by);return {'path':tag+'.tar','sha256':hashlib.sha256(by).hexdigest(),'bytes':len(by),'members':archmeta(by),'exit_code':rc,'stderr':err.decode(errors='replace'),'helper':record}
 ob['unprivileged_export']=export('unprivileged-incomplete',False);ob['export_1']=export('checkpoint-1');ob['paused_inspect_2']=inspect(cid);run(['unpause',cid]);time.sleep(.25);ob['heartbeat_after_resume']=execpy(cid,heart);run(['pause',cid]);ob['export_2']=export('checkpoint-2');ob['os_before_stop']=observe_ns(rd['namespace']);run(['kill',cid]);ob['stopped_inspect']=inspect(cid);ob['os_after_stop']=observe_ns(rd['namespace']);run(['rm',cid]);containers.remove(cid)
except Exception as e:result['errors'].append(repr(e))
finally:
 for cid in list(containers):
  try:run(['rm','-f',cid],check=False)
  except Exception as e:result['errors'].append('cleanup container '+repr(e))
 if volume:
  try:run(['volume','rm',volume],check=False)
  except Exception as e:result['errors'].append('cleanup volume '+repr(e))
 result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();result['status']='OBSERVED' if not result['errors'] else 'INVESTIGATE';(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'batch':batch,'status':result['status'],'errors':result['errors'],'observations':list(result['observations'])}))
raise SystemExit(1 if result['errors'] else 0)
