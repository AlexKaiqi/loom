"""Finite real-process regressions for the pure Node/Pi module, not S/XN acceptance."""
import argparse,copy,hashlib,json,os,pathlib,select,shutil,signal,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
NODE='/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node'
PI=ROOT/'research/derived/pi-71dca871-compaction-enabled-v1'
sys.path.insert(0,str(ROOT/'validation/components/s'))
from oracle import pi_jsonl,clipped_context_objects,native_tool_text
from context_fixtures import long_log,write_materials

def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('batch');args=ap.parse_args();out=ROOT/'lore_session/node/evidence'/args.batch;out.mkdir(parents=True,exist_ok=False)
 inputs=[]
 for directory in ('lore_session/node','harnesses/minimal'):
  for p in (ROOT/directory).iterdir():
   if p.is_file():
    q=out/'source'/directory/p.name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);inputs.append({'path':str(p),'copy':str(q),'sha256':sha(p.read_bytes())})
 source=out/'source';acceptance=ROOT/'research/patches/pi-compaction-enabled-v1/acceptance.json'
 save(out/'inputs.json',{'files':inputs,'Pi_acceptance':{'path':str(acceptance),'sha256':sha(acceptance.read_bytes())},'actual_Pi_root':str(PI),'scope':'Pure Node module; provider/tool callbacks are bounded fixtures, no HTTP/Engine','limits':{'node_processes':32,'per_process_seconds':10}})
 config=json.loads((ROOT/'research/pi/tsconfig.json').read_text());config['compilerOptions']['baseUrl']=str(PI);save(out/'tsconfig.json',config)
 env={'PATH':str(pathlib.Path(NODE).parent)+':/usr/bin:/bin','LANG':'C.UTF-8','TSX_TSCONFIG_PATH':str(out/'tsconfig.json')}
 cases=json.loads((ROOT/'design/g3/provider/cases.json').read_text())['cases'];messages={c['id'].split('-')[0]:c['expected']['normalized']['message'] for c in cases if 'normalized'in c.get('expected',{})}
 checks=[];runs=[]
 def setup(name):
  base=out/name;base.mkdir();work=base/'work';work.mkdir();inp=base/'input';inp.mkdir();surface=inp/'surface';surface.mkdir();workspace=base/'workspace';workspace.mkdir()
  (surface/'template.md').write_text('GOAL_MARKER_雪\n{{notes.md}}\n');(surface/'notes.md').write_text('NOTES_MARKER NOTES_V1\n');(inp/'events.jsonl').write_text('{"type":"EVENT_MARKER"}\n');(inp/'feedback.txt').write_text('SAVED_TOOL_MARKER\n')
  model={'id':'gpt-5.6-terra','name':'keyless finite callback','api':'lore-proxy-completions','provider':'lore-authorized-proxy','baseUrl':'http://localhost:0','reasoning':False,'input':['text'],'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0},'contextWindow':131072,'maxTokens':2048}
  c={'schema':'lore.s.node/1','pi_root':str(PI),'work_root':str(work),'harness_entry':str(source/'harnesses/minimal/index.mts'),'harness_ref':{'owner':'F','id':'h1'},'model':model,'session_scope':{'namespace':'node-module','surface_id':'surface','session_id':name,'session_generation':1},'input':{'ref':{'owner':'F','id':'in1'},'paths':{'surface':str(surface),'events':str(inp/'events.jsonl'),'feedback':str(inp/'feedback.txt'),'runtime':'/input/surface','workspace':str(workspace)}},'capability_ref':{'owner':'R','id':'cap1'}}
  request={'protocol':'lore.s/1','session_ref':{'owner':'S',**c['session_scope']},'operation_id':'op-1','harness_ref':c['harness_ref'],'input_ref':c['input']['ref'],'source_result_ref':None,'capability_ref':c['capability_ref']}
  return base,c,request
 def original(c):
  meta=json.loads((pathlib.Path(c['work_root'])/'metadata.json').read_text());return pathlib.Path(meta['path']).read_bytes()
 def invoke(base,c,request,action,message=None,cut=None):
  folder=base/('invoke-'+str(len(runs)));folder.mkdir();save(folder/'config.json',c);sent={**request,'action':action};save(folder/'request.json',sent)
  argv=[NODE,'--import',str(PI/'node_modules/tsx/dist/loader.mjs'),str(source/'lore_session/node/entry.mts'),'--config',str(folder/'config.json')]
  proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=c['work_root'],start_new_session=True)
  proc.stdin.write((json.dumps(sent)+'\n').encode());proc.stdin.flush();frames=[];replies=[];result=None;deadline=time.monotonic()+10
  try:
   while True:
    if time.monotonic()>deadline:raise RuntimeError('Node frame timeout')
    if not select.select([proc.stdout],[],[],max(0,deadline-time.monotonic()))[0]:raise RuntimeError('Node no frame')
    line=proc.stdout.readline()
    if not line:raise RuntimeError('Node EOF before result')
    frame=json.loads(line);frames.append(frame)
    if cut==frame.get('type'):os.killpg(proc.pid,signal.SIGKILL);break
    if frame['type']=='result':result=frame;proc.stdin.close();break
    if frame['type']=='provider.request':
     if sum(f['type']=='provider.request'for f in frames)>1:raise RuntimeError('unexpected second provider')
     reply={'type':'provider.reply','effect_id':frame['effect_id'],'response_entry_id':frame['response_entry_id'],'message':copy.deepcopy(message)}
    elif frame['type']=='tool.request':
     raw='ORIGINAL_TOOL_RESULT_雪\n'.encode();(folder/'actual-tool-stdout').write_bytes(raw)
     reply={'type':'tool.reply','effect_id':frame['effect_id'],'invocation_id':frame['invocation_id'],'result_ref':{'owner':'controlled-X-fixture','execution_id':frame['effect_id']},'stdout':{'data_b64':__import__('base64').b64encode(raw).decode(),'bytes':len(raw),'sha256':sha(raw)}}
    elif frame['type']in ('provider.query','effect.query'):reply={'type':'effect.query_reply','effect_id':frame['effect_id'],'result':{'status':'UNKNOWN'}}
    else:raise RuntimeError('unexpected frame '+frame['type'])
    replies.append(reply);proc.stdin.write((json.dumps(reply)+'\n').encode());proc.stdin.flush()
   proc.wait(timeout=3)
  finally:
   if proc.poll()is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=3)
   stderr=proc.stderr.read();(folder/'stderr').write_bytes(stderr);record={'pid':proc.pid,'argv':argv,'exit':proc.returncode,'frames':frames,'replies':replies,'result':result};save(folder/'actual.json',record);runs.append(record)
   if (pathlib.Path(c['work_root'])/'metadata.json').exists():
    try:(folder/'original.jsonl').write_bytes(original(c))
    except OSError:pass
  return result,frames
 def check(name,condition):checks.append({'id':name,'pass':bool(condition)})
 base,c,r=setup('ordinary');res,frames=invoke(base,c,r,'accept');check('accept_zero_effects',res and res.get('boundary_kind')=='accepted'and len(frames)==1)
 raw=original(c);check('original_complete_binding',pi_jsonl(raw)['values']['lore.s.binding']['op-1']['input_ref']==r['input_ref'])
 for action in ('query','accept'):
  res,frames=invoke(base,c,r,action);check(action+'_exact_readonly',raw==original(c)and len(frames)==1 and not res.get('error'))
 for field in ('harness_ref','input_ref','source_result_ref','capability_ref'):
  rc=copy.deepcopy(r);cc=copy.deepcopy(c);rc[field]={'owner':'controlled','id':'changed'}
  if field=='input_ref':cc['input']['ref']=rc[field]
  elif field in cc:cc[field]=rc[field]
  res,_=invoke(base,cc,rc,'accept');check('conflict_'+field,res.get('error',{}).get('code')=='conflict'and raw==original(c))
 res,frames=invoke(base,c,r,'drive',messages['PW01']);check('ordinary_original_answer',res.get('boundary_kind')=='answer_saved'and pi_jsonl(original(c))['assistant_stop_reasons']==['stop'])
 saved_ref=res['operation_result_ref'];check('proposal_original_locator',res['decision_proposal']['source_result_ref']==saved_ref and sha(original(c)[:saved_ref['session_bytes']])==saved_ref['session_sha256'])
 raw=original(c);res,frames=invoke(base,c,r,'query');check('saved_query_zero_writes_calls',raw==original(c)and len(frames)==1);check('saved_query_identical_locator',res['operation_result_ref']==saved_ref and res['decision_proposal']['source_result_ref']==saved_ref)
 for name,key in [('native','PW02'),('length_text','PW04'),('length_native','PW05'),('multi','PW02')]:
  base,c,r=setup(name)
  if name=='native':write_materials(pathlib.Path(c['input']['paths']['workspace']))
  invoke(base,c,r,'accept');message=copy.deepcopy(messages[key])
  if name=='multi':second=copy.deepcopy(message['content'][0]);second['id']='second';message['content'].append(second)
  res,frames=invoke(base,c,r,'drive',message);parsed=pi_jsonl(original(c));saved=[e['message']for e in parsed['entries']if e.get('message',{}).get('role')=='assistant'];tools=[f for f in frames if f['type']=='tool.request']
  check(name+'_original_message',saved==[message]);check(name+'_bounded_callbacks',sum(f['type']=='provider.request'for f in frames)==1 and len(tools)==(1 if name=='native'else 0))
  check(name+'_boundary',res.get('boundary_kind')==('tool_feedback_saved'if name=='native'else 'blocked_invalid'))
  if name=='native':
   check('native_actual_stdout_in_Pi','ORIGINAL_TOOL_RESULT_雪' in parsed['native_tool_text'])
   first=next(f['payload']for f in frames if f['type']=='provider.request')
   check('lazy_materials_not_preexpanded',not any(x in json.dumps(first)for x in ('UNSELECTED_TREE_PATH','UNSELECTED_FILE_BODY','UNSELECTED_DIFF_BODY')))
   old_ref=res['operation_result_ref'];r['operation_id']='op-next';r['source_result_ref']=old_ref;c['input']['ref']={'owner':'F','id':'in2'};r['input_ref']=c['input']['ref']
   (pathlib.Path(c['input']['paths']['surface'])/'notes.md').write_text('NOTES_MARKER NOTES_V2\n')
   invoke(base,c,r,'accept');res,frames=invoke(base,c,r,'drive',messages['PW01'])
   payload=next(f['payload']for f in frames if f['type']=='provider.request')
   check('next_original_tool_feedback', 'ORIGINAL_TOOL_RESULT_雪' in native_tool_text(payload['messages']))
   check('next_input_projected','NOTES_V2' in json.dumps(payload))
 base,c,r=setup('unknown');invoke(base,c,r,'accept');_,cut_frames=invoke(base,c,r,'drive',messages['PW01'],cut='provider.request');pending_id=cut_frames[-1]['effect_id'];raw=original(c);c['session_scope']={k:c['session_scope'][k]for k in reversed(c['session_scope'])}
 for action in ('query','drive'):
  res,frames=invoke(base,c,r,action);check('pending_'+action+'_no_replay',res.get('boundary_kind')=='paused_unknown'and [f['type']for f in frames]==['provider.query','result']and frames[0]['effect_id']==pending_id and raw==original(c))
 meta=json.loads((pathlib.Path(c['work_root'])/'metadata.json').read_text());path=pathlib.Path(meta['path']);path.write_bytes(raw+b'{"torn":');broken=path.read_bytes();res,frames=invoke(base,c,r,'query');check('torn_preopen_unchanged',res.get('error',{}).get('code')=='session_corrupt'and path.read_bytes()==broken and len(frames)==1)
 base,c,r=setup('clip');raw=long_log();log=base/'input/original-log';log.write_bytes(raw);ref={'owner':'F','id':'fixed-log','sha256':sha(raw)}
 c['input']['original_refs']={'log':{'source_ref':ref,'path':str(log),'read_path':'/input/originals/log','bytes':len(raw),'sha256':sha(raw)}}
 invoke(base,c,r,'accept');res,frames=invoke(base,c,r,'drive',messages['PW01']);payload=next(f['payload']for f in frames if f['type']=='provider.request');clips=clipped_context_objects(payload)
 check('clip_actual_ranges_sources',len(clips)==1 and clips[0]['retained_ranges']==[[0,78],[len(raw)-44,len(raw)]] and clips[0]['fragments']==[raw[:78].decode(),raw[-44:].decode()] and clips[0]['source_ref']==ref and clips[0]['source_sha256']==sha(raw))
 rr={**r,'read_ref':ref};res,_=invoke(base,c,rr,'export_read');check('complete_read_original_bytes',pathlib.Path(res['read_result_ref']['path']).read_bytes()==raw)
 base,c,r=setup('unknown-tool');invoke(base,c,r,'accept');invoke(base,c,r,'drive',messages['PW02'],cut='tool.request');raw=original(c)
 res,frames=invoke(base,c,r,'query');check('pending_tool_original_query_no_replay',res.get('boundary_kind')=='paused_unknown'and [f['type']for f in frames]==['effect.query','result']and original(c)==raw)
 meta=json.loads((pathlib.Path(c['work_root'])/'metadata.json').read_text());path=pathlib.Path(meta['path']);path.write_bytes(raw+b'{"bad":"'+bytes([255])+b'"}\n');broken=path.read_bytes();res,frames=invoke(base,c,r,'query');check('bad_utf8_preopen_unchanged',res.get('error',{}).get('code')=='session_corrupt'and path.read_bytes()==broken and len(frames)==1)
 metadata_path=pathlib.Path(c['work_root'])/'metadata.json';metadata_path.rename(metadata_path.with_name('preserved-metadata.json'));res,frames=invoke(base,c,r,'accept');check('missing_metadata_no_new_session',res.get('error',{}).get('code')=='session_corrupt'and path.read_bytes()==broken)
 unchanged=all(sha(pathlib.Path(x['path']).read_bytes())==x['sha256'] for x in inputs)
 report={'status':'PASS_PURE_NODE_MODULE_ONLY'if checks and all(c['pass']for c in checks)and unchanged else 'FAIL','checks':checks,'processes':len(runs),'source_unchanged':unchanged,'scope':'No X/F/R/S owner or system acceptance; real Pi with fixture provider/tool replies'};save(out/'assessment.json',report);print(json.dumps({'status':report['status'],'checks':len(checks),'processes':len(runs),'failed':[x['id']for x in checks if not x['pass']]}));return 0 if report['status'].startswith('PASS')else 1
if __name__=='__main__':raise SystemExit(main())
