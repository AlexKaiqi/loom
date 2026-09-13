"""Source-only capture and observed execution checks for the E acceptance wrapper."""
import hashlib,json,os,shutil
from pathlib import Path

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def copy_file(original,dest,record):
 original=Path(original).absolute();dest=Path(dest).absolute()
 if not original.is_file() or original.is_symlink():raise ValueError('source missing or symlinked: '+str(original))
 dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,dest)
 record['original'][str(original)]=digest(original);record['copied'][str(dest)]=digest(dest)
 return dest

def package(module,root,stage,record):
 parts=module.split('.')
 if not all(x.isidentifier() for x in parts):raise ValueError('explicit Python module required')
 top=Path(root)/parts[0]
 if top.is_dir() and (top/'__init__.py').is_file():files=sorted(top.rglob('*.py'));entry=top.joinpath(*parts[1:]) if len(parts)>1 else top;entry=entry/'__init__.py' if entry.is_dir() else entry.with_suffix('.py')
 elif len(parts)==1 and top.with_suffix('.py').is_file():files=[top.with_suffix('.py')];entry=files[0]
 else:return None
 if not entry.is_file():return None
 sources={}
 for source in files:
  dest=copy_file(source,Path(stage)/source.relative_to(root),record);sources[str(source.resolve())]={'copy':str(dest),'sha256':digest(source)}
 return {'module':module,'original_entry':str(entry),'copied_entry':str(Path(stage)/entry.relative_to(root)),'copied_package_root':str(Path(stage)/top.relative_to(root)),'source_to_copy':sources}

def drift(record):
 return [p for key in ['original','copied'] for p,h in record[key].items() if not Path(p).is_file() or Path(p).is_symlink() or digest(p)!=h]

def object_state(row):
 try:
  fields=(Path('/proc')/str(row['pid'])/'stat').read_text().rsplit(') ',1)[1].split()
  same=int(fields[19])==row['starttime']
  return {'pid':row['pid'],'original_starttime':row['starttime'],'current_starttime':int(fields[19]),'state':fields[0],'same_object':same,'running_original':same and fields[0]!='Z'}
 except (OSError,ValueError,IndexError):return {'pid':row['pid'],'original_starttime':row['starttime'],'running_original':False,'state':'absent'}

def audit_execution(out,stage,record,packages,nats_binary):
 rows=[]
 for p in sorted((Path(out)/'audit').glob('*.jsonl')):
  rows.extend(json.loads(line) for line in p.read_text().splitlines())
 bound=record['copied'];execs=[r for r in rows if r['event']=='exec'];spawns=[r for r in rows if r['event']=='spawn'];unknown=[]
 for row in execs:
  file=Path(row['filename'])
  if str(file) in bound:
   if row['sha256']!=bound[str(file)]:unknown.append(row)
  elif file.is_relative_to('/usr/lib/python3.10'):
   if not file.is_file() or digest(file)!=row['sha256']:unknown.append(row)
  else:unknown.append(row)
 seen={r['filename'] for r in execs};required=[p['copied_entry'] for p in packages];required += [str(Path(stage)/'research/.venvs/runtime-research/lib/python3.10/site-packages/nats/__init__.py')]
 missing=[p for p in required if p not in seen]
 servers=[r for r in spawns if r['exe']==str(nats_binary)];starts=[]
 for p in (Path(stage)/'validation/components/e/evidence').rglob('lifecycle.json'):
  starts.extend({**row,'file':str(p)} for row in json.loads(p.read_text()) if row.get('action')=='start')
 server_ids={r['pid'] for r in servers};lifecycle_ids={r['pid'] for r in starts}
 server_hash_ok=all(r['exe_sha256']==bound[str(nats_binary)] for r in servers)
 states=[object_state(r) for r in servers];spawn_states=[object_state(r) for r in spawns]
 provenance=[]
 f=Path(out)/'dependency-audit.jsonl'
 if f.exists():provenance=[json.loads(line) for line in f.read_text().splitlines()]
 # This cannot prove hostile code is unable to alter same-UID records; it observes trusted test runs.
 python=Path(stage)/'research/.venvs/runtime-research/bin/python'
 allowed_exes={str(python),str(nats_binary)};exec_pids={r['pid'] for r in execs}
 checks={'all_observed_children_stopped':not any(r['running_original'] for r in spawn_states),'all_spawns_identified':not any(r['event']=='spawn-unobserved' for r in rows),'all_spawn_executables_bound':all(r['exe'] in allowed_exes and r['exe_sha256']==bound.get(r['exe']) for r in spawns),'all_python_children_have_exec_audit':all(r['pid'] in exec_pids for r in spawns if r['exe']==str(python)),'has_exec_audit':bool(execs),'all_executed_sources_bound':not unknown,'all_candidate_entries_observed':not missing,'nats_actual_processes_observed':bool(servers),'all_server_lifecycle_starts_match':server_ids==lifecycle_ids,'server_binary_sha':server_hash_ok,'no_original_server_running':not any(r['running_original'] for r in states),'r_dependency_proof_observed':bool(provenance)}
 return {'checks':checks,'unbound_execs':unknown,'missing_entries':missing,'exec_rows':len(execs),'pids':sorted({r['pid'] for r in execs}),'spawns':spawns,'spawn_after':spawn_states,'unobserved_spawns':[r for r in rows if r['event']=='spawn-unobserved'],'nats_processes':servers,'nats_after':states,'r_dependency_checks':provenance}
