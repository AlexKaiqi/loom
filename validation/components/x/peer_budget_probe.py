"""Direct facility controls, never a substitute for actual X019 candidate execution."""
from pathlib import Path
import base64,copy,http.client,io,json,os,socket,sys,time,uuid
from collector import Collector,ENV
from fixtures import create
from peer_fixture import LivePeer
from oracle import EvidenceError
from source_closure import inventory
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=False)
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def api(observer,method,path,obj=None):
 endpoint=json.loads(observer.run(['docker','context','inspect'])[1])[0]['Endpoints']['docker']['Host'];assert endpoint.startswith('unix://')
 class Unix(http.client.HTTPConnection):
  def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(endpoint[7:])
 h=Unix('localhost',timeout=5);h.request(method,'/v1.48'+path,None if obj is None else json.dumps(obj).encode(),{'Content-Type':'application/json'});z=h.getresponse();raw=z.read(1048577);h.close();n=observer.serial;observer.serial+=1;save(observer.out/f'raw-{n:04d}.facility-Engine.json',{'method':method,'path':path,'request':obj,'status':z.status,'raw':raw.decode()});assert z.status in (200,201) and len(raw)<=1048576;return json.loads(raw) if raw else None

def run(mode):
 dest=OUT/mode;dest.mkdir();case=next(x for x in json.loads((ROOT/'design/g3/x/cases.json').read_text())['cases'] if x['id']=='X019');fx=create(dest/'fixture',case,{'domain':'task'});observer=Collector(dest,fx);peer=LivePeer(observer,fx,dest);cid=vol=None
 try:
  peer.prepare();vol='lore-peer-probe-'+uuid.uuid4().hex;observer.run(['docker','volume','create','--driver','local','--opt','type=tmpfs','--opt','device=tmpfs','--opt','o=size=2m,nr_inodes=128,uid=1000,gid=1000,mode=0700','--label','lore.x.execution_id='+fx['request']['execution_id'],vol]);network=peer.plan['network_name'] if mode=='bad-shared-network' else 'none';extra=['--ip',peer.plan['bad_task_ip']] if mode=='bad-shared-network' else []
  cid=observer.run(['docker','create',*observer.options(network=network),*extra,'--user','1000:1000','--label','lore.x.execution_id='+fx['request']['execution_id'],'--mount','type=volume,src='+vol+',dst=/work,volume-nocopy',ENV['image'],'sleep','60'])[1].decode().strip();observer.run(['docker','start',cid]);peer.occupancy()
  # Actual import helper occurs before peer exists, as the original product CREATED boundary promises.
  observer.helper(['--user','1000:1000','--mount','type=volume,src='+vol+',dst=/work,volume-nocopy',ENV['image'],'python','-c',"from pathlib import Path;Path('/work/imported').write_bytes(b'original')"]);peer.occupancy()
  request=copy.deepcopy(fx['request']);argv=[*request['interpreter_argv'],base64.b64decode(request['script_base64']).decode()];eid=api(observer,'POST','/containers/'+cid+'/exec',{'AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'User':'1000:1000','WorkingDir':'/work','Cmd':argv})['Id'];binding={'container_id':cid,'exec_id':eid,'volume_id':vol,'object_generation':1,'freeze_generation':0};peer.start(binding)
  api(observer,'POST','/exec/'+eid+'/start',{'Detach':True,'Tty':False});end=time.monotonic()+5
  while observer.exec_inspect(eid)['Running']:
   if time.monotonic()>end:raise TimeoutError('finite network task');
   time.sleep(.01)
  completed=peer.completion(binding);assert fx['params']=={'domain':'task'} and fx['request']==request;peer.stop();peer.occupancy();observer.run(['docker','pause',cid]);frame=observer.capture({'binding':binding},binding,'prepared');fact=frame['archive']['files']['network.json']['json'];expected=mode=='bad-shared-network';assert (fact['peer_connect_errno']==0)==expected and fact['engine_available'] is False;save(dest/'observations.json',{'mode':mode,'errno':fact['peer_connect_errno'],'network':frame['physical']['network_mode'],'peer_completion':completed,'actual_budget':peer.occupancies,'source_request_unchanged':fx['request']==request,'parameters':fx['params']});return {'mode':mode,'pass':True,'bad_mechanism_rejected':expected,'actual_errno':fact['peer_connect_errno']}
 finally:
  if cid:observer.run(['docker','rm','-f',cid],check=False)
  peer.cleanup()
  if vol:observer.run(['docker','volume','rm',vol],check=False)
  own=observer.ids('container');save(dest/'cleanup.json',{'remaining_own_containers':[x for x in own if x not in observer.baseline_containers],'remaining_own_volumes':[x for x in observer.ids('volume') if x not in observer.baseline_volumes]})

def controls():
 rows=[];peer=LivePeer.__new__(LivePeer);peer.peer='a'*64;peer.before={'Id':peer.peer,'State':{'Running':True,'Paused':False,'Pid':123,'StartedAt':'original'},'RestartCount':0};peer.original={'original':'request'};peer.fx={'request':{'original':'request'},'params':{'domain':'task'}};peer.parameters={'domain':'task'};peer.check_request();peer.check_peer(copy.deepcopy(peer.before));events=[{'Type':'container','Actor':{'ID':peer.peer},'Action':'start'}];peer.check_events(events)
 for name,fn in [('missing-events',lambda:peer.check_events([])),('pause-event',lambda:peer.check_events(events+[{'Type':'container','Actor':{'ID':peer.peer},'Action':'pause'}])),('wrong-event-id',lambda:peer.check_events([{'Type':'container','Actor':{'ID':'b'*64},'Action':'start'}])),('wrong-peer',lambda:peer.check_peer({**peer.before,'Id':'b'*64})),('stopped-peer',lambda:peer.check_peer({**peer.before,'State':{**peer.before['State'],'Running':False}})),('new-peer-pid',lambda:peer.check_peer({**peer.before,'State':{**peer.before['State'],'Pid':456}}))]:
  try:fn()
  except EvidenceError:rows.append({'name':name,'rejected':True})
  else:raise AssertionError(name+' not rejected')
 peer.fx['params']['peer_ip']='pollution'
 try:peer.check_request()
 except EvidenceError:rows.append({'name':'parameter-pollution','rejected':True})
 else:raise AssertionError('mutated parameters accepted')
 old=json.loads((ROOT/'design/g4/x-peer-budget-repair-001/prior/design/g3/x/cases.json').read_text());new=json.loads((ROOT/'design/g3/x/cases.json').read_text());assert inventory(old['cases'])==inventory(new['cases']) and len(inventory(new['cases']))==97
 for a,b in zip(old['cases'],new['cases']):
  assert a['expected']==b['expected'][:len(a['expected'])]
  if a['id']!='X019':assert a==b
 save(OUT/'controls.json',rows);return rows
if __name__=='__main__':
 rec={'scope':'PEER_BUDGET_FACILITY_PREPARATION_NOT_X','controls':controls(),'runs':[]};save(OUT/'assessment.json',rec)
 try:
  for mode in ['network-none','bad-shared-network']:rec['runs'].append(run(mode));save(OUT/'assessment.json',rec)
  rec['status']='PASS_PREPARATION_ONLY'
 except Exception as e:rec['status']='FAIL';rec['error']=repr(e);raise
 finally:save(OUT/'assessment.json',rec)
