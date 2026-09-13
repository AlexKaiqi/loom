"""Finite preparation of the independent OS collector, not an S/X product."""
from pathlib import Path
import hashlib,http.client,json,socket,sys,time,shutil
from physical_witness import run,start_witness,stop_witness,IMAGE,PROFILE
R=Path(__file__).parent;ROOT=R.parents[2];out=R/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False);raw=out/'raw';result={'scope':'S_OS_COLLECTOR_PREPARATION_ONLY','inputs':{},'errors':[]};cid=None;begin=time.monotonic()
for p in [Path(__file__),R/'physical_witness.py',ROOT/'design/g3/s/physical-witness-preparation-protocol.json',ROOT/'design/g3/system/contract.md',PROFILE]:shutil.copy2(p,out/p.name);result['inputs'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
try:
 argv=['docker','create','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--security-opt','seccomp='+str(PROFILE),'--network','none','--memory','512m','--memory-swap','512m','--pids-limit','64','--cpus','1','--shm-size','1m','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64','--log-driver','none',IMAGE,'sleep','30'];cid=run(argv,raw).decode().strip();run(['docker','start',cid],raw)
 endpoint=json.loads(run(['docker','context','inspect'],raw))[0]['Endpoints']['docker']['Host'];assert endpoint.startswith('unix://')
 class Unix(http.client.HTTPConnection):
  def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(endpoint[7:])
 def api(path,body):
  h=Unix('localhost');h.request('POST','/v1.48'+path,json.dumps(body),{'Content-Type':'application/json'});z=h.getresponse();by=z.read(1048576);h.close();name=str(len(list(out.glob('api-*.json'))));(out/('api-'+name+'.json')).write_text(json.dumps({'path':path,'body':body,'status':z.status,'raw':by.decode()},indent=2))
  assert z.status in (200,201);return json.loads(by) if by else None
 command=['python','-c','import time;time.sleep(20)'];eid=api('/containers/'+cid+'/exec',{'AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'User':'1000:1000','Cmd':command})['Id'];api('/exec/'+eid+'/start',{'Detach':True,'Tty':False});binding={'container_id':cid,'exec_id':eid,'object_generation':1};before=start_witness(binding,out/'before',command);run(['docker','kill',cid],raw);after=stop_witness(binding,before,out/'after');result['before']=before;result['after']=after;result['pass']=len(before['before_pids'])>=2 and not after
except Exception as e:result['errors'].append(repr(e));result['pass']=False
finally:
 if cid:run(['docker','rm','-f',cid],raw)
 result['elapsed_seconds']=time.monotonic()-begin;(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'pass':result['pass'],'errors':result['errors'],'elapsed':result['elapsed_seconds']}))
raise SystemExit(0 if result['pass'] else 1)
