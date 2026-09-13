"""Trusted finite PID-namespace observer; never substitutes Engine inventory for PIDs."""
from pathlib import Path
import hashlib,http.client,json,os,selectors,socket,subprocess,time
from oracle import InvalidEvidence
ROOT=Path(__file__).resolve().parents[3]
IMAGE='python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea'
PROFILE=ROOT/'research/docker-linux/seccomp.json'
PROFILE_SHA='9c1025c88ccaa517b648da571961838744ea2137f176bfe6a48b21294cae9c76'
ENV={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
def run(argv,root,limit=1048576):
 root.mkdir(parents=True,exist_ok=True);n=len(list(root.glob('*.command.json')));p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,close_fds=True);sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ,'stdout');sel.register(p.stderr,selectors.EVENT_READ,'stderr');data={'stdout':bytearray(),'stderr':bytearray()};end=time.monotonic()+10;error=None
 try:
  while sel.get_map():
   if time.monotonic()>end:raise InvalidEvidence('OS observer command timeout')
   for k,_ in sel.select(.02):
    by=os.read(k.fileobj.fileno(),min(65536,max(1,limit-sum(map(len,data.values()))+1)))
    if not by:sel.unregister(k.fileobj);continue
    data[k.data]+=by
    if sum(map(len,data.values()))>limit:raise InvalidEvidence('OS observer output limit')
  rc=p.wait(timeout=1)
 except Exception as e:error=repr(e);p.kill();p.wait();rc=p.returncode
 finally:sel.close()
 for key,by in data.items():(root/f'{n:03d}.{key}').write_bytes(by)
 (root/f'{n:03d}.command.json').write_text(json.dumps({'argv':argv,'exit':rc,'error':error},indent=2)+'\n')
 if rc or error:raise InvalidEvidence(error or ('OS command failed '+bytes(data['stderr']).decode(errors='replace')[:300]))
 return bytes(data['stdout'])
def full_id(v):
 if not isinstance(v,str) or len(v)!=64 or any(x not in '0123456789abcdef' for x in v):raise InvalidEvidence('full actual Engine ID required')
 return v
def helper(root,pid,namespace,task_pid,uid):
 if hashlib.sha256(PROFILE.read_bytes()).hexdigest()!=PROFILE_SHA:raise InvalidEvidence('fixed seccomp drift')
 code=r"""import os,pathlib,json
P=pathlib.Path;pid=PID;task=TASK;ns=NS
if ns is None:
 try:ns=os.readlink('/proc/'+str(pid)+'/ns/pid')
 except OSError:pass
pids=[]
for p in P('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  if os.readlink(p/'ns/pid')==ns:pids.append(int(p.name))
 except OSError:pass
status={}
try:status=dict(x.split(':',1) for x in P('/proc/'+str(task)+'/status').read_text().splitlines() if ':' in x)
except OSError:pass
try:task_ns=os.readlink('/proc/'+str(task)+'/ns/pid')
except OSError:task_ns=None
print(json.dumps({'namespace':ns,'pids':sorted(pids),'task_status':status,'task_namespace':task_ns,'observer_namespace':os.readlink('/proc/self/ns/pid')}))
""".replace('PID',str(int(pid))).replace('TASK',str(int(task_pid))).replace('NS',repr(namespace))
 args=['docker','create','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--security-opt','seccomp='+str(PROFILE),'--user',str(uid)+':'+str(uid),'--pid','host','--network','none','--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','.5','--shm-size','1m','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64','--log-driver','none',IMAGE,'python','-c',code]
 cid=full_id(run(args,root).decode().strip())
 try:
  run(['docker','inspect',cid],root);by=run(['docker','start','-a',cid],root);run(['docker','inspect',cid],root);return json.loads(by)
 finally:run(['docker','rm','-f',cid],root)
def observe_namespace(root,pid,namespace,task_pid):
 a=helper(root,pid,namespace,task_pid,0)
 if not isinstance(a['namespace'],str) or not a['namespace'].startswith('pid:['):raise InvalidEvidence('original namespace not independently identified')
 b=helper(root,pid,a['namespace'],task_pid,1000)
 return {'namespace':a['namespace'],'pids':sorted(set(a['pids']+b['pids'])),'task_status':b['task_status'] or a['task_status'],'task_namespace':b['task_namespace'] or a['task_namespace'],'observer_namespace':a['observer_namespace']}
def start_witness(binding,root,argv):
 cid=full_id(binding['container_id']);eid=full_id(binding['exec_id']);st=json.loads(run(['docker','inspect',cid],root))[0]
 endpoint=json.loads(run(['docker','context','inspect'],root))[0]['Endpoints']['docker']['Host']
 if not endpoint.startswith('unix://'):raise InvalidEvidence('fixed local Linux Engine socket required')
 class Unix(http.client.HTTPConnection):
  def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(endpoint[7:])
 h=Unix('localhost');h.request('GET','/v1.48/exec/'+eid+'/json');z=h.getresponse();by=z.read(1048577);h.close();(root/'exec-inspect.raw').write_bytes(by)
 if z.status!=200 or len(by)>1048576:raise InvalidEvidence('actual exec inspection unavailable')
 ex=json.loads(by);cfg=ex['ProcessConfig']
 if ex['ContainerID']!=cid or not ex['Running'] or not st['State']['Running'] or [cfg['entrypoint'],*cfg['arguments']]!=argv:raise InvalidEvidence('S original exec/container/argv binding differs')
 facts=observe_namespace(root,st['State']['Pid'],None,ex['Pid']);status=facts['task_status']
 if facts['namespace']==facts['observer_namespace'] or facts['task_namespace']!=facts['namespace'] or ex['Pid'] not in facts['pids']:raise InvalidEvidence('actual S exec is not in its isolated keeper PID namespace')
 if int(status['Uid'].split()[0])!=1000 or int(status['CapEff'].strip(),16)!=0:raise InvalidEvidence('S actual UID/caps differ')
 witness={'container_id':cid,'exec_id':eid,'object_generation':binding['object_generation'],'namespace':facts['namespace'],'before_pids':facts['pids'],'task_pid':ex['Pid'],'task_namespace':facts['task_namespace'],'host_pid_namespace':facts['observer_namespace']};(root/'start-witness.json').write_text(json.dumps(witness,indent=2)+'\n');return witness
def stop_witness(binding,witness,root):
 if any(binding[k]!=witness[k] for k in ('container_id','exec_id','object_generation')):raise InvalidEvidence('stop evidence changes original physical binding')
 facts=observe_namespace(root,0,witness['namespace'],0);(root/'stop-witness.json').write_text(json.dumps(facts,indent=2)+'\n')
 return [{'type':'remaining_original_namespace_pid','pid':pid,'namespace':facts['namespace'],'container_id':binding['container_id'],'exec_id':binding['exec_id']} for pid in facts['pids']]
