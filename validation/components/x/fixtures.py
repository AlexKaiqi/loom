"""Harmless test inputs for X; no executor implementation or production state."""
from pathlib import Path
import base64, hashlib, json, os, socket, uuid

def sha(b): return hashlib.sha256(b).hexdigest()
STDOUT=bytes(range(256))*32
STDERR=b'error\x00\xff\r\n'*97
PREFIX='{"type":"original-intent","id":"one"}\n'
RESTORE_CONFIG=b'{"mode":"original","limit":5}\n'
RESTORE_STDOUT=b'RESTORE_ORIGINAL_RECEIPT\n'
SCRIPTS={
'restore_seed':"""with open('/work/effect','ab') as f:f.write(b'one\\n');f.flush();os.fsync(f.fileno())
write('input-result',Path('/work/input-a').read_bytes()+Path('/work/untracked-dependency').read_bytes()+Path('/work/config.json').read_bytes())
os.write(1,b'RESTORE_ORIGINAL_RECEIPT\\n')""",
'restore_readonly':"""import hashlib
facts={'input_a':hashlib.sha256(Path('/work/input-a').read_bytes()).hexdigest(),'dependency':hashlib.sha256(Path('/work/untracked-dependency').read_bytes()).hexdigest(),'config':hashlib.sha256(Path('/work/config.json').read_bytes()).hexdigest(),'effect_count':Path('/work/effect').read_bytes().count(b'one\\n')}
print(json.dumps(facts,sort_keys=True),flush=True);time.sleep(5)""",
'identity':"write('identity.json', json.dumps({'uid':os.getuid(),'domain':P['domain']})); time.sleep(5)",
'effect':"with open('/work/effect','ab') as f:f.write(b'one\\n');f.flush();os.fsync(f.fileno())",
'create_child':"Path('/work/created').mkdir(exist_ok=True);write('created/data.bin',b'created')",
'escape_paths':"""denied=[]
for p in ['/control/canary','/var/run/docker.sock','/unauthorized/canary']:
 try:open(p,'r+b');denied.append(p)
 except OSError:pass
os.chdir('/tmp');write('escape.json',json.dumps({'denied_all':not denied,'opened':denied}))""",
'binary':"os.write(1,bytes(range(256))*32);os.write(2,b'error\\x00\\xff\\r\\n'*97)",
'binary_effect':"write('effect',b'one\\n');os.write(1,bytes(range(256))*32);os.write(2,b'error\\x00\\xff\\r\\n'*97)",
'output_flood':"while True:os.write(1,b'x'*4096);os.write(2,b'y'*4096)",
'heartbeat':"""fd=os.open('/work/heartbeat',os.O_CREAT|os.O_RDWR,0o600);i=0
while True:
 i+=1;os.pwrite(fd,str(i).encode().ljust(32,b' '),0);os.fsync(fd)
 print(json.dumps({'lore_fixture_ready':'heartbeat','value':i}),flush=True);time.sleep(.03)""",
'orphan':"""pid=os.fork()
if pid:os._exit(0)
os.setsid();fd=os.open('/work/heartbeat',os.O_CREAT|os.O_RDWR,0o600);i=0
while True:
 i+=1;os.pwrite(fd,str(i).encode().ljust(32,b' '),0);time.sleep(.03)""",
'keeper_attack':"""write('locked.bin',b'preserved-after-command-exit');os.chmod('/work/locked.bin',0);err=None
try:os.kill(1,signal.SIGKILL)
except OSError as e:err=e.errno
import ctypes
libc=ctypes.CDLL(None,use_errno=True);libc.ptrace(16,1,0,0);ptrace_errno=ctypes.get_errno();setuid_errno=None
try:os.setuid(0)
except OSError as e:setuid_errno=e.errno
write('keeper.json',json.dumps({'kill_errno':err,'ptrace_errno':ptrace_errno,'setuid_errno':setuid_errno}))""",
'leak':"""found=[]
for p in ['/control/canary','/var/run/docker.sock','/proc/1/root/control/canary']:
 try:
  b=Path(p).read_bytes()
  if b:found.append(p)
 except OSError:pass
for p in Path('/proc/self/fd').iterdir():
 try:
  n=int(p.name)
  if n>2:
   link=os.readlink(p)
   if 'control-canary' in link:found.append(str(p))
   if link.startswith('socket:'):
    try:os.set_blocking(n,False);os.write(n,b'X-LEAK-PROBE');found.append('socket-write-'+str(n))
    except OSError:pass
 except OSError:pass
if 'LORE_TEST_CONTROL_CANARY' in os.environ:found.append('environment')
write('leak.json',json.dumps({'forbidden_successes':found}))""",
'network':"""s=socket.socket();s.settimeout(.3);err=0
try:s.connect((P['peer_ip'],P['peer_port']))
except OSError as e:err=e.errno or -1
finally:s.close()
write('network.json',json.dumps({'peer_connect_errno':err,'engine_available':Path('/var/run/docker.sock').exists()}))""",
'quota':"""err=None;fds=[];i=0
try:
 if P['quota_mode']=='inodes':
  while True:
   p=Path('/work')/('fill-'+str(i));fd=os.open(p,os.O_CREAT|os.O_WRONLY,0o600);fds.append(fd);i+=1
 else:
  p=Path('/work/fill-bytes');fd=os.open(p,os.O_CREAT|os.O_WRONLY,0o600);fds.append(fd)
  if P['quota_mode']=='unlinked':os.unlink(p)
  while True:os.write(fd,b'x'*65536)
except OSError as e:err=e.errno
s=os.statvfs('/work');fact={'errno':err,'total':s.f_frsize*s.f_blocks,'free':s.f_frsize*s.f_bavail,'inodes':s.f_files,'inodes_free':s.f_favail,'limit_matches':s.f_frsize*s.f_blocks==P['volume_bytes'] and s.f_files==P['inode_limit']}
print(json.dumps(fact),flush=True);sys.stdin.buffer.readline()
# All quota allocation and the same unlinked FD remain until the external observation.
for fd in fds:os.close(fd)
for p in Path('/work').glob('fill-*'):p.unlink()
write('quota.json',json.dumps(fact))""",
'unsupported_output':"""kind=P['unsupported']
if kind=='sparse':
 with open('/work/huge','wb') as f:f.truncate(16*1024*1024)
elif kind=='fifo':os.mkfifo('/work/pipe')
elif kind=='socket':s=socket.socket(socket.AF_UNIX);s.bind('/work/socket')""",
'resource':"""kind=P['resource'];time.sleep(.35)
if kind=='memory':
 xs=[]
 while True:xs.append(bytearray(4*1024*1024))
elif kind=='pids':
 children=[];err=None
 try:
  while True:
   pid=os.fork()
   if pid==0:time.sleep(30);os._exit(0)
   children.append(pid)
 except OSError as e:err=e.errno
 write('resource.json',json.dumps({'fork_errno':err,'children':len(children)}));time.sleep(30)
else:
 while True:pass""",
'input_version':"write('input-result',Path('/work/input-a').read_bytes()+Path('/work/untracked-dependency').read_bytes())",
'session_prefix':"""with open('/work/session.jsonl','ab',buffering=0) as f:
 f.write(b'{"type":"original-intent","id":"one"}\\n');os.fsync(f.fileno());print(json.dumps({'lore_fixture_ready':'session_prefix','value':f.tell()}),flush=True);time.sleep(.1)
 for i in range(100):f.write((json.dumps({'type':'original-result','n':i})+'\\n').encode());os.fsync(f.fileno());print(json.dumps({'lore_fixture_ready':'session_prefix','value':f.tell()}),flush=True);time.sleep(.03)""",
'duplex':"""with open('/work/session.jsonl','ab',buffering=0) as f:
 f.write(b'intent-one\\n');os.fsync(f.fileno());os.write(1,b'intent-one\\n')
 response=sys.stdin.buffer.readline();f.write(response);os.fsync(f.fileno());os.write(1,b'accepted\\n')"""
}
# Script strings are literal executable Python, never domain commands.
def script_bytes(name,params):
 code='import os,sys,time,json,signal,socket\nfrom pathlib import Path\nP='+repr(params)+'\ndef write(n,b):\n p=Path("/work")/n\n if isinstance(b,str):b=b.encode()\n p.write_bytes(b)\n'+SCRIPTS[name]+'\n'
 # Decode only the doubled backslashes deliberately used in embedded script source.
 return code.replace('\\\\','\\').encode()

def create(root,case,params):
 root.mkdir(parents=True,exist_ok=False);state=root/'state';state.mkdir();target=root/'target';target.mkdir();sibling=root/'target-sibling';sibling.mkdir();other=root/'other';other.mkdir();(root/'control').mkdir()
 canary=('self-owned-credential-like-'+uuid.uuid4().hex).encode();(root/'control'/'control-canary').write_bytes(canary)
 for p in [target,sibling,other]:(p/'canary').write_bytes(b'unchanged')
 (target/'input-a').write_bytes(b'alpha');(target/'untracked-dependency').write_bytes(b'beta')
 if case['initial']['script']=='restore_seed':(target/'config.json').write_bytes(RESTORE_CONFIG)
 ino=target.stat();domain=params.get('domain','task');target_id='target-'+domain;eid='exec-'+uuid.uuid4().hex
 values={'target_id':target_id,'created_sha256':sha(b'created'),'locked_sha256':sha(b'preserved-after-command-exit'),'stdout_sha256':sha(STDOUT),'stderr_sha256':sha(STDERR),'input_result_sha256':sha(b'alphabeta'),'session_prefix':PREFIX}
 values['restore_input_result_sha256']=sha(b'alpha'+b'beta'+RESTORE_CONFIG);values['restore_original_stdout_sha256']=sha(RESTORE_STDOUT);values['restore_verify_stdout_sha256']=sha((json.dumps({'input_a':sha(b'alpha'),'dependency':sha(b'beta'),'config':sha(RESTORE_CONFIG),'effect_count':1},sort_keys=True)+'\n').encode())
 cache=root/'cache';cache.mkdir();(cache/'preparation-cache-marker').write_bytes(b'cache-not-authority')
 inputs={'files':[{'path':p.name,'sha256':sha(p.read_bytes()),'size':p.stat().st_size} for p in target.iterdir()]}
 authority={'namespace':'test-'+root.name,'caller':'trusted-fixture','target_id':target_id,'domain':domain,'target_path':str(target),'target_identity':{'dev':ino.st_dev,'ino':ino.st_ino},'binding_generation':1,'base_version':sha(json.dumps(inputs,sort_keys=True).encode()),'write_token':'test-only-token','state_dir':str(state),'allowed_parent':None,'grants':['execute','query','checkpoint','stop'],'metadata_profile':'ordinary-posix-no-xattr-acl'}
 target_case=params.get('target_case','normal');selector={'target_id':target_id,'location':str(target)}
 if target_case=='unauthorized':authority['grants']=[]
 if target_case=='unregistered':selector={'location':str(other)}
 if target_case in ('ambiguous','ambiguous_explicit'):
  authority['same_location_targets']=[target_id,target_id+'-other']
  if target_case=='ambiguous':selector={'location':str(target)}
 if target_case=='prefix_sibling':selector={'location':str(sibling)}
 if target_case in ('symlink_inside','symlink_outside'):
  link=target/'alias';link.symlink_to(target if target_case=='symlink_inside' else other,target_is_directory=True);selector['location']=str(link)
 if target_case=='authorized_parent':authority['allowed_parent']=str(target);selector['location']=str(target/'new-surface')
 if 'input_metadata' in params:inputs['required_metadata']=[params['input_metadata']]
 request={'schema_version':1,'execution_id':eid,'caller':'trusted-fixture','invocation_id':'invocation-one','step_id':'step-one','source_result':'saved-result-one','harness_version':'harness-v1','target_selector':selector,'target_id':selector.get('target_id'),'binding_generation':1,'domain':domain,'base_version':authority['base_version'],'input_manifest':inputs,'input_root':str(target),'cwd':'.','environment':'fixed-python-linux-v1','endpoints':[],'network':'none','budgets':{'memory_bytes':134217728,'pids':32,'cpu':params.get('cpu',.5),'volume_bytes':params.get('volume_bytes',2097152),'inodes':params.get('inode_limit',128),'tmp_bytes':1048576,'shm_bytes':1048576,'stdout_bytes':65536,'stderr_bytes':65536,'combined_output_bytes':98304,'archive_bytes':8388608,'expanded_bytes':12582912,'deadline_seconds':8 if case['initial']['script']=='resource' else 20},'stdin_base64':'','io_mode':'duplex' if case['initial']['script'] in ('duplex','quota','heartbeat','session_prefix') else 'finite','interpreter_argv':['python','-c'],'script_base64':base64.b64encode(script_bytes(case['initial']['script'],{**params,'domain':domain})).decode()}
 return {'root':root,'state':state,'cache':cache,'execution_ids':{eid},'target':target,'other':other,'authority':authority,'request':request,'params':params,'values':values,'canary':canary,'host_initial':{str(p):p.read_bytes() for p in [target/'canary',sibling/'canary',other/'canary',root/'control'/'control-canary']},'human_edit':False,'script':case['initial']['script']}
