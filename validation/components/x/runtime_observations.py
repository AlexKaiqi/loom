"""External bounded readiness and raw cgroup facts; no candidate status oracle."""
from pathlib import Path
import base64,hashlib,json,os,time
from oracle import EvidenceError,at

def memory_limit_facts(samples):
 if not isinstance(samples,list) or not samples:raise EvidenceError('missing actual memory samples')
 observations=[]
 for index,row in enumerate(samples):
  if not isinstance(row,dict):raise EvidenceError('invalid cgroup sample')
  for key,raw in row.items():
   if key.endswith('memory.failcnt'):
    text=raw.strip() if isinstance(raw,str) else ''
    if not text.isdecimal():raise EvidenceError('invalid actual failcnt')
    observations.append({'sample':index,'key':key,'counter':'failcnt','count':int(text),'raw':raw})
   elif key.endswith(('memory.oom_control','memory.events')):
    try:
     pairs=[line.split() for line in raw.splitlines()];counts={k:int(v) for k,v in pairs}
     if len(counts)!=len(pairs) or any(v<0 for v in counts.values()):raise ValueError()
    except (AttributeError,TypeError,ValueError):raise EvidenceError('invalid actual memory counter file')
    if 'oom_kill' in counts:observations.append({'sample':index,'key':key,'counter':'oom_kill','count':counts['oom_kill'],'raw':raw})
 if not observations:raise EvidenceError('missing actual memory limit counter')
 return {'observed':any(x['count']>0 for x in observations),'source':'original fresh execution cgroup files','observations':observations}

def ready_value(line,marker):
 try:obj=json.loads(line)
 except (ValueError,UnicodeError):raise EvidenceError('invalid fixture ready JSON')
 if not isinstance(obj,dict) or set(obj)!={'lore_fixture_ready','value'} or obj['lore_fixture_ready']!=marker or type(obj['value']) is not int or obj['value']<0:raise EvidenceError('wrong fixture ready frame')
 return obj['value']

def source_event(log,pid,entry):
 if not log.exists():return None
 raw=log.read_bytes();lines=raw.split(b'\n')[:-1]
 for line in lines:
  item=json.loads(line)
  if item.get('kind')=='exec' and item.get('pid')==pid and item.get('filename')==str(entry):
   if item.get('sha256')!=hashlib.sha256(entry.read_bytes()).hexdigest():raise EvidenceError('started candidate source hash differs')
   return item
 return None

def await_source_start(process,argv,root,out):
 if os.environ.get('LORE_X_REQUIRE_SOURCE_AUDIT')!='1':return
 if '-m' not in argv:raise EvidenceError('copied candidate module required by frozen adapter')
 module=argv[argv.index('-m')+1];entry=root.joinpath(*module.split('.')).with_suffix('.py');log=root.parent/'imports'/(str(process.pid)+'.jsonl');end=time.monotonic()+3
 try:
  while time.monotonic()<end:
   event=source_event(log,process.pid,entry)
   if event is not None:
    with (out/'adapter-source-starts.jsonl').open('a') as stream:stream.write(json.dumps({'pid':process.pid,'entry':str(entry),'event':event})+'\n');stream.flush();os.fsync(stream.fileno())
    return
   if process.poll() is not None:raise EvidenceError('candidate exited before copied source execution')
   time.sleep(.01)
  raise EvidenceError('bounded copied-source start evidence absent')
 except Exception:raise

def await_fixture_stdio(adapter,observer,fx,binding,arg,frames,deadline):
 marker=arg['marker'];threshold=at(frames,arg['greater_than_ref']) if 'greater_than_ref' in arg else arg['minimum']-1
 if type(threshold) is not int or threshold<0:raise EvidenceError('invalid original readiness threshold')
 until=min(deadline,time.monotonic()+3);buffer=fx.get('ready_buffer',b'');total=0;ready=None
 while ready is None:
  while b'\n' in buffer:
   line,buffer=buffer.split(b'\n',1);value=ready_value(line,marker)
   if value>threshold:ready=value;break
  if ready is not None:break
  remaining=until-time.monotonic()
  if remaining<=0:raise EvidenceError('bounded actual fixture readiness absent')
  response=adapter.call('channel_read',{'request':fx['request'],'authority':fx['authority'],'binding':binding,'state_dir':str(fx['state']),'stream':'stdout','max_bytes':4096,'test_context':{'cache_dir':str(fx['cache'])}},timeout=remaining)
  chunk=base64.b64decode(response['channel']['data_base64'],validate=True);buffer+=chunk;total+=len(chunk)
  if total>4096 or len(buffer)>4096:raise EvidenceError('fixture readiness raw cap')
  if not chunk and response['channel']['eof']:raise EvidenceError('fixture exited before readiness')
 fx['ready_buffer']=buffer;execution=observer.exec_inspect(binding['exec_id'])
 if not execution or execution['ContainerID']!=binding['container_id'] or not execution['Running']:raise EvidenceError('checkpoint readiness must be active original execution')
 return {'marker':marker,'value':ready,'threshold':threshold,'Engine_exec':execution,'buffered_bytes':len(buffer)}
