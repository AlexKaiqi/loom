"""Validator/fixture repair calibration only, not an S behavior test."""
from pathlib import Path
import hashlib,io,json,subprocess,sys,tarfile
import live_ports
from collector import CaseDriver
from physical_witness import stop_witness
from oracle import InvalidEvidence
R=Path(__file__).parent;out=R/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False);rows=[]
d=CaseDriver.__new__(CaseDriver);d.journals={};d.recovery=False
d.observe_result({'operation_id':'old','boundary_kind':'answer_saved'})
d.recovery=True;d.observe_result({'operation_id':'restore','boundary_kind':'blocked_invalid','error':{'code':'session_corrupt'}})
rows.append({'name':'retain_old_final_no_new_corrupt_recovery_final','pass':len(d.journals['accepted_finals'])==1 and len(d.journals.get('recovery_finals',[]))==0})
d.observe_result({'operation_id':'wrong-recovery','boundary_kind':'answer_saved'})
rows.append({'name':'wrong_recovery_final_is_observed_separately','pass':len(d.journals['accepted_finals'])==2 and len(d.journals['recovery_finals'])==1})
d.response='single-tool';d.bootstrap_tool_marker=True;message=d.message();script=message['content'][0]['arguments']['script'];p=subprocess.run(['/bin/sh','-c',script],capture_output=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=2);(out/'real-print.stdout').write_bytes(p.stdout);(out/'real-print.stderr').write_bytes(p.stderr)
rows.append({'name':'actual_fixed_shell_script_produces_tool_stdout_marker','pass':p.returncode==0 and p.stdout=='ORIGINAL_TOOL_RESULT_雪\n'.encode(),'argv':['/bin/sh','-c',script]})
source=json.loads((R/'evidence/physical-preparation-003/result.json').read_text());witness=source['before'];wrong={k:witness[k] for k in ['container_id','exec_id','object_generation']};wrong['object_generation']+=1
try:stop_witness(wrong,witness,out/'wrong-generation');rejected=False
except InvalidEvidence:rejected=True
rows.append({'name':'wrong_generation_rejected_before_OS_claim','pass':rejected})
# This small test covers the DRIVER checkpoint mode, with real saved Pi bytes
# packaged as an explicit test reference; it is not an X/S component mock pass.
original=(R/'evidence/container-preparation-002/single.original.jsonl').read_bytes()
archive_path=out/'checkpoint-mode-fixture.tar'
with tarfile.open(archive_path,'w') as t:
 info=tarfile.TarInfo('sessions/original.jsonl');info.size=len(original);t.addfile(info,io.BytesIO(original))
blob=archive_path.read_bytes();ref={'path':str(archive_path.resolve()),'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob)}
live_ports.ARTIFACT_ROOTS=[out.resolve()];trace=[]
def checkpoint_port(name,method,**kw):
 trace.append(method)
 return {'prepared_artifact':ref,'receipt':{'test_only':True}} if method=='checkpoint' else {}
d.root=out;d.calls=1;d.env={'test_only':True};d.binding={'session_id':'test-original'};d.artifacts={};d.port=checkpoint_port
d.checkpoint('final-no-resume',resume=False)
rows.append({'name':'final_checkpoint_keeps_frozen_until_seal','pass':trace==['checkpoint'] and d.frozen is True})
trace.clear();d.checkpoint('intermediate',resume=True)
rows.append({'name':'intermediate_checkpoint_explicitly_resumes','pass':trace==['checkpoint','resume'] and d.frozen is False})
result={'scope':'S_DRIVER_REPAIR_CALIBRATION_ONLY','S_component':'NOT_IMPLEMENTED','checks':rows,'pass':all(x['pass'] for x in rows),'sources':{f:hashlib.sha256((R/f).read_bytes()).hexdigest() for f in ['collector.py','collector_actions.py','physical_witness.py']}};(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'pass':result['pass'],'checks':len(rows)}));raise SystemExit(0 if result['pass'] else 1)
