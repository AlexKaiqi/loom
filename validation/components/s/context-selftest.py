"""Actual ordinary fixture command plus explicit oracle calibration, never S PASS."""
from pathlib import Path
import copy,hashlib,json,subprocess,sys,time
from context_fixtures import write_materials,retrieval_script,long_log
from oracle import evaluate_case,InvalidEvidence,pi_jsonl
R=Path(__file__).resolve().parent;ROOT=R.parents[2]
out=R/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
protocol=json.loads((ROOT/'design/g3/s/context-supplement-004.json').read_text())
spec=json.loads((ROOT/'design/g3/s/cases.json').read_text());cases={c['id']:c for c in spec['cases']};checks=[]
for p in [R/'context_fixtures.py',R/'oracle.py',R/'context-selftest.py',ROOT/'design/g3/s/context-supplement-004.json',ROOT/'design/g3/s/cases.json']:(out/p.name).write_bytes(p.read_bytes())
def digest(by):return hashlib.sha256(by).hexdigest()
def art(name,by):
    p=out/name;p.write_bytes(by);return {'path':name,'sha256':digest(by),'origin':'trusted_external_collector'}
def journal(name,rows):return art(name,(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)).encode())
def observe(name,case,evidence,wanted):
    try:result=evaluate_case(case,evidence,out);status=result['status']
    except InvalidEvidence as e:result={'error':str(e)};status='INVALID'
    checks.append({'name':name,'scope':'EXPLICIT_ORACLE_CALIBRATION_ONLY','expected':wanted,'observed':status,'pass':status==wanted});(out/(name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
w=out/'workspace';w.mkdir();selected,diff=write_materials(w)
input_ref={'fixture_only':True,'resource_id':'immutable-input-test','version':'fixed-capture'}
script=retrieval_script(input_ref);(out/'actual-script.sh').write_text(script)
started=time.monotonic();p=subprocess.run(['/bin/sh','-c',script],cwd=w,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,timeout=10)
(out/'command.json').write_text(json.dumps({'argv':['/bin/sh','-c',script],'cwd':str(w),'exit':p.returncode,'elapsed':time.monotonic()-started},ensure_ascii=False,indent=2)+'\n');(out/'actual.stdout').write_bytes(p.stdout);(out/'actual.stderr').write_bytes(p.stderr)
actual=json.loads(p.stdout);files=[f for f in w.rglob('*') if f.is_file()];tree=[{'path':str(f.relative_to(w)),'bytes':f.stat().st_size,'sha256':digest(f.read_bytes())} for f in files];(out/'material-manifest.json').write_text(json.dumps(tree,ensure_ascii=False,indent=2)+'\n')
expected=protocol['fixtures']['large_materials'];ok=p.returncode==0 and len(files)==513 and sum(f.stat().st_size for f in files)<protocol['limits']['fixture_bytes_max'] and len(list(w.rglob('*')))<protocol['limits']['fixture_inodes_max'] and len(p.stdout)<protocol['limits']['retrieval_stdout_bytes_max'] and actual['file_fragment'].strip()==expected['selected_text'] and actual['diff_fragment'].strip()==expected['selected_diff_line']
for i,file in enumerate([selected,diff]):ok=ok and actual['sources'][i]=={'path':str(file.relative_to(w)),'bytes':file.stat().st_size,'sha256':digest(file.read_bytes()),'input_ref':input_ref}
checks.append({'name':'actual_ordinary_glob_read_hash_fixture','scope':'REAL_LINUX_FIXTURE_COMMAND_ONLY','pass':ok})
# The following provider records are explicitly test specimens, not S output.
firstcase=copy.deepcopy(cases['S-027']);firstcase['assertions']=[a for a in firstcase['assertions'] if a['source']=='journal:provider_first'];firstcase['evidence_required']=['journal:provider_first']
text='GOAL_MARKER_雪 NOTES_MARKER EVENT_MARKER SAVED_TOOL_MARKER /workspace'
def first_ev(extra):return {'journal:provider_first':journal('first-'+str(len(checks))+'.jsonl',[{'type':'provider_request','payload':{'messages':[{'role':'user','content':[{'type':'text','text':extra}]}]}}])}
observe('initial_compact_context',firstcase,first_ev(text),'PASS')
observe('eager_directory_listing',firstcase,first_ev(text+'\n'+'\n'.join(x['path'] for x in tree)),'FAIL')
observe('eager_long_diff',firstcase,first_ev(text+'\n'+diff.read_text()),'FAIL')
observe('eager_file_contents',firstcase,first_ev(text+'\n'+next(f for f in files if 'UNSELECTED_TREE_PATH_' in f.name).read_text()),'FAIL')
observe('hide_necessary_context',firstcase,first_ev(''),'FAIL')
secondcase=copy.deepcopy(cases['S-027']);secondcase['assertions']=[a for a in secondcase['assertions'] if a['source']=='journal:provider_second'];secondcase['evidence_required']=sorted({'journal:provider_second'}|{a['other']['source'] for a in secondcase['assertions'] if 'other'in a})
refs={'bytes:retrieval_selected':art('selected.raw',selected.read_bytes()),'bytes:retrieval_diff':art('diff.raw',diff.read_bytes()),'bytes:retrieval_stdout':art('stdout.raw',p.stdout)}
def second_ev(output):return {**refs,'journal:provider_second':journal('second-'+str(len(checks))+'.jsonl',[{'type':'provider_request','payload':{'messages':[{'role':'toolResult','content':[{'type':'text','text':output}]}]}}])}
observe('native_feedback_with_complete_stdout',secondcase,second_ev(p.stdout.decode()),'PASS')
observe('native_feedback_drops_source_binding',secondcase,second_ev(actual['file_fragment']+actual['diff_fragment']),'FAIL')
raw=long_log();source_ref={'fixture_only':True,'resource_id':'original-log','archive_sha256':digest(raw),'version':'captured'}
clipdef=protocol['fixtures']['clip'];prefix=clipdef['prefix'];suffix=clipdef['suffix'];clip={'clipped':True,'owner':'F','read_path':'/input/originals/log','source_ref':source_ref,'source_sha256':digest(raw),'source_bytes':len(raw),'retained_ranges':[[0,len(prefix.encode())],[len(raw)-len(suffix.encode()),len(raw)]],'fragments':[prefix,suffix]}
clipbase={'bytes:original':art('log-original.raw',raw),'bytes:retained':art('log-retained.raw',raw),'bytes:retrieved':art('log-retrieved.raw',raw),'journal:clip_source':journal('clip-source.jsonl',[{'type':'actual_immutable_source_reference','reference':source_ref}])}
def clip_ev(block):return {**clipbase,'journal:provider':journal('clip-'+str(len(checks))+'.jsonl',[{'type':'provider_request','payload':{'messages':[{'role':'user','content':[{'type':'text','text':'UNKNOWN_EXEC_17'},{'type':'text','text':json.dumps(block,ensure_ascii=False)}]}]}}])}
observe('useful_exact_clipped_view',cases['S-020'],clip_ev(clip),'PASS')
bad=copy.deepcopy(clip);bad['fragments']=['',''];observe('empty_fragments_label_only',cases['S-020'],clip_ev(bad),'FAIL')
bad=copy.deepcopy(clip);bad['retained_ranges'][1][0]-=1;observe('wrong_utf8_byte_range',cases['S-020'],clip_ev(bad),'FAIL')
bad=copy.deepcopy(clip);bad['source_sha256']='0'*64;observe('wrong_full_source_hash',cases['S-020'],clip_ev(bad),'FAIL')
bad=copy.deepcopy(clip);del bad['source_ref'];observe('missing_source_ref_is_invalid',cases['S-020'],clip_ev(bad),'INVALID')
missing=clip_ev(clip);del missing['bytes:retained'];observe('missing_original_not_negative_killed',cases['S-020'],missing,'INVALID')
result={'scope':'CONTEXT_FIXTURE_AND_ORACLE_PREPARATION_ONLY','S_component':'NOT_IMPLEMENTED','formal_S_cases_executed':0,'checks':checks,'pass':all(c['pass'] for c in checks),'inputs':{str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in [R/'context_fixtures.py',R/'oracle.py',R/'context-selftest.py',ROOT/'design/g3/s/context-supplement-004.json',ROOT/'design/g3/s/cases.json']}}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'pass':result['pass'],'checks':len(checks)}));raise SystemExit(0 if result['pass'] else 1)
