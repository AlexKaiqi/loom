"""Explicitly scheduled Docker load probe; requires existing prepared projection, no X product."""
from pathlib import Path
import argparse,hashlib,http.client,io,json,os,socket,subprocess,tarfile,time,uuid
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--projection',required=True);ap.add_argument('--docker-window',action='store_true');a=ap.parse_args()
 if not a.docker_window:ap.error('Docker probe disabled without root-coordinated --docker-window')
 if not a.batch.replace('-','').isalnum():ap.error('fresh batch')
 out=Path(__file__).parent/'evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);projection=Path(a.projection).resolve();profile=json.loads((ROOT/'design/g3/x-node-profile/profile.json').read_text());manifest=json.loads((ROOT/'design/g3/x-node-profile/dependencies.json').read_text())
 from prepare import verify
 verify(projection,manifest)
 # Dedicated projected fixture root retains ordinary imports; candidate upstream files unchanged.
 fixture=out/'fixture';fixture.mkdir();entry=fixture/'probe-public.mts';entry.write_text((ROOT/'validation/components/s/probe-public.mts').read_text().replace('../../../research/repos/pi','/opt/lore/research/repos/pi'))
 config=fixture/'tsconfig.json';config.write_bytes((ROOT/'design/g3/x-node-profile/tsconfig.json').read_bytes())
 rec={'scope':'PROJECTED_NODE_PI_LOAD_PREPARATION_NOT_X','profile_sha256':sha(ROOT/'design/g3/x-node-profile/profile.json'),'manifest_sha256':sha(ROOT/'design/g3/x-node-profile/dependencies.json'),'probe_source_sha256':sha(Path(__file__)),'entry_sha256':sha(entry),'config_sha256':sha(config),'commands':[],'runs':[]};counter=0
 def save(): (out/'assessment.json').write_text(json.dumps(rec,indent=2)+'\n')
 def cmd(argv,limit=18874368):
  nonlocal counter
  counter+=1;p=subprocess.run(argv,capture_output=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=10)
  for stream in ['stdout','stderr']:(out/f'{counter:03d}.{stream}').write_bytes(getattr(p,stream))
  rec['commands'].append({'n':counter,'argv':argv,'exit':p.returncode});save()
  if p.returncode or len(p.stdout)+len(p.stderr)>limit:raise RuntimeError('command failed/cap: '+str(argv)+' '+p.stderr.decode(errors='replace')[:400])
  return p.stdout
 endpoint=json.loads(cmd(['docker','context','inspect']))[0]['Endpoints']['docker']['Host']
 if not endpoint.startswith('unix://'):raise ValueError('fixed local Linux endpoint')
 class Unix(http.client.HTTPConnection):
  def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(endpoint[7:])
 def api(method,path,obj=None):
  nonlocal counter
  h=Unix('localhost',timeout=5);h.request(method,'/v1.48'+path,None if obj is None else json.dumps(obj).encode(),{'Content-Type':'application/json'});z=h.getresponse();raw=z.read(1048577);h.close();counter+=1;(out/f'{counter:03d}.Engine.json').write_text(json.dumps({'method':method,'path':path,'request':obj,'status':z.status,'raw':raw.decode()},indent=2));save()
  if z.status not in (200,201) or len(raw)>1048576:raise RuntimeError('Engine API failure')
  return json.loads(raw) if raw else None
 cid=helper=None;vol=None
 try:
  for mode in ['single','multi']:
   vol='lore-xn-probe-'+uuid.uuid4().hex;cmd(['docker','volume','create','--driver','local','--opt','type=tmpfs','--opt','device=tmpfs','--opt','o=size=16m,nr_inodes=512,uid=1000,gid=1000,mode=0700,nosuid,nodev',vol]);seccomp=str(ROOT/'research/docker-linux/seccomp.json')
   common=['--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--security-opt','seccomp='+seccomp,'--network','none','--log-driver','none','--shm-size','1m']
   cid=cmd(['docker','create',*common,'--user','0:0','--memory','512m','--memory-swap','512m','--pids-limit','64','--cpus','.5','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=32m,nr_inodes=2048','--mount','type=volume,src='+vol+',dst=/work,volume-nocopy','--mount','type=bind,src='+str(projection/'opt')+',dst=/opt,readonly','--mount','type=bind,src='+str(fixture)+',dst=/harness,readonly',profile['image'],'sleep','60']).decode().strip();cmd(['docker','start',cid]);before=json.loads(cmd(['docker','inspect',cid]))[0]
   node_version=cmd(['docker','exec','--user','1000:1000',cid,'/opt/node/bin/node','--version']).decode().strip()
   argv=['/opt/node/bin/node','--import','/opt/lore/research/repos/pi/node_modules/tsx/dist/loader.mjs','/harness/probe-public.mts',mode,'/work'];body={'AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'User':'1000:1000','WorkingDir':'/work','Env':['PATH=/opt/node/bin:/usr/local/bin:/usr/bin:/bin','HOME=/work','LANG=C.UTF-8','TSX_TSCONFIG_PATH=/harness/tsconfig.json'],'Cmd':argv};eid=api('POST','/containers/'+cid+'/exec',body)['Id'];api('POST','/exec/'+eid+'/start',{'Detach':True,'Tty':False});deadline=time.monotonic()+30
   while True:
    execution=api('GET','/exec/'+eid+'/json')
    if not execution['Running']:break
    if time.monotonic()>deadline:raise TimeoutError('bounded Node/Pi load')
    time.sleep(.05)
   cmd(['docker','pause',cid]);helper=cmd(['docker','create',*common,'--user','1000:1000','--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','.25','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=1m,nr_inodes=64','--mount','type=volume,src='+vol+',dst=/work,readonly,volume-nocopy',profile['image'],'tar','--format=pax','--pax-option=delete=atime,delete=ctime','-cpf','-','-C','/work','.']).decode().strip();helper_before=json.loads(cmd(['docker','inspect',helper]))[0];raw=cmd(['docker','start','-a',helper]);(out/(mode+'.original.tar')).write_bytes(raw);cmd(['docker','rm',helper]);helper=None
   with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as t:files={m.name.removeprefix('./'):t.extractfile(m).read() for m in t if m.isfile()}
   provider=len(files.get('provider.jsonl',b'').splitlines());effects=len(files.get('effects.jsonl',b'').splitlines());sessions=[b for n,b in files.items() if n.startswith('sessions/') and n.endswith('.jsonl')]
   checks={'actual_node_version':node_version=='v24.21.0','original_argv':execution['ProcessConfig']['entrypoint']==argv[0] and execution['ProcessConfig']['arguments']==argv[1:],'actual_exit':execution['ExitCode']==0,'provider_one':provider==1,'effects_original':effects==(1 if mode=='single' else 0),'original_session':len(sessions)==1 and all(json.loads(line) for line in sessions[0].splitlines()),'actual_memory':before['HostConfig']['Memory']==536870912 and helper_before['HostConfig']['Memory']==134217728,'actual_CPU':before['HostConfig']['NanoCpus']==500000000 and helper_before['HostConfig']['NanoCpus']==250000000,'actual_ro_mounts':all(not m['RW'] for m in before['Mounts'] if m['Type']=='bind')}
   rec['runs'].append({'mode':mode,'container_id':cid,'exec_id':eid,'namespace_claim':'not observed here; full XN05/09 still required','Engine_before':before,'Engine_exec':execution,'helper_before':helper_before,'archive_sha256':hashlib.sha256(raw).hexdigest(),'provider':provider,'effects':effects,'checks':checks});save();cmd(['docker','kill',cid]);cmd(['docker','rm',cid]);cid=None;cmd(['docker','volume','rm',vol]);vol=None
  verify(projection,manifest);rec['status']='PASS_LOAD_PREPARATION_ONLY' if len(rec['runs'])==2 and all(all(x['checks'].values()) for x in rec['runs']) else 'FAIL'
 except Exception as exc:rec['status']='FAIL';rec['error']=repr(exc)
 finally:
  for object_id in [helper,cid]:
   if object_id:
    try:cmd(['docker','rm','-f',object_id])
    except Exception as exc:rec.setdefault('cleanup_errors',[]).append(repr(exc))
  if vol:
   try:cmd(['docker','volume','rm',vol])
   except Exception as exc:rec.setdefault('cleanup_errors',[]).append(repr(exc))
  save()
 print(json.dumps({'status':rec['status'],'error':rec.get('error')}));return 0 if rec['status']=='PASS_LOAD_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
