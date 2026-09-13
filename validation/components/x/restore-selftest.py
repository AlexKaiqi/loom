"""Real ordinary Linux fixture + restore oracle/actions calibration only; no X SUT."""
from pathlib import Path
import base64,copy,hashlib,json,os,subprocess,sys
from fixtures import create,script_bytes
from oracle import archive,assess,EvidenceError
from restore_actions import retain,clear_cache,fault_source,prepare_request
R=Path(__file__).resolve().parent;ROOT=R.parents[2];out=R/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
suite=json.loads((ROOT/'design/g3/x/cases.json').read_text());case=next(c for c in suite['cases'] if c['id']=='X028');fx=create(out/'fixture',case,{'domain':'task'});checks=[]
for p in [R/'restore-selftest.py',R/'restore_actions.py',R/'fixtures.py',R/'oracle.py',ROOT/'design/g3/x/cases.json',ROOT/'design/g3/x/restore-supplement-001.json']:(out/p.name).write_bytes(p.read_bytes())
def run(name,argv):
 p=subprocess.run(argv,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,timeout=10);(out/(name+'.stdout')).write_bytes(p.stdout);(out/(name+'.stderr')).write_bytes(p.stderr);(out/(name+'.command.json')).write_text(json.dumps({'argv':argv,'exit':p.returncode},indent=2)+'\n')
 if p.returncode:raise EvidenceError(name+' failed')
 return p.stdout
def pack(name,source):return run(name,['tar','--format=pax','--acls','--xattrs','--numeric-owner','--pax-option=delete=atime,delete=ctime','-cpf','-','-C',str(source),'.'])
# Explicit fixture-only relocation of /work onto this self-created finite folder.
seed=base64.b64decode(fx['request']['script_base64']).decode().replace('/work',str(fx['target']));seedout=run('actual-seed-fixture',['python3','-c',seed]);before_tar=pack('before-archive',fx['target']);original=archive(before_tar);blob=fx['state']/'checkpoint.tar';blob.write_bytes(before_tar)
old={'execution_id':fx['request']['execution_id'],'container_id':'a'*64,'exec_id':'b'*64,'volume_id':'explicit-calibration-old','object_generation':1,'freeze_generation':1};new={**old,'execution_id':'calibration-new','container_id':'c'*64,'exec_id':'d'*64,'volume_id':'explicit-calibration-new','object_generation':2,'freeze_generation':1}
api={'binding':old,'artifacts':{'checkpoint':{'path':str(blob),'sha256':hashlib.sha256(before_tar).hexdigest(),'size':len(before_tar)}}}
retain(fx,{'prepared':{'api':api,'archive':original}},'prepared',out)
restored=out/'restored';restored.mkdir();run('actual-tar-copy-fixture',['tar','--acls','--xattrs','--same-permissions','-xpf',str(blob),'-C',str(restored)])
readscript=script_bytes('restore_readonly',{'domain':'task'}).decode().replace('/work',str(restored));readout=run('actual-read-only-fixture',['python3','-c',readscript]);after=archive(pack('after-read-only-archive',restored))
cache,entries=clear_cache(fx);checks.append({'name':'actual_fixture_seed_tar_read_and_cache_clear','scope':'LINUX_FIXTURE_ONLY_NOT_X_RESTORE','pass':hashlib.sha256(seedout).hexdigest()==fx['values']['restore_original_stdout_sha256'] and hashlib.sha256(readout).hexdigest()==fx['values']['restore_verify_stdout_sha256'] and original['files']==after['files'] and original['files']['effect']['count']==1 and bool(entries) and not list(cache.iterdir())})
# Physical/API rows below are explicit oracle calibration specimens, not OS claims.
old_result={'output_state':'COMPLETE','exit_code':0,'original':'stable-calibration-result'}
blobs={'stdout':{'sha256':hashlib.sha256(seedout).hexdigest()},'stderr':{'sha256':hashlib.sha256(b'').hexdigest()}}
frames={'prepared':{'archive':original,'api':{'binding':old},'physical':{'namespace':'explicit-calibration-old-namespace'}},'released':{'physical':{'namespace_pids':[],'owned_containers':[],'owned_volumes':[]}},'cold_boundary':{'cache_empty':not list(cache.iterdir())},'rebuilt':{'api':{'binding':new},'physical':{'exec_running':False,'namespace':'pid:[900000002]','namespace_pids':[900000003],'host_rw_mounts':[],'network_mode':'none','log_driver':'none'}},'verify_running':{'physical':{'task_uid':1000,'cap_eff':0}},'restored_source':{'archive':after},'read_verified':{'blobs':{'stdout':{'sha256':hashlib.sha256(readout).hexdigest()}}},'verified_archive':{'archive':after},'new_released':{'physical':{'namespace_pids':[],'owned_containers':[],'owned_volumes':[]}},'old_before':{'api':{'binding':old,'result':old_result},'blobs':blobs},'old_after':{'api':{'binding':copy.deepcopy(old),'result':copy.deepcopy(old_result)},'blobs':copy.deepcopy(blobs)}}
def observe(name,sample,want):
 result=assess(case['expected'],sample,fx['values'],{'domain':'task'});(out/(name+'.assessment.json')).write_text(json.dumps(result,indent=2)+'\n');checks.append({'name':name,'scope':'EXPLICIT_ORACLE_CALIBRATION_ONLY','expected_accept':want,'accepted':result['pass'],'pass':result['pass']==want})
observe('well_formed_finite_restore_observations',frames,True)
bad=copy.deepcopy(frames);bad['rebuilt']['api']['error']={'code':'INPUT_VERSION_UNAVAILABLE'};observe('always_reject_legal_restore',bad,False)
bad=copy.deepcopy(frames);bad['rebuilt']['api']['binding']=copy.deepcopy(old);observe('reused_original_identity_generation',bad,False)
with (restored/'effect').open('ab') as f:f.write(b'one\n')
bad_archive=archive(pack('replayed-effect-archive',restored));bad=copy.deepcopy(frames);bad['verified_archive']['archive']=bad_archive;observe('actual_second_effect_in_bad_specimen',bad,False)
(restored/'untracked-dependency').unlink();bad=copy.deepcopy(frames);bad['restored_source']['archive']=archive(pack('missing-dependency-archive',restored));observe('actual_missing_dependency_specimen',bad,False)
bad=copy.deepcopy(frames);bad['old_after']['api']['result']['output_state']='PENDING';observe('changed_original_result',bad,False)
bad=copy.deepcopy(frames);del bad['old_after']['blobs']['stdout'];observe('missing_old_blob_rejected_not_killed',bad,False)
# Real file fault action covers both required source conditions; restore responses
# themselves remain unimplemented and are never generated by this calibration.
fx['params']['restore_fault']='hash_mismatch';fault_source(fx,out);corrupt=Path(fx['restore_source']['archive_ref']['path']);checks.append({'name':'actual_selected_source_hash_fault','scope':'FIXTURE_FAULT_ONLY','pass':hashlib.sha256(corrupt.read_bytes()).hexdigest()!=fx['restore_source']['archive_ref']['sha256']})
fx['params']['restore_fault']='missing'
# Preserve the hash-fault evidence first; a separate confined folder avoids overwrite.
missing_out=out/'missing-fault';missing_out.mkdir();fault_source(fx,missing_out);checks.append({'name':'actual_selected_source_missing_fault','scope':'FIXTURE_FAULT_ONLY','pass':not corrupt.exists() and not blob.exists()})
prepare_request(fx);checks.append({'name':'new_request_selects_old_source_and_new_read_script','scope':'DRIVER_REQUEST_CALIBRATION_ONLY','pass':fx['request']['execution_id']!=old['execution_id'] and fx['request']['object_generation']==2 and fx['request']['restore_source']['source_execution_id']==old['execution_id'] and base64.b64decode(fx['request']['script_base64']).decode()==script_bytes('restore_readonly',fx['params']).decode()})
result={'scope':'X_RESTORE_PREPARATION_ONLY','X_component':'NOT_IMPLEMENTED','formal_X_runs':0,'checks':checks,'pass':all(c['pass'] for c in checks),'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'restore-selftest.py',R/'restore_actions.py',R/'fixtures.py',R/'oracle.py',ROOT/'design/g3/x/cases.json',ROOT/'design/g3/x/restore-supplement-001.json']}};(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':result['pass'],'checks':len(checks)}));raise SystemExit(0 if result['pass'] else 1)
