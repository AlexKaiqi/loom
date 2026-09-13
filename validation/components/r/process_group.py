"""Observe and reap only a process group created by this verifier."""
import os,signal,time
from pathlib import Path

def members(pgid):
 rows=[]
 for path in Path('/proc').iterdir():
  if not path.name.isdigit():continue
  try:
   fields=(path/'stat').read_text().rsplit(') ',1)[1].split()
   if int(fields[2])==pgid and int(fields[3])==pgid:rows.append({'pid':int(path.name),'state':fields[0],'ppid':int(fields[1]),'pgid':int(fields[2]),'session':int(fields[3]),'starttime':int(fields[19])})
  except (OSError,ValueError,IndexError):continue
 return sorted(rows,key=lambda x:x['pid'])

def cleanup(pgid):
 before=members(pgid);sent=False
 if any(row['state']!='Z' for row in before):
  try:os.killpg(pgid,signal.SIGKILL);sent=True
  except ProcessLookupError:pass
 end=time.monotonic()+3
 while True:
  after=members(pgid)
  if not any(row['state']!='Z' for row in after) or time.monotonic()>=end:break
  time.sleep(.02)
 return {'owned_pgid':pgid,'before':before,'signal_sent':sent,'after':after,'no_running_members':not any(row['state']!='Z' for row in after),'note':'Zombie records, if any, are reported separately; no unrelated process group is touched.'}
