"""G3 calibration only, never reports a production X PASS."""
from pathlib import Path
import copy,json,subprocess,sys,hashlib
from prepare_oracle import load,check_bundle
from oracle import EvidenceError
R=Path(__file__).parent;batch=sys.argv[1];out=R/'evidence'/batch;out.mkdir(parents=True,exist_ok=False);raw=load(R/'evidence');rows=[]
def attempt(name,data,want):
 try:detail=check_bundle(data);accepted=True
 except Exception as e:detail={'error':repr(e)};accepted=False
 rows.append({'name':name,'expected_accept':want,'actual_accept':accepted,'matched':accepted==want,'detail':detail})
attempt('real_named_tmpfs_and_keeper_raw',raw,True)
for key in raw:
 b=dict(raw);del b[key];attempt('missing:'+key,b,False)
b=dict(raw);b['checkpoint-1.tar']=(R/'evidence/storage-preparation-001/009.stdout').read_bytes();attempt('cp_exit_zero_but_empty',b,False)
b=dict(raw);b['checkpoint-1.tar']=(R/'evidence/storage-preparation-001/unprivileged-incomplete.tar').read_bytes();attempt('mode000_not_read',b,False)
for name,key,mut in [
 ('wrong_export_volume','031.stdout',lambda o:o[0]['Mounts'][0].update({'Name':'wrong-volume'})),
 ('exporter_writable','031.stdout',lambda o:o[0]['Mounts'][0].update({'RW':True})),
 ('claimed_stop_old_pids_remain','053.stdout',lambda o:o.update({'actual_pids':[12345]})),
 ('bytes_unbounded','020.stdout',lambda o:o.update({'bytes_total':999999999})),
 ('inodes_not_exhausted','021.stdout',lambda o:o.update({'inodes_free':100})),
 ('task_can_kill_keeper','lifecycle/004.stdout',lambda o:o.update({'kill_keeper_errno':None})),
 ('root_exporter_can_write','lifecycle/010.stderr',lambda o:o.update({'write_errno':None}))]:
 b=dict(raw);v=json.loads(b[key]);mut(v);b[key]=json.dumps(v).encode();attempt(name,b,False)
for name,args,want in [('missing_target',['--batch',batch+'-missing'],4),('fake_green',['--batch',batch+'-fake-green','--case','X001','--component-json',json.dumps([sys.executable,str(R/'always_green_adapter.py')])],1)]:
 p=subprocess.run([sys.executable,'-B',str(R/'run.py'),*args],capture_output=True,timeout=40);(out/(name+'.stdout')).write_bytes(p.stdout);(out/(name+'.stderr')).write_bytes(p.stderr);rows.append({'name':name,'actual_exit':p.returncode,'expected_exit':want,'matched':p.returncode==want})
result={'type':'G3_ORACLE_AND_DRIVER_CALIBRATION_ONLY','production_component':'NOT_IMPLEMENTED','raw_inputs':{k:hashlib.sha256(v).hexdigest() for k,v in raw.items()},'checks':rows,'pass':all(r['matched'] for r in rows)};(out/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'pass':result['pass'],'checks':len(rows)}));raise SystemExit(0 if result['pass'] else 1)
