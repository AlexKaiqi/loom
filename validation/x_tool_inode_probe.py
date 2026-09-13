"""Narrow original-schema1 inode acceptance. Copies existing sources; no new executor API."""
from pathlib import Path
import argparse,base64,copy,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'validation/components/x'),str(ROOT/'validation/components/v'),str(ROOT/'validation/components/r')]
from source_snapshot import capture,unchanged
from source_closure import AUDIT,python_children
from process_group import cleanup as process_cleanup

SCALE=Path('validation/components/x_node_profile/evidence/f-scale-preparation-root-001/actual')
IDS=['large-original128','large-explicit1024','above-explicit1025','small-original128']
SCRIPT=r"""import os,sys,json,hashlib,errno,select
from pathlib import Path
root=Path('/work')
def emit(value):
 raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
 while raw:
  try:count=os.write(1,raw);raw=raw[count:]
  except BlockingIOError:select.select([],[1],[],1)
def inventory():
 rows={}
 for path in [root,*sorted(root.glob('**/*'))]:
  name='.'if path==root else path.relative_to(root).as_posix()
  if path.is_dir():rows[name]=['dir']
  elif path.is_file():raw=path.read_bytes();rows[name]=['file',len(raw),hashlib.sha256(raw).hexdigest()]
  else:raise RuntimeError('unexpected ordinary member')
 return rows
def volume():
 s=os.statvfs(root);return dict(inodes=s.f_files,free=s.f_favail,bytes=s.f_frsize*s.f_blocks)
def expect(line):
 if sys.stdin.buffer.readline()!=line:raise RuntimeError('explicit probe continuation missing')
original=inventory();baseline=volume();emit(dict(phase='original',entries=original,volume=baseline))
fds=[];paths=[];error=None
try:
 while True:
  p=root/('inode-probe-'+str(len(fds)));fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);fds.append(fd);paths.append(p)
except OSError as e:error=e.errno
emit(dict(phase='full',errno=error,open_count=len(fds),volume=volume()))
expect(b'unlink\n')
for path in paths:path.unlink()
emit(dict(phase='deleted-open',open_count=len(fds),volume=volume()))
expect(b'close\n')
for fd in fds:os.close(fd)
emit(dict(phase='cleared',volume=volume(),entries_unchanged=inventory()==original))
"""


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def require(value,message):
 if not value:raise AssertionError(message)
def inspect_source(path):
 rows={}
 for p in [path,*sorted(path.rglob('*'))]:
  name='.'if p==path else p.relative_to(path).as_posix()
  require(not p.is_symlink(),'fixture has an unprepared link')
  rows[name]=['dir']if p.is_dir()else['file',p.stat().st_size,sha(p)]
 return rows


def source_expected(origin,out):
 scale=origin/SCALE;bundle=json.loads((scale/'bundle.json').read_bytes());view=json.loads((scale/'materialized.json').read_bytes());source=Path(view['path'])
 expected=inspect_source(source);original=json.loads((scale/'original-members.json').read_bytes())
 require(len(expected)==578 and sum(x[0]=='file'for x in expected.values())==513,'original full scale missing')
 require(expected=={k:['dir']if x['kind']=='dir'else['file',x['size'],x['sha256']]for k,x in original.items()},'actual original F source differs')
 require(view['version_ref']==bundle['version_ref']and sha(bundle['archive_path'])==bundle['version_ref']['archive_sha256']and sha(bundle['manifest_path'])==bundle['version_ref']['manifest_sha256'],'F actual original reference differs')
 for name,key in [('archive.tar','archive_path'),('manifest.json','manifest_path')]:
  argv=['/usr/bin/git','--git-dir='+str(scale/'configured-control/versions.git'),'cat-file','blob',bundle['version_ref']['git_ref']+':'+name]
  result=subprocess.run(argv,capture_output=True,check=True,env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
  require(result.stdout==Path(bundle[key]).read_bytes(),'original actual Git blob differs');(out/('F-'+name)).write_bytes(result.stdout)
 save(out/'independent-expected.json',{'source':str(source),'bundle':bundle,'entries':expected,'source_files':{str(source/k):x[2]for k,x in expected.items()if x[0]=='file'}})
 return source,expected,bundle


def fixture(out,name,source=None,expected=None,bundle=None):
 from fixtures import create
 params={'domain':'task','cpu':.25,'volume_bytes':6291456,'inode_limit':1025 if name==IDS[2]else 1024 if name==IDS[1]else 128}
 fx=create(out/'fixture',{'initial':{'script':'quota'}},params)
 if source is not None:
  fx['target']=source;authority=fx['authority'];authority.update(target_path=str(source),target_identity={'dev':source.stat().st_dev,'ino':source.stat().st_ino},base_version=hashlib.sha256(json.dumps(bundle['version_ref'],sort_keys=True).encode()).hexdigest())
  fx['request'].update(input_root=str(source),base_version=authority['base_version'],target_selector={'target_id':authority['target_id'],'location':str(source)},input_manifest={'files':[{'path':k,'size':v[1],'sha256':v[2]}for k,v in expected.items()if v[0]=='file']})
 fx['request'].update(script_base64=base64.b64encode(SCRIPT.encode()).decode(),io_mode='duplex')
 save(out/'request.json',fx['request']);save(out/'authority.json',fx['authority']);return fx


def baseline(origin,out):
 # Actual original functions, no Engine creation/inspection and no Docker commands.
 from lore_execution.requests import validate
 from lore_execution.archives import initial
 source,expected,bundle=source_expected(origin,out);rows=[]
 for name in IDS[:3]:
  folder=out/name;folder.mkdir();fx=fixture(folder,name,source,expected,bundle)
  try:validate(fx['request'],fx['authority'],fx['state']);initial(fx['request']);error=None
  except Exception as exc:error={'code':getattr(exc,'code',None),'message':str(exc),'cause_code':getattr(exc.__cause__,'code',None),'cause':str(exc.__cause__)}
  rows.append({'id':name,'actual_error':error})
 save(out/'actual-baseline-errors.json',rows)
 require(rows[0]['actual_error']['code']=='UNSUPPORTED'and rows[0]['actual_error']['cause_code']=='ARCHIVE_LIMIT','old full128 baseline must reject complete input at archive member ceiling')
 require(rows[1]['actual_error']['code']=='INVALID_REQUEST','current old ceiling baseline not observed')
 require(rows[2]['actual_error']['code']=='INVALID_REQUEST','1025 baseline not rejected')
 save(out/'assessment.json',{'status':'EXPECTED_PRECHANGE_CAPACITY_FAILURE','rows':rows,'Docker_calls':0})
 return 0


def exact_cleanup(observer,fx,binding):
 facts=[]
 for kind,key in [('container','container_id'),('volume','volume_id')]:
  names=[binding[key]]if binding.get(key)else []
  # Try the exact known object before discovery can fail; discover only this execution label.
  names.append(None)
  for name in names:
   if name is None:
    argv=['docker','ps','-aq','--no-trunc']if kind=='container'else['docker','volume','ls','-q']
    names.extend(sorted(set(observer.run([*argv,'--filter','label=lore.x.execution_id='+fx['request']['execution_id']])[1].decode().split())-set(x for x in names if x)))
    continue
   argv=['docker','inspect',name]if kind=='container'else['docker','volume','inspect',name]
   rc,raw,err=observer.run(argv,check=False)
   if rc==0:
    original=json.loads(raw)[0];labels=(original.get('Config',{}).get('Labels')if kind=='container'else original.get('Labels'))or{}
    require(labels.get('lore.x.execution_id')in fx['execution_ids'],'foreign cleanup object')
    observer.run(['docker','rm','-f',name]if kind=='container'else['docker','volume','rm',name],check=False)
   rc,raw,err=observer.run(argv,check=False);text=err.decode(errors='replace').lower()
   require(rc!=0 and name.lower()in text and any(x in text for x in ['no such object','no such container','no such volume']),'original object not proven absent')
   facts.append({'kind':kind,'id':name,'absent':True})
 return facts


def physical(origin,out):
 from run import Adapter
 from collector import Collector,ENV
 source,expected,bundle=source_expected(origin,out);rows=[]
 for name in IDS:
  folder=out/name;folder.mkdir();fx=fixture(folder,name,source,expected,bundle)if name!=IDS[3]else fixture(folder,name)
  wanted=expected if name!=IDS[3]else inspect_source(fx['target']);observer=None;adapter=None;binding={};row={'id':name,'status':'FAIL'};rows.append(row)
  try:
   observer=Collector(folder,fx);adapter=Adapter([sys.executable,'-B','-m','lore_execution.adapter'],fx,folder)
   def call(method,**extra):
    result=adapter.call(method,{'request':fx['request'],'authority':fx['authority'],'binding':binding,'state_dir':str(fx['state']),**extra})
    return result
   result=call('execute');binding=result.get('binding',{})
   if name in (IDS[0],IDS[2]):
    require(result.get('error',{}).get('code')==('UNSUPPORTED'if name==IDS[0]else'INVALID_REQUEST'),'exact capacity rejection missing')
    require(observer.ids('container')==observer.baseline_containers and observer.ids('volume')==observer.baseline_volumes,'rejected input created physical objects')
    row.update(status='PASS',rejection=result);continue
   require('error'not in result and binding.get('exec_id'),'legal complete input rejected')
   initial=observer.capture(result,binding,'initial')
   mount=initial['physical']['volume_stat'];require(mount['inodes_total']==fx['request']['budgets']['inodes']and mount['bytes_total']==6291456,'actual private allocation differs')
   original_exec=initial['physical']['exec'];require(original_exec['Running'],'original tool not running')
   buffer=b''
   def frame(phase):
    nonlocal buffer
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
     if b'\n'in buffer:
      line,buffer=buffer.split(b'\n',1);value=json.loads(line);require(value['phase']==phase,'original tool phase order differs');save(folder/(phase+'.json'),value);return value
     result=call('channel_read',stream='stdout',max_bytes=65536);require('error'not in result,'actual channel read failed')
     buffer+=base64.b64decode(result['channel']['data_base64']);require(len(buffer)<=65536,'original stdout exceeds budget')
    raise AssertionError('actual ordinary tool phase absent: '+phase)
   first=frame('original');require(first['entries']==wanted,'complete original file/member/hash set differs')
   full=frame('full');v=observer.volume_bytes(binding['volume_id']);require(full['errno']==28 and full['volume']['free']==0 and v['inodes_free']==0 and full['volume']['inodes']==mount['inodes_total'],'actual inode ENOSPC absent')
   call('channel_write',data_base64=base64.b64encode(b'unlink\n').decode());deleted=frame('deleted-open');v=observer.volume_bytes(binding['volume_id']);require(deleted['open_count']==full['open_count']>0 and v['inodes_free']==0,'unlink released still-open inode debt')
   code="import os,json;from pathlib import Path;p=Path('/proc')/str("+str(original_exec['Pid'])+")/'fd';rows=[]\nfor x in p.iterdir():\n try:\n  t=os.readlink(x)\n  if t.endswith(' (deleted)') and 'inode-probe-'in t:rows.append(t)\n except OSError:pass\nprint(json.dumps(rows))"
   raw,helper=observer.helper(['--user','1000:1000','--pid','host',ENV['image'],'python','-c',code],limit=262144);fds=json.loads(raw);save(folder/'actual-deleted-FDs.json',{'files':fds,'helper':helper});require(len(fds)==full['open_count'],'actual open deleted FDs differ')
   call('channel_write',data_base64=base64.b64encode(b'close\n').decode());cleared=frame('cleared');require(cleared['entries_unchanged']and cleared['volume']==first['volume'],'closing original FDs did not restore inode capacity')
   done=call('await_exit');require('error'not in done and observer.exec_inspect(binding['exec_id'])['ExitCode']==0,'original tool did not naturally complete')
   final_volume=observer.volume_bytes(binding['volume_id']);require(final_volume['inodes_free']==first['volume']['free'],'external post-close inode balance differs')
   cp=call('checkpoint',checkpoint_id='original-final',purpose='checkpoint');require('error'not in cp,'actual final checkpoint failed');binding=cp['binding'];prepared=observer.capture(cp,binding,'prepared')
   final={k:['dir']if v['type']=='directory'else['file',v['byte_length'],v['sha256']]for k,v in prepared['archive']['files'].items()};require(final==wanted,'actual final archive omitted original inputs or leaked temporary fills')
   sealed=call('seal',receipt=cp['artifacts']['checkpoint']);require('error'not in sealed,'actual original seal failed');stopped=observer.capture(sealed,binding,'stopped');require(not stopped['physical']['namespace_pids']and not stopped['physical']['container_running'],'old namespace survives')
   released=call('release');require('error'not in released,'original physical resource release failed');row.update(status='PASS',inodes=mount['inodes_total'],original_members=len(wanted),original_files=sum(x[0]=='file'for x in wanted.values()))
  except Exception as exc:row['error']=repr(exc)
  finally:
   if adapter:adapter.stop()
   if observer:
    try:row['cleanup']=exact_cleanup(observer,fx,binding)
    except Exception as exc:row.update(status='FAIL',cleanup_error=repr(exc))
   save(out/'assessment.json',{'status':'PASS'if len(rows)==4 and all(x['status']=='PASS'for x in rows)else'FAIL','rows':rows})
 require(inspect_source(source)==expected,'protected original F materialization changed')
 return 0 if all(x['status']=='PASS'for x in rows)else 1


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--baseline-only',action='store_true');ap.add_argument('--worker',action='store_true');ap.add_argument('--origin',type=Path);a=ap.parse_args()
 require(a.batch.replace('-','').isalnum(),'fresh batch name required')
 if a.worker:
  out=ROOT.parent/'actual';out.mkdir();return baseline(a.origin,out)if a.baseline_only else physical(a.origin,out)
 out=ROOT/'validation/tool-inode-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);ws=out/'workspace';source=capture('lore_execution.adapter',[ROOT],ws);require(source is not None,'candidate missing')
 paths=[Path(__file__).resolve(),*list((ROOT/'validation/components/x').glob('*.py')),*list((ROOT/'design/g3/x').glob('*.json')),ROOT/'design/g3/x-large-tool-inodes.md',ROOT/'research/docker-linux/seccomp.json',ROOT/'validation/components/v/source_snapshot.py',ROOT/'validation/components/r/process_group.py']
 paths += [p for p in (ROOT/'lore_execution').rglob('*')if p.is_file()and p.suffix!='.py'and '__pycache__'not in p.parts]
 bindings=[]
 for p in paths:
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());bindings.append({'original':str(p),'copy':str(q),'sha256':sha(q)})
 audit=ws/'sitecustomize.py';audit.write_text(AUDIT);generated={str(audit):sha(audit)}
 argv=[sys.executable,'-B',str(ws/'validation/x_tool_inode_probe.py'),'--batch',a.batch,'--worker','--origin',str(ROOT)]+(['--baseline-only']if a.baseline_only else[])
 save(out/'before.json',{'candidate':source,'inputs':bindings,'generated':generated,'argv':argv,'expected_scenarios':IDS,'budget':'one tool+one serial existing observer helper, 256MiB; original byte/CPU limits unchanged'})
 with (out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
  process=subprocess.Popen(argv,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1','LORE_X_REQUIRE_SOURCE_AUDIT':'1'},stdout=stdout,stderr=stderr,start_new_session=True)
  try:code=process.wait(timeout=30 if a.baseline_only else 480)
  except subprocess.TimeoutExpired:code=124
  finally:clean=process_cleanup(process.pid)
 events=[json.loads(line)for p in (out/'imports').glob('*.jsonl')for line in p.read_text().splitlines()];known={**source['executed_snapshot'],**generated,**{x['copy']:x['sha256']for x in bindings}}
 executions=[x for x in events if x['kind']=='exec'];bound=bool(executions)and all(known.get(x['filename'])==x['sha256']for x in executions)
 stable=unchanged(source)and all(sha(x[k])==x['sha256']for x in bindings for k in ['original','copy'])and all(sha(p)==h for p,h in generated.items());children=python_children(events,ws)
 adapters=[json.loads(line)for p in (out/'actual').rglob('adapter-processes.jsonl')for line in p.read_text().splitlines()];adapter_cleanup=[{'pid':x['pid'],**process_cleanup(x['pid'])}for x in adapters]
 actual_pids={x['pid']for x in executions if x['filename']in source['executed_snapshot']};all_adapters=all(x['pid']in actual_pids for x in adapters)and(bool(adapters)or a.baseline_only)
 result={'status':'PASS'if code==0 and bound and stable and children['pass']and all_adapters and not clean['before']and all(not x['before']for x in adapter_cleanup)else'FAIL','scope':'PRECHANGE_BASELINE_NO_DOCKER'if a.baseline_only else'ORIGINAL_SCHEMA1_TOOL_INODE_EXTENSION_ONLY','exit_code':code,'source_unchanged':stable,'observed_source_bound':bound,'python_child_closure':children,'every_adapter_executed_copy':all_adapters,'cleanup':clean,'adapter_cleanup':adapter_cleanup,'actual':str(out/'actual/assessment.json')};save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS'else 1


if __name__=='__main__':raise SystemExit(main())
