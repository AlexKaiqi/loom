"""G2 finite Docker/Linux mechanism probe; no production adapter."""
from pathlib import Path
import subprocess,json,os,sys,time,hashlib,traceback,datetime
B=Path(__file__).resolve().parent
IMAGE=json.loads((B/'protocol.json').read_text())['image']
def main(batch):
 out=B/'evidence'/batch;out.mkdir(parents=True,exist_ok=False)
 fixture=out/'fixture';fixture.mkdir();control=fixture/'control';control.mkdir();(control/'canary').write_text('CONTROL-CANARY')
 result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'observations':{},'checks':[],'errors':[],'inputs':{n:hashlib.sha256((B/n).read_bytes()).hexdigest() for n in ['protocol.json','protocol-amendment-002.json','seccomp.json','worker.py','experiment.py']}}
 result['active_protocol']='protocol.json plus prospective protocol-amendment-002.json';result['concurrency_scope']={'maximum_containers':2,'combined_memory_max_bytes':268435456,'only_overlap':'K3 writer with trusted read-only host-PID observer'}
 created=[]
 def cmd(args):
  r=subprocess.run(args,capture_output=True,text=True,timeout=45);i=len(result['commands']);(out/f'{i:03}.stdout').write_text(r.stdout);(out/f'{i:03}.stderr').write_text(r.stderr)
  result['commands'].append({'argv':args,'exit_code':r.returncode,'stdout':f'{i:03}.stdout','stderr':f'{i:03}.stderr'})
  return r
 def required(args):
  r=cmd(args)
  if r.returncode:raise RuntimeError(r.stderr)
  return r.stdout.strip()
 def check(name,value):
  result['checks'].append({'id':name,'passed':bool(value)})
  if not value:raise AssertionError(name)
 def create(name,mode,extra=None,script=None):
  work=fixture/name;work.mkdir();(work/'marker').write_text('LINUX-EXT4-MARKER');(work/'object').write_text('ORIGINAL\n');(work/'alias').symlink_to(control/'canary')
  args=['docker','create','--label','lore.g2.docker='+batch,'--name','lore-g2-'+batch+'-'+name,'--user','1000:1000','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--security-opt','seccomp='+str(B/'seccomp.json'),'--network','none','--memory','128m','--memory-swap','128m','--pids-limit','32','--cpus','0.5','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777','--workdir','/work','--mount','type=bind,source='+str(work)+',target=/work']
  if extra:args+=extra
  args += [IMAGE,'python','-u','-c',script if script is not None else (B/'worker.py').read_text(),mode,str(control/'canary')]
  cid=required(args);created.append(cid);required(['docker','start',cid]);return cid,work
 def inspect(cid):return json.loads(required(['docker','inspect',cid]))[0]
 def finish(cid):
  rc=required(['docker','wait',cid]);state=inspect(cid);logs=required(['docker','logs',cid]);return {'wait':rc,'state':state,'logs':logs}
 def ready(path):
  for _ in range(400):
   if path.exists():
    try:return json.loads(path.read_text())
    except ValueError:pass
   time.sleep(.01)
  raise TimeoutError(str(path))
 def host_observer(name,namespace):
  script="import pathlib,os,json; target="+repr(namespace)+"; found=[]\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit():continue\n try:\n  if os.readlink(p/'ns/pid')==target:found.append(int(p.name))\n except OSError:pass\nprint(json.dumps({'namespace':target,'actual_pids':found}))"
  cid,w=create(name,'observe',['--pid','host'],script);v=finish(cid);v['data']=json.loads(v['logs']);return v
 try:
  result['engine']=json.loads(required(['docker','version','--format','{{json .}}']))
  cid,work=create('matrix','matrix');m=finish(cid);result['observations']['matrix']=m;d=json.loads(m['logs'])
  check('K1_ext4_bind_identity',d['marker']=='LINUX-EXT4-MARKER' and (work/'object').read_text()=='ORIGINAL\nWRITE\n')
  check('K2_enforced_domain',d['uid']==1000 and d['gid']==1000 and all(d['writes'][n]!='written' for n in ['/work/alias','/root/new','/other/object','/etc/hostname']) and all('errno' in v for v in d['reads'].values()) and (control/'canary').read_text()=='CONTROL-CANARY')
  check('K2_no_fd_network_capabilities',all(d['writes']['fd'+str(fd)]==9 for fd in [3,4,5]) and d['network'].get('errno')==101 and 'CapEff:\t0000000000000000' in d['status'])
  check('K5_explicit_seccomp', 'Seccomp:\t2' in d['status'] and 'NoNewPrivs:\t1' in d['status'])
  check('K4_actual_cgroup_limits',int(d['limits']['memory'])==128*1024*1024 and int(d['limits']['pids'])==32 and int(d['limits']['cpu_quota'])/int(d['limits']['cpu_period'])==.5)
  for name,kill_first in [('negative',False),('stopped',True)]:
   cid,work=create(name,'writer');rr=ready(work/'ready.json');obs={'ready':rr,'before':inspect(cid),'top_before':required(['docker','top',cid,'-eo','pid,ppid,pgid,sid,uid'])};result['observations'][name]=obs
   if kill_first:
    obs['os_before']=host_observer('observe-before',rr['namespace']);check('K3_actual_old_processes_exist',len(obs['os_before']['data']['actual_pids'])>=2)
    required(['docker','kill',cid]);obs['stopped']=finish(cid);obs['os_after']=host_observer('observe-after',rr['namespace']);check('K3_actual_namespace_processes_absent',obs['os_after']['data']['actual_pids']==[])
    (work/'trigger').write_text('go');time.sleep(.8)
   else:
    (work/'trigger').write_text('go');obs['done']=ready(work/'done');required(['docker','kill',cid]);obs['stopped']=finish(cid)
   obs['actual_object']=(work/'object').read_text();check('K3_'+name+'_object',obs['actual_object']==('ORIGINAL\n' if kill_first else 'ORIGINAL\nLATE-FD\n'))
  cid,work=create('fork','fork');v=finish(cid);result['observations']['fork']=v;d=json.loads(v['logs']);check('K4_actual_pids_enforcement',d['fork_error']==11 and 0<d['children']<48)
  cid,work=create('memory','memory');v=finish(cid);result['observations']['memory']=v;check('K4_actual_memory_enforcement',v['state']['State']['OOMKilled'] and v['state']['State']['ExitCode']==137 and 'before-allocation' in v['logs'] and 'allocated' not in v['logs'])
 except Exception as e:result['errors'].append({'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
 finally:
  for cid in created:
   r=cmd(['docker','rm','--force',cid])
   if r.returncode:result['errors'].append({'cleanup_failed':cid,'stderr':r.stderr})
  result['status']='PASS' if not result['errors'] else 'FAIL';(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'checks':result['checks'],'errors':result['errors']}));return 0 if not result['errors'] else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
