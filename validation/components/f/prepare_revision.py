"""FR01-04 verification preparation; no F product implementation."""
import ast,ctypes,fcntl,hashlib,json,os,subprocess,sys
from pathlib import Path
from writer_handshake import attempt_under_lease
ROOT=Path(__file__).resolve().parents[3]
out=ROOT/'validation/components/f/evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
q=out/'leased-file';q.write_bytes(b'OLD');fd=os.open(q,os.O_RDONLY);fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_RDLCK);children=[]
try:
 attempt_under_lease(q,out/'actual-handshake',timeout=2,on_started=children.append)
 before=q.read_bytes();assert before==b'OLD' and len(children)==1 and children[0].poll() is None
finally:fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_UNLCK);os.close(fd)
stdout,stderr=children[0].communicate(timeout=5);(out/'writer.stdout').write_bytes(stdout);(out/'writer.stderr').write_bytes(stderr);assert children[0].returncode==0 and q.read_bytes()==b'AFTER'
libc=ctypes.CDLL(None,use_errno=True);monitor=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
if monitor<0:raise OSError(ctypes.get_errno(),'inotify_init1')
try:observed=os.readlink('/proc/self/fd/'+str(monitor));assert observed=='anon_inode:inotify'
finally:os.close(monitor)
missing=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('run_contract.py')),'--module','lore_files','--batch',sys.argv[2]],cwd=ROOT,capture_output=True);(out/'missing.stdout').write_bytes(missing.stdout);(out/'missing.stderr').write_bytes(missing.stderr)
assert missing.returncode==2
plan=json.loads((ROOT/'design/g3/f/cases.json').read_text());tree=ast.parse(Path(__file__).with_name('test_contract.py').read_text());ids=[n.name.split('_')[1] for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Contract' for n in x.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')];assert sorted(ids)==sorted(c['id'] for c in plan['cases']) and len(ids)==19
result={'scope':'G3 verifier/driver preparation only; no component pass','actual_handshake':{'before_release_b64':'T0xE','after_release':'AFTER','child_exit':children[0].returncode},'actual_monitor':{'type':observed,'closed':True},'missing_component_exit':missing.returncode,'case_ids':ids,'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},'protocol_sha256':hashlib.sha256((ROOT/'design/g3/f/observer-protocol.json').read_bytes()).hexdigest()}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
