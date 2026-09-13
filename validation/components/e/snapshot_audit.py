"""Loaded as sitecustomize only in a frozen, secret-free validation interpreter."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path(os.environ['LORE_SNAPSHOT_ROOT']).resolve()
out=Path(os.environ['LORE_SNAPSHOT_AUDIT_DIR']);out.mkdir(exist_ok=True)
fd=os.open(out/(str(os.getpid())+'.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
def record(row):os.write(fd,(json.dumps(row)+'\n').encode());os.fsync(fd)
def hook(event,args):
 if event!='exec':return
 file=getattr(args[0],'co_filename','')
 if not file.startswith('/'):return
 p=Path(file)
 record({'event':'exec','pid':os.getpid(),'filename':file,'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,'inside_snapshot':p.is_relative_to(root)})
sys.addaudithook(hook)
original_init=subprocess.Popen.__init__
def init(self,*args,**kwargs):
 original_init(self,*args,**kwargs)
 try:
  base=Path('/proc')/str(self.pid);raw=(base/'stat').read_text();fields=raw[raw.rfind(')')+2:].split();exe=(base/'exe').resolve()
  record({'event':'spawn','parent_pid':os.getpid(),'pid':self.pid,'starttime':int(fields[19]),'pgid':int(fields[2]),'session':int(fields[3]),'exe':str(exe),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'argv':(base/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')})
 except OSError as e:record({'event':'spawn-unobserved','parent_pid':os.getpid(),'pid':self.pid,'error':type(e).__name__})
subprocess.Popen.__init__=init
