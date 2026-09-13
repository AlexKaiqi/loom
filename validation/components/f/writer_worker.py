import json,os,sys
from pathlib import Path
p=Path(sys.argv[1]);ready=Path(sys.argv[2]);temp=ready.with_suffix('.tmp')
with temp.open('w') as f:
 json.dump({'pid':os.getpid(),'target':str(p),'stage':'immediately_before_write_open'},f);f.flush();os.fsync(f.fileno())
temp.replace(ready)
with p.open('wb',buffering=0) as f:f.write(b'AFTER')
