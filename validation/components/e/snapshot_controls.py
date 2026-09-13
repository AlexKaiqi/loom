"""Finite provenance preparation against a real R gate; never creates a fake PASS gate."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from snapshot_support import copy_file,package,digest,save,drift
from dependency_snapshot import verify_loaded,gate_original
ROOT=Path(__file__).resolve().parents[3]

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--r-gate',required=True);args=p.parse_args();out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False);stage=out/'workspace';stage.mkdir();record={'original':{},'copied':{}}
 control_sources={str(Path(__file__).resolve()):digest(Path(__file__)),**{str(Path(__file__).resolve().parent/n):digest(Path(__file__).resolve().parent/n) for n in ['snapshot_support.py','dependency_snapshot.py','snapshot_audit.py']}}
 os.environ['LORE_DEPENDENCY_AUDIT']=str(out/'dependency-audit.jsonl')
 gatepath=Path(args.r_gate).resolve();gate=gate_original(gatepath);rp=package('lore_control',ROOT,stage,record)
 assert gate['implementation']=={k:v['sha256'] for k,v in rp['source_to_copy'].items()}
 gatecopy=copy_file(gatepath,stage/'r-gate.json',record)
 proof={'schema':'lore.source-equivalence/r-v1','workspace':str(stage),'gate_original':str(gatepath),'gate_copy':str(gatecopy),'gate_sha256':digest(gatepath),'source_to_copy':rp['source_to_copy'],'copied_package_root':rp['copied_package_root']};path=out/'equivalence.json';save(path,proof);checks={}
 checks['actual_R_original_accepted']=verify_loaded(gatepath,rp['original_entry'])==gate
 checks['actual_R_exact_copy_accepted']=verify_loaded(gatecopy,rp['copied_entry'],path)==gate
 def rejection(name,alter,loaded=None):
  item=json.loads(json.dumps(proof));restore=alter(item);save(path,item)
  try:verify_loaded(gatecopy,loaded or rp['copied_entry'],path);checks[name]=False
  except RuntimeError as e:checks[name]=str(e).startswith('MISSING verified R dependency:')
  finally:
   if restore:restore()
   save(path,proof)
 keys=list(proof['source_to_copy']);file=Path(rp['copied_entry']);raw=file.read_bytes()
 def change_copy(item):file.write_bytes(raw+b'\n# bad copy\n');return lambda:file.write_bytes(raw)
 rejection('copy_byte_change_rejected',change_copy)
 rejection('missing_mapping_rejected',lambda item:item['source_to_copy'].pop(keys[-1]) and None)
 def duplicate(item):item['source_to_copy'][keys[-1]]['copy']=item['source_to_copy'][keys[0]]['copy']
 rejection('duplicate_destination_rejected',duplicate)
 rejection('unbound_loaded_path_rejected',lambda item:None,rp['original_entry'])
 extra=Path(rp['copied_package_root'])/'extra.py'
 def add_extra(item):extra.write_text('# foreign source\n');return lambda:extra.unlink()
 rejection('extra_package_source_rejected',add_extra)
 original_gate=gatecopy.read_bytes()
 def changed_gate(item):
  value=json.loads(original_gate);value['status']='FAIL';save(gatecopy,value);return lambda:gatecopy.write_bytes(original_gate)
 rejection('changed_gate_copy_rejected',changed_gate)
 config=json.loads((ROOT/'design/g4/e-snapshot-environment.json').read_text())
 for source,expected in config['files'].items():
  source=Path(source);assert digest(source)==expected
  rel=Path('research/.venvs/runtime-research/bin/python') if str(source)=='/usr/bin/python3.10' else source.relative_to(ROOT)
  dest=copy_file(source,stage/rel,record)
  if dest.name in ['python','nats-server']:dest.chmod(0o755)
 copy_file(ROOT/'validation/components/e/snapshot_audit.py',stage/'sitecustomize.py',record)
 script=stage/'environment_probe.py';script.write_text("import json,sys,subprocess,nats,lore_control\nfrom pathlib import Path\nrow={'python':sys.executable,'nats':nats.__file__,'R':lore_control.__file__}\nif len(sys.argv)==1:\n p=subprocess.run([sys.executable,'-B',__file__,'child'],capture_output=True,text=True,timeout=8)\n row.update(child_exit=p.returncode,child=json.loads(p.stdout),child_stderr=p.stderr)\nprint(json.dumps(row))\n")
 record['copied'][str(script)]=digest(script);(out/'audit').mkdir()
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(stage),'PYTHONDONTWRITEBYTECODE':'1','LORE_SNAPSHOT_ROOT':str(stage),'LORE_SNAPSHOT_AUDIT_DIR':str(out/'audit')}
 argv=[str(stage/'research/.venvs/runtime-research/bin/python'),'-B',str(script)]
 proc=subprocess.run(argv,capture_output=True,text=True,env=env,timeout=20);save(out/'environment-command.json',{'argv':argv,'env':env,'exit':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
 try:
  row=json.loads(proc.stdout);paths=[row[k] for k in ['python','nats','R']]+[row['child'][k] for k in ['python','nats','R']]
  checks['copied_interpreter_client_R_and_child_import_paths']=proc.returncode==0 and row['child_exit']==0 and not proc.stderr and not row['child_stderr'] and all(Path(x).is_relative_to(stage) for x in paths) and not drift(record)
 except (ValueError,KeyError):checks['copied_interpreter_client_R_and_child_import_paths']=False
 result={'control_sources':control_sources,'control_sources_unchanged':all(digest(p)==h for p,h in control_sources.items()),'status':'PASS' if all(checks.values()) else 'FAIL','scope':'Provenance/environment preparation; 0 E cases, 0 NATS server','checks':checks,'source':record,'drift':drift(record),'gate_sha256':digest(gatepath)};save(out/'result.json',result);print(json.dumps({'status':result['status'],'checks':checks}));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
