import os,time,json,sys,errno
from pathlib import Path
p=Path('/work'); (p/'empty').mkdir();(p/'payload.bin').write_bytes(b'fixed-bytes-\x00-\xff-\xe9\x9b\xaa')
os.chmod(p/'payload.bin',0o751);os.utime(p/'payload.bin',ns=(1700000000123456789,1700000000123456789))
(p/'locked.bin').write_bytes(b'locked-but-required');os.chmod(p/'locked.bin',0)
os.symlink('payload.bin',p/'alias');os.link(p/'payload.bin',p/'hardlink');os.symlink('/not-authorized/canary',p/'external-link')
xattr=None
try:os.setxattr(p/'payload.bin','user.lore',b'checkpoint');xattr='set'
except OSError as e:xattr={'errno':e.errno}
fd=os.open(p/'heartbeat',os.O_CREAT|os.O_RDWR,0o600);os.write(fd,b'0'.ljust(64,b' '))
result={'pid':os.getpid(),'uid':os.getuid(),'gid':os.getgid(),'namespace':os.readlink('/proc/self/ns/pid'),'xattr':xattr}
if sys.argv[1]=='quota':
 (p/'filler').mkdir();total=0;err=None
 for i in range(20):
  try:
   with open(p/'filler'/str(i),'wb',buffering=0) as f:
    for _ in range(16):total+=f.write(b'F'*65536)
  except OSError as e:err=e.errno;break
 result['fill_error']=err;result['written']=total
print(json.dumps(result),flush=True)
for tick in range(1200):os.pwrite(fd,str(tick).encode().ljust(64,b' '),0);time.sleep(.05)
