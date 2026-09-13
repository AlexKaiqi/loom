"""Independent copied-source/equivalence evidence; never a rewritten F gate."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def copy_f(ws):
 gate_path=ROOT/'design/g4/f-gate.json';gate=json.loads(gate_path.read_text())
 if gate.get('status')!='PASS' or gate.get('stage')!='G4' or gate.get('component')!='F':raise ValueError('verified F G4 gate missing')
 actual={str(p.resolve()):sha(p) for p in (ROOT/'lore_files').rglob('*.py') if p.is_file()}
 if actual!=gate['implementation']:raise ValueError('F complete source differs from original G4 gate')
 rows=[]
 for original,h in actual.items():
  p=Path(original)
  if p.is_symlink():raise ValueError('symlink F source')
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());rows.append({'original':original,'copy':str(q),'sha256':h})
 q=ws/'design/g4/f-gate.json';q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(gate_path.read_bytes())
 rec={'kind':'SOURCE_COPY_EQUIVALENCE_NOT_A_GATE','gate':{'original':str(gate_path),'copy':str(q),'sha256':sha(q)},'implementation':rows}
 save(ws/'f-source-equivalence.json',rec);return rec

def verify_f(ws):
 rec=json.loads((ws/'f-source-equivalence.json').read_text());g=rec['gate'];gate=json.loads(Path(g['copy']).read_text())
 if Path(g['copy'])!=ws/'design/g4/f-gate.json' or sha(g['copy'])!=g['sha256'] or gate.get('status')!='PASS' or gate.get('stage')!='G4' or gate.get('component')!='F':raise ValueError('F original gate unavailable or changed')
 if {x['original']:x['sha256'] for x in rec['implementation']}!=gate['implementation']:raise ValueError('F gate equivalence incomplete')
 expected={str(ws/'lore_files'/Path(x['original']).name):x['sha256'] for x in rec['implementation']}
 actual={str(p):sha(p) for p in (ws/'lore_files').rglob('*.py')}
 if actual!=expected or any(x['copy'] not in expected for x in rec['implementation']):raise ValueError('F copied source differs')
 return rec

AUDIT=r"""import os,sys,json,hashlib,sysconfig
from pathlib import Path
root=Path(__file__).resolve().parent
out=root.parent/'imports';out.mkdir(exist_ok=True)
fd=os.open(out/(str(os.getpid())+'.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
stdlib=Path(sysconfig.get_path('stdlib')).resolve()
os.write(fd,(json.dumps({'kind':'startup','pid':os.getpid(),'ppid':os.getppid(),'cwd':str(Path.cwd()),'argv':sys.argv,'pythonpath':os.environ.get('PYTHONPATH')})+'\n').encode());os.fsync(fd)
def hook(event,args):
 if event=='exec':
  name=getattr(args[0],'co_filename','')
  if not name or name.startswith('<'):return
  p=Path(name)
  if not p.is_absolute():p=Path.cwd()/p
  p=p.resolve()
  if p.is_relative_to(stdlib) and not p.is_relative_to(root):return
  row={'kind':'exec','pid':os.getpid(),'filename':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}
 elif event=='subprocess.Popen':
  executable,argv,cwd,env=args
  row={'kind':'spawn','pid':os.getpid(),'executable':str(executable),'argv':argv,'cwd':str(cwd),'pythonpath':(env or os.environ).get('PYTHONPATH')}
 else:return
 os.write(fd,(json.dumps(row)+'\n').encode());os.fsync(fd)
sys.addaudithook(hook)
"""

def inventory(cases,case_id=None):
 # Independent explicit expansion; does not call run.variants().
 import itertools
 rows=[]
 for c in cases:
  if case_id and c['id']!=case_id:continue
  params=c['initial']['parameters'];dimensions=[];used=set()
  for group in c['parameter_rules']['zip_groups']:
   if len({len(params[k]) for k in group})!=1:raise ValueError('zip size')
   dimensions.append([{k:params[k][i] for k in group} for i in range(len(params[group[0]]))]);used.update(group)
  for key,value in params.items():
   if key in used:continue
   if key=='repetitions':dimensions.append([{'repeat_index':n} for n in range(value)])
   else:dimensions.append([{key:v} for v in (value if isinstance(value,list) else [value])])
  for combination in itertools.product(*dimensions):
   values={k:v for part in combination for k,v in part.items()};values.setdefault('domain','task');rows.append({'case_id':c['id'],'parameters':values})
 return rows


def python_children(events,ws):
 # Direct Python children must keep the copied import root and actually start audit.
 children=[x for x in events if x['kind']=='spawn' and Path(x['executable']).name.startswith('python')]
 starts=[x for x in events if x['kind']=='startup'];checks=[]
 for parent in {x['pid'] for x in children}:
  requests=[x for x in children if x['pid']==parent];observed=[x for x in starts if x['ppid']==parent]
  checks.append({'parent_pid':parent,'requested':len(requests),'observed':len(observed),'pass':len(requests)==len(observed) and all(x['pythonpath']==str(ws) and x['cwd'] in ('None',str(ws)) and not any(v in x['argv'] for v in ('-I','-S','-E')) for x in requests) and all(x['pythonpath']==str(ws) and x['cwd']==str(ws) for x in observed)})
 return {'checks':checks,'pass':all(x['pass'] for x in checks)}
