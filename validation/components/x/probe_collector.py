"""One fixed existing-Engine fixture to exercise the new external collector. No X product."""
from pathlib import Path
import base64,hashlib,http.client,json,socket,sys,time,shutil
from fixtures import create
from collector import Collector,ENV
from oracle import assess,EvidenceError
R=Path(__file__).parent;ROOT=R.parents[2];out=R/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False);case={'initial':{'script':'identity'}};fx=create(out/'fixture',case,{'domain':'task'});c=Collector(out,fx);cid=None;volume='lore-x-'+fx['request']['execution_id'];result={'type':'G3_COLLECTOR_FACILITY_PREFLIGHT','production_X':'NOT_IMPLEMENTED','inputs':{},'frames':{},'errors':[]};deadline=time.monotonic()+60
for p in [Path(__file__),R/'collector.py',R/'oracle.py',R/'fixtures.py',ROOT/'design/g3/x/collector-preflight-protocol.json',ROOT/'design/g3/x/environment.json']:
 shutil.copy2(p,out/p.name);result['inputs'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
endpoint=json.loads(c.run(['docker','context','inspect'])[1])[0]['Endpoints']['docker']['Host'];assert endpoint.startswith('unix://')
class Unix(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(endpoint[7:])
def api(path,obj):
 h=Unix('localhost',timeout=5);data=json.dumps(obj).encode();h.request('POST','/v1.48'+path,data,{'Content-Type':'application/json'});z=h.getresponse();by=z.read(1048577);status=z.status;h.close();n=c.serial;c.serial+=1;(out/f'raw-{n:04d}.api-request.json').write_text(json.dumps({'path':path,'body':obj},indent=2)+'\n');(out/f'raw-{n:04d}.api-response').write_bytes(by)
 if status not in (200,201):raise EvidenceError('Engine POST '+str(status)+' '+by.decode(errors='replace'))
 return json.loads(by) if by else None
try:
 c.run(['docker','volume','create','--label','lore.x.execution_id='+fx['request']['execution_id'],'--driver','local','--opt','type=tmpfs','--opt','device=tmpfs','--opt','o=size=2m,nr_inodes=128,uid=1000,gid=1000,mode=0700,nosuid,nodev',volume])
 cid=c.run(['docker','create',*c.options(),'--label','lore.x.execution_id='+fx['request']['execution_id'],'--user','0:0','--mount','type=volume,src='+volume+',dst=/work,volume-nocopy',ENV['image'],'sleep','30'])[1].decode().strip();c.run(['docker','start',cid])
 code="import os,json,time;from pathlib import Path;Path('/work/identity.json').write_text(json.dumps({'uid':os.getuid(),'domain':'task'}));time.sleep(20)"
 fx['request']['script_base64']=base64.b64encode(code.encode()).decode()
 eid=api('/containers/'+cid+'/exec',{'AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'User':'1000:1000','Cmd':['python','-c',code]})['Id'];binding={'container_id':cid,'volume_id':volume,'exec_id':eid,'object_generation':1,'domain':'task'};(out/'original-exec-binding.json').write_text(json.dumps(binding,indent=2)+'\n');api('/exec/'+eid+'/start',{'Detach':True,'Tty':False})
 result['frames']['running']=c.capture({},binding,'running');c.run(['docker','pause',cid]);result['frames']['prepared']=c.capture({},binding,'prepared');c.run(['docker','kill',cid]);result['frames']['stopped']=c.capture({},binding,'stopped')
 expected=[{'path':'running.physical.task_uid','comparison':'eq','value':1000},{'path':'running.physical.cap_eff','comparison':'eq','value':0},{'path':'running.physical.namespace_pids','comparison':'length_gt','value':1},{'path':'prepared.archive.files.identity.json.json.uid','comparison':'eq','value':1000},{'path':'prepared.archive.files.identity.json.json.domain','comparison':'eq','value':'task'},{'path':'stopped.physical.namespace_pids','comparison':'eq','value':[]},{'path':'stopped.physical.container_running','comparison':'eq','value':False}]
 cg=result['frames']['running']['physical']['cgroup']
 expected.extend([{'path':'running.physical.cgroup.memory/memory.failcnt','comparison':'eq','value':'0\n'},{'path':'running.physical.cgroup.pids/pids.max','comparison':'eq','value':'32\n'}])
 result['assessment']=assess(expected,result['frames'],{},{});result['cgroup_numeric_checks']={'pids_at_least_two':int(cg.get('pids/pids.current','-1'))>=2,'cpu_ratio':int(cg.get('cpu/cpu.cfs_quota_us','-1'))/int(cg.get('cpu/cpu.cfs_period_us','1'))==.5};result['pass']=result['assessment']['pass'] and all(result['cgroup_numeric_checks'].values())
except Exception as e:result['errors'].append(repr(e));result['pass']=False
finally:
 if cid:c.run(['docker','rm','-f',cid],check=False)
 c.run(['docker','volume','rm',volume],check=False)
 result['elapsed_seconds']=60-(deadline-time.monotonic());(out/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'pass':result['pass'],'errors':result['errors'],'elapsed':result['elapsed_seconds']}))
raise SystemExit(0 if result['pass'] else 1)
