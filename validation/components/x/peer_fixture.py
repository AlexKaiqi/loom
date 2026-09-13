"""Trusted live TCP peer within the original two-object budget; no X implementation."""
from pathlib import Path
import base64,copy,hashlib,ipaddress,json,time,uuid
from datetime import datetime,timezone,timedelta
from fixtures import script_bytes
from oracle import EvidenceError
from collector import ENV

def require(value,message):
 if not value:raise EvidenceError(message)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
class LivePeer:
 def __init__(self,observer,fx,out):
  self.observer=observer;self.fx=fx;self.out=out;self.peer=None;self.network=None;self.plan=None;self.original=None;self.before=None;self.complete_record=None;self.occupancies=[];self.parameters=copy.deepcopy(fx['params']);self.tag=uuid.uuid4().hex
 def save(self,name,value):(self.out/name).write_text(json.dumps(value,indent=2)+'\n')
 def occupancy(self):
  ids=set(self.observer.ids('container'))-set(self.observer.baseline_containers);states=[self.observer.inspect(cid) for cid in sorted(ids)];require(all(states),'object disappeared while observing budget');total=sum(s['HostConfig']['Memory'] for s in states);row={'objects':len(ids),'memory_bytes':total,'containers':[{'id':s['Id'],'memory_bytes':s['HostConfig']['Memory']} for s in states]};self.occupancies.append(row);self.save('peer-occupancies.json',self.occupancies);require(len(ids)<=2 and total<=268435456,'peer facility exceeded original two-object/256MiB budget');return row
 def prepare(self):
  require(self.network is None,'peer already prepared');name='lore-x-peer-'+self.tag;self.network=self.observer.run(['docker','network','create','--internal','--label','lore.validation.peer='+self.tag,name])[1].decode().strip();actual=json.loads(self.observer.run(['docker','network','inspect',self.network])[1])[0];require(actual['Internal'] is True and actual['Id']==self.network,'not original internal peer network');nets=[row for row in actual['IPAM']['Config'] if ':' not in row['Subnet']];require(len(nets)==1,'one actual IPv4 allocation required');discovered=copy.deepcopy(actual);self.observer.run(['docker','network','rm',self.network]);self.network=None;name+='-fixed';self.network=self.observer.run(['docker','network','create','--internal','--subnet',nets[0]['Subnet'],'--gateway',nets[0]['Gateway'],'--label','lore.validation.peer='+self.tag,name])[1].decode().strip();actual=json.loads(self.observer.run(['docker','network','inspect',self.network])[1])[0];require(actual['Id']==self.network and actual['Internal'] is True and actual['IPAM']['Config']==nets,'explicit original subnet differs');net=ipaddress.ip_network(nets[0]['Subnet']);gateway=ipaddress.ip_address(nets[0]['Gateway']);ip=gateway+1;require(ip in net and ip!=net.broadcast_address and not actual.get('Containers'),'peer address not reserved within new empty network');self.plan={'network_id':self.network,'network_name':name,'network_inspect':actual,'allocation_discovery':discovered,'ip':str(ip),'bad_task_ip':str(ip+1),'port':29293,'marker':'live-own-peer-'+self.tag};require(ip+1 in net and ip+1!=net.broadcast_address,'fixture needs two own reserved addresses');self.fx['peer']=copy.deepcopy(self.plan)
  params={**self.fx['params'],'peer_ip':self.plan['ip'],'peer_port':self.plan['port']};self.fx['request']['script_base64']=base64.b64encode(script_bytes(self.fx['script'],params)).decode();self.original=copy.deepcopy(self.fx['request']);self.save('peer-plan.json',{'plan':self.plan,'original_request':self.original,'request_digest':hashlib.sha256(canonical(self.original)).hexdigest(),'original_parameters':self.parameters});self.check_request();self.occupancy()
 def check_request(self):require(self.fx['params']==self.parameters and self.fx['request']==self.original,'derived peer address changed original request/parameter grid')
 def connect(self):
  code="import socket,time,json\nend=time.monotonic()+2\nwhile True:\n try:\n  s=socket.create_connection(("+repr(self.plan['ip'])+","+str(self.plan['port'])+"),.2);raw=s.recv(256);s.close();assert raw=="+repr(self.plan['marker'].encode())+";print(json.dumps({'marker_hex':raw.hex()}));break\n except OSError:\n  if time.monotonic()>=end:raise\n  time.sleep(.01)"
  by=self.observer.run(['docker','exec','--user','1000:1000',self.peer,'python','-c',code])[1];obj=json.loads(by);require(obj=={'marker_hex':self.plan['marker'].encode().hex()},'live peer positive connection missing');return obj
 def start(self,binding):
  self.check_request();require(self.plan and self.peer is None,'peer state');self.original_binding=copy.deepcopy(binding);ex=self.observer.exec_inspect(binding['exec_id']);require(ex and ex['ID']==binding['exec_id'] and ex['ContainerID']==binding['container_id'] and ex['Running'] is False and 'ExitCode' in ex and ex['ExitCode'] is None and type(ex.get('Pid')) is int and ex['Pid']==0,'original exec must be unstarted CREATED before live peer');self.occupancy();require(self.occupancies[-1]['objects']<=1,'peer needs original reserved second slot')
  code="import socket;s=socket.socket();s.bind(('0.0.0.0',"+str(self.plan['port'])+"));s.listen()\nwhile True:\n c,a=s.accept();c.sendall("+repr(self.plan['marker'].encode())+");c.close()"
  self.peer=self.observer.run(['docker','create',*self.observer.options(network=self.plan['network_name']),'--ip',self.plan['ip'],'--label','lore.validation.peer='+self.tag,ENV['image'],'python','-u','-c',code])[1].decode().strip();self.observer.run(['docker','start',self.peer]);self.before=self.observer.inspect(self.peer);require(self.before['Config']['Labels']['lore.validation.peer']==self.tag and self.before['NetworkSettings']['Networks'][self.plan['network_name']]['IPAddress']==self.plan['ip'] and self.before['State']['Running'] and not self.before['State']['Paused'],'actual live peer identity/address');positive=self.connect();self.occupancy();self.save('peer-started.json',{'Engine':self.before,'positive':positive,'original_exec':ex})
 def completion(self,binding):
  self.check_request();require(binding.get('container_id')==self.original_binding['container_id'] and binding.get('exec_id')==self.original_binding['exec_id'],'peer task execution changed');execution=self.observer.exec_inspect(binding['exec_id']);require(execution and execution['ID']==binding['exec_id'] and execution['ContainerID']==binding['container_id'] and execution['Running'] is False and execution['ExitCode']==0,'task did not really finish before peer shutdown');wanted=[*self.original['interpreter_argv'],base64.b64decode(self.original['script_base64']).decode()];actual=[execution['ProcessConfig']['entrypoint'],*execution['ProcessConfig']['arguments']];require(actual==wanted,'actual network attempt differs from frozen request');after=self.observer.inspect(self.peer);self.check_peer(after);positive=self.connect()
  # Engine original event history rules out intervening pause/kill/restart during attempt.
  until=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat(timespec='microseconds').replace('+00:00','Z');raw=self.observer.run(['docker','events','--since',self.before['Created'],'--until',until,'--filter','container='+self.peer,'--format','{{json .}}'],timeout=5)[1];events=[json.loads(line) for line in raw.splitlines()];self.check_events(events);last=self.observer.inspect(self.peer);self.check_peer(last);self.occupancy();record={'physical':{'exec':execution},'peer':{'before':self.before,'after':last,'positive':positive,'events':events,'continuous':True},'request_digest':hashlib.sha256(canonical(self.original)).hexdigest(),'request_unchanged':True,'parameters_unchanged':True,'max_objects':max(x['objects'] for x in self.occupancies),'max_memory_bytes':max(x['memory_bytes'] for x in self.occupancies)};self.complete_record=record;self.save('peer-completion.json',record);return record
 def check_peer(self,after):
  require(after and after['Id']==self.peer and after['State']['Running'] and not after['State']['Paused'] and after['State']['Pid']==self.before['State']['Pid'] and after['State']['StartedAt']==self.before['State']['StartedAt'] and after['RestartCount']==self.before['RestartCount'],'peer not continuously original live object')
 def check_events(self,events):
  require(events and all(e.get('Actor',{}).get('ID')==self.peer and e.get('Type')=='container' for e in events),'original peer event history missing/wrong source');actions=[e.get('Action','').split(':',1)[0] for e in events];require(actions.count('start')==1 and not any(a in ('pause','unpause','kill','die','stop','restart','destroy') for a in actions),'peer interrupted during actual network attempt')
 def stop(self):
  require(self.complete_record is not None,'cannot stop peer before actual attempted-task completion');self.remove_peer()
 def remove_peer(self):
  if self.peer:
   state=self.observer.inspect(self.peer)
   if state:
    require(state['Id']==self.peer and state['Config'].get('Labels',{}).get('lore.validation.peer')==self.tag,'refuse unrelated peer cleanup');self.observer.run(['docker','rm','-f',self.peer])
   self.peer=None
 def cleanup(self):
  self.remove_peer()
  if self.network:self.observer.run(['docker','network','rm',self.network]);self.network=None
