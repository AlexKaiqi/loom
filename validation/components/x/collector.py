"""External Docker/OS collector for pre-registered X cases; never runs a Shell fallback."""
from pathlib import Path
import base64,hashlib,http.client,io,json,os,selectors,socket,subprocess,sys,time,uuid
from oracle import archive,EvidenceError
from runtime_observations import memory_limit_facts
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from lore_execution.engine import DOCKER_CLI
# Current platform facts come from the product profile (platform_revision
# 2026-09-14 rebase); design/g3/x/environment.json stays the historical G3 record.
ENV=json.loads((ROOT/'lore_execution/profile.json').read_text())
class Collector:
 def __init__(self,out,fixture):
  self.out=out;self.fx=fixture;self.commands=[];self.serial=0;self.namespace=None;self.namespaces={};self.original_binding={};self.baseline_containers=self.ids('container');self.baseline_volumes=self.ids('volume')
  profile=ROOT/'lore_execution/seccomp.json'
  if hashlib.sha256(profile.read_bytes()).hexdigest()!=ENV['seccomp_sha256']:raise EvidenceError('seccomp profile changed')
  version=json.loads(self.run([DOCKER_CLI,'version','--format','{{json .}}'])[1])
  image=json.loads(self.run([DOCKER_CLI,'image','inspect',ENV['image']])[1])[0]
  if version['Server']['Version']!=ENV['engine_version'] or image['Id']!=ENV['image_id']:raise EvidenceError('fixed Engine/image differs')
 def run(self,argv,limit=16*1024*1024,timeout=10,check=True):
  n=self.serial;self.serial+=1;p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(self.fx['root'])},close_fds=True);s=selectors.DefaultSelector();s.register(p.stdout,selectors.EVENT_READ,'stdout');s.register(p.stderr,selectors.EVENT_READ,'stderr');b={'stdout':bytearray(),'stderr':bytearray()};deadline=time.monotonic()+timeout;err=None
  try:
   while s.get_map():
    if time.monotonic()>deadline:raise EvidenceError('external command deadline')
    for k,_ in s.select(.02):
     chunk=os.read(k.fileobj.fileno(),65536)
     if not chunk:s.unregister(k.fileobj);continue
     b[k.data].extend(chunk)
     if sum(map(len,b.values()))>limit:raise EvidenceError('external raw cap')
   rc=p.wait(timeout=1)
  except Exception as e:err=str(e);p.kill();p.wait();rc=p.returncode
  finally:s.close()
  rec={'argv':argv,'exit_code':rc,'error':err}
  for k,v in b.items():name=f'raw-{n:04d}.{k}';(self.out/name).write_bytes(v);rec[k]=name;rec[k+'_sha256']=hashlib.sha256(v).hexdigest()
  self.commands.append(rec);(self.out/'commands.json').write_text(json.dumps(self.commands,indent=2)+'\n')
  if err or (check and rc):raise EvidenceError(err or f'command exit {rc}: '+bytes(b['stderr']).decode(errors='replace')[:1000])
  return rc,bytes(b['stdout']),bytes(b['stderr'])
 def ids(self,kind):
  args=[DOCKER_CLI,'ps','-aq','--no-trunc'] if kind=='container' else [DOCKER_CLI,'volume','ls','-q']
  return sorted(self.run(args)[1].decode().split())
 def inspect(self,cid):
  if not isinstance(cid,str) or len(cid)!=64 or not all(c in '0123456789abcdef' for c in cid):raise EvidenceError('non-full Engine container id')
  rc,b,_=self.run([DOCKER_CLI,'inspect',cid],check=False)
  if rc:return None
  return json.loads(b)[0]
 def exec_inspect(self,eid):
  if not isinstance(eid,str) or len(eid)!=64 or not all(c in '0123456789abcdef' for c in eid):raise EvidenceError('non-full Engine exec id')
  endpoint=json.loads(self.run([DOCKER_CLI,'context','inspect'])[1])[0]['Endpoints']['docker']['Host']
  if not endpoint.startswith('unix://'):raise EvidenceError('fixed Linux Unix Engine endpoint required')
  class Unix(http.client.HTTPConnection):
   def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(endpoint[7:])
  h=Unix('localhost',timeout=5);h.request('GET','/v1.48/exec/'+eid+'/json');z=h.getresponse();by=z.read(1048577);h.close()
  n=self.serial;self.serial+=1;(self.out/f'raw-{n:04d}.exec-inspect').write_bytes(by)
  if len(by)>1048576:raise EvidenceError('Engine response cap')
  return json.loads(by) if z.status==200 else None
 def options(self,network='none'):
  return ['--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--security-opt','seccomp='+str(ROOT/'lore_execution/seccomp.json'),'--network',network,'--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','.5','--shm-size','1m','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64','--log-driver','none']
 def helper(self,args,limit=16*1024*1024):
  # Raw create+inspect+start+inspect+remove binds the actual helper lifetime/identity.
  owned=[x for x in self.ids('container') if x not in self.baseline_containers]
  if len(owned)>=2:raise EvidenceError('no reserved observer/helper slot; physical batch would exceed two containers')
  memory=sum(self.inspect(x)['HostConfig']['Memory'] for x in owned)
  # Cap scales with the case's declared task budget (2x); equals the
  # historical v1 hardcode (2*134217728) — amendment-linux-browser-2026-09-15.
  if memory+134217728>2*self.fx['request']['budgets']['memory_bytes']:raise EvidenceError('observer/helper combined memory reservation unavailable')
  cid=self.run([DOCKER_CLI,'create',*self.options(),*args])[1].decode().strip()
  try:
   before=self.inspect(cid);rc,by,err=self.run([DOCKER_CLI,'start','-a',cid],limit=limit,check=False);after=self.inspect(cid)
   if rc:raise EvidenceError('observer helper exit '+str(rc)+': '+err.decode(errors='replace')[:500])
   return by,{'before':before,'after':after}
  finally:self.run([DOCKER_CLI,'rm','-f',cid],check=False)
 def process_facts(self,pid,namespace,execpid):
  code=r"""import os,json,pathlib
P=pathlib.Path;pid=PID;epid=EPID;ns=NAMESPACE
if ns is None:
 try:ns=os.readlink('/proc/'+str(pid)+'/ns/pid')
 except OSError:pass
found=[];status={};cg={}
for p in P('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  if os.readlink(p/'ns/pid')==ns:found.append(int(p.name))
 except OSError:pass
try:status=dict(line.split(':',1) for line in P('/proc/'+str(epid)+'/status').read_text().splitlines() if ':' in line)
except OSError:pass
try:
 for line in P('/proc/'+str(pid)+'/cgroup').read_text().splitlines():
  _,controllers,rel=line.split(':',2)
  for c in controllers.split(',') if controllers else ['']:
   base=P('/proc')/str(pid)/'root/sys/fs/cgroup'/c
   for name in ['memory.failcnt','memory.limit_in_bytes','memory.oom_control','memory.events','pids.current','pids.max','pids.events','cpu.stat','cpu.cfs_quota_us','cpu.cfs_period_us','cpu.max']:
    f=base/name
    if f.exists():cg[c+'/'+name]=f.read_text()
except OSError:pass
print(json.dumps({'namespace':ns,'namespace_pids':sorted(found),'task_status':status,'cgroup':cg}))
""".replace('NAMESPACE',repr(namespace)).replace('EPID',str(execpid or 0)).replace('PID',str(pid or 0))
  by,root_helper=self.helper(['--user','0:0','--pid','host',ENV['image'],'python','-c',code],limit=1048576)
  facts=json.loads(by)
  # Two fixed UIDs are observed separately without CAP_SYS_PTRACE.
  # Root reads keeper namespace; UID1000 can inspect task descendants.
  task_code=code.replace('ns='+repr(namespace),'ns='+repr(facts['namespace']))
  by,task_helper=self.helper(['--user','1000:1000','--pid','host',ENV['image'],'python','-c',task_code],limit=1048576)
  task=json.loads(by);facts['namespace_pids']=sorted(set(facts['namespace_pids']+task['namespace_pids']));facts['task_status']=task['task_status'] or facts['task_status'];facts['observer_helpers']=[root_helper,task_helper];return facts
 def volume_bytes(self,volume):
  # Name and immutable Source/Driver are cross-checked against actual task mount.
  code="import os,json,stat;from pathlib import Path;s=os.statvfs('/work');entries={}\nfor p in Path('/work').iterdir():\n t=p.lstat();entries[p.name]={'size':t.st_size,'mode':t.st_mode,'inode':t.st_ino,'kind':'fifo' if stat.S_ISFIFO(t.st_mode) else ('socket' if stat.S_ISSOCK(t.st_mode) else ('regular' if stat.S_ISREG(t.st_mode) else 'other'))}\nprint(json.dumps({'bytes_total':s.f_frsize*s.f_blocks,'bytes_free':s.f_frsize*s.f_bavail,'inodes_total':s.f_files,'inodes_free':s.f_favail,'entries':entries}))"
  by,h=self.helper(['--user','1000:1000','--mount','type=volume,src='+volume+',dst=/work,readonly,volume-nocopy',ENV['image'],'python','-c',code],limit=1048576)
  return json.loads(by)
 def export(self,volume):
  args=['--user','0:0','--cap-add','DAC_OVERRIDE','--mount','type=volume,src='+volume+',dst=/work,readonly,volume-nocopy',ENV['image'],'tar','--format=pax','--acls','--xattrs','--numeric-owner','--pax-option=delete=atime,delete=ctime','-cpf','-','-C','/work','.']
  by,h=self.helper(args);name=f'raw-{self.serial:04d}.independent.tar';self.serial+=1;(self.out/name).write_bytes(by)
  return archive(by,self.fx['canary']),h
 def blobs(self,api):
  found={};total=0
  for stream in ['stdout','stderr']:
   ref=api.get('artifacts',{}).get(stream)
   if ref is None:continue
   p=Path(ref['path']);resolved=p.resolve(strict=True);root=self.fx['state'].resolve()
   if not resolved.is_relative_to(root) or p.is_symlink():raise EvidenceError('result blob escapes trusted test state')
   by=resolved.read_bytes()
   if len(by)>98304:raise EvidenceError('result blob cap')
   total+=len(by);digest=hashlib.sha256(by).hexdigest()
   if digest!=ref['sha256'] or len(by)!=ref['size']:raise EvidenceError('result reference mismatch')
   dest=self.out/(stream+'-'+digest+'.blob');dest.write_bytes(by);found[stream]={'sha256':digest,'size':len(by),'path':dest.name}
  found['total_bytes']=total;return found
 def capture(self,api,binding,tag,sample_seconds=0):
  physical={}
  peer=self.fx.get('control_peer')
  if peer is not None:
   try:self.fx['leak_bytes']=self.fx.get('leak_bytes',b'')+peer.recv(4096)
   except (BlockingIOError,OSError):pass
  frames={'api':api,'physical':physical,'host':{'control_socket_received':self.fx.get('leak_bytes',b'').decode(errors='replace'),'canaries_unchanged':all(p.exists() and p.read_bytes()==v for k,v in self.fx['host_initial'].items() for p in [Path(k)]),'human_edit_preserved':(self.fx['target']/'human-edit').exists() if self.fx['human_edit'] else False}}
  current=self.ids('container');physical['owned_containers']=[x for x in current if x not in self.baseline_containers];physical['owned_volumes']=[x for x in self.ids('volume') if x not in self.baseline_volumes]
  cid=binding.get('container_id');st=self.inspect(cid) if cid else None
  if not st:
   physical['container_running']=False
   if cid in self.namespaces:physical.update(self.process_facts(0,self.namespaces[cid],0))
   elif not cid:physical['namespace_pids']=[]
  else:
   
   if cid in self.baseline_containers or st['Config'].get('Labels',{}).get('lore.x.execution_id')!=self.fx['request']['execution_id']:raise EvidenceError('foreign container identity')
   ex=self.exec_inspect(binding['exec_id']) if binding.get('exec_id') else None;
   if ex:
    cfg=ex['ProcessConfig'];actual=[cfg['entrypoint'],*cfg['arguments']];wanted=[*self.fx['request']['interpreter_argv'],base64.b64decode(self.fx['request']['script_base64']).decode()]
    if actual!=wanted:raise EvidenceError('actual Engine exec script differs from bound request')
   state=st['State'];hc=st['HostConfig'];physical.update({'container':st,'container_running':state['Running'],'paused':state['Paused'],'log_driver':hc['LogConfig']['Type'],'network_mode':hc['NetworkMode'],'host_rw_mounts':[m for m in st['Mounts'] if m.get('Type')=='bind' and m.get('RW')],'exec':ex,'exec_running':None if ex is None else ex['Running']})
   process=self.process_facts(state.get('Pid'),self.namespaces.get(cid),ex.get('Pid') if ex else 0);self.namespace=process['namespace'];self.namespaces[cid]=process['namespace'];physical.update(process)
   if process['task_status']:
    physical['task_uid']=int(process['task_status']['Uid'].split()[0]);physical['cap_eff']=int(process['task_status']['CapEff'].strip(),16)
   mounts=[m for m in st['Mounts'] if m['Destination']=='/work']
   if len(mounts)!=1:raise EvidenceError('unique actual /work volume missing')
   m=mounts[0]
   if m['Type']!='volume' or m['Name']!=binding.get('volume_id'):raise EvidenceError('actual private volume binding mismatch')
   vol=json.loads(self.run([DOCKER_CLI,'volume','inspect',m['Name']])[1])[0]
   if vol['Driver']!='local' or vol['Mountpoint']!=m['Source']:raise EvidenceError('volume source differs')
   physical['volume']=vol
   if state['Running']:
    physical['volume_stat']=self.volume_bytes(m['Name']);v=physical['volume_stat'];physical['quota_exhausted']=v['inodes_free']==0 if self.fx['params'].get('quota_mode')=='inodes' else v['bytes_free']==0
   if state['Paused']:
    entries=physical.get('volume_stat',{}).get('entries',{});kind=self.fx['params'].get('unsupported');physical['invalid_output_observed']=any((e['size']>12582912 if kind=='sparse' else e['kind']==kind) for e in entries.values()) if kind else False
    try:frames['archive'],physical['exporter']=self.export(m['Name'])
    except Exception as e:frames['archive_error']=repr(e)
   if sample_seconds:
    samples=[process['cgroup']];end=time.monotonic()+sample_seconds
    while time.monotonic()<end:
     p=self.process_facts(state.get('Pid'),self.namespace,ex.get('Pid') if ex else 0);samples.append(p['cgroup'])
    physical['resource_samples']=samples
    kind=self.fx['params'].get('resource');effects=[]
    for row in samples:
     if kind=='memory':continue
     elif kind=='pids':effects.extend(int(v.strip())>=32 for k,v in row.items() if k.endswith('pids.current'))
     elif kind=='cpu':
      for k,v in row.items():
       if k.endswith('cpu.stat'):
        kv=dict(x.split() for x in v.splitlines());effects.append(int(kv.get('nr_throttled','0'))>0)
     elif kind=='timeout':effects.append(bool(process['namespace_pids']))
    if kind=='memory':
     physical['memory_limit_facts']=memory_limit_facts(samples);effects.append(physical['memory_limit_facts']['observed'])
    physical['resource_effect_observed']=any(effects)
  frames['blobs']=self.blobs(api);(self.out/(tag+'.json')).write_text(json.dumps(frames,ensure_ascii=False,indent=2)+'\n');return frames
