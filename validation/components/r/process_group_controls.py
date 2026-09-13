"""Known orphan control for the external launcher, never R behavior."""
import json,subprocess,sys,time
from pathlib import Path
from process_group import cleanup,members
out=Path(__file__).parent/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
code="import subprocess,time,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(p.pid,flush=True); time.sleep(.2)"
p=subprocess.Popen([sys.executable,'-B','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
try:
 child_id=int(p.stdout.readline());leader=members(p.pid);assert p.wait(timeout=3)==0
 orphan=members(p.pid);assert any(row['pid']==child_id and row['state']!='Z' for row in orphan)
 result=cleanup(p.pid);assert result['signal_sent'] and result['no_running_members'];assert all(row['pid']==child_id for row in result['before'])
 again=cleanup(p.pid);assert not again['signal_sent'];record={'scope':'external launcher known orphan cleanup only','status':'PASS','leader_before':leader,'parent_exit':p.returncode,'actual_child_pid':child_id,'cleanup':result,'second_cleanup':again}
finally:
 cleanup(p.pid)
 if p.poll() is None:p.wait(timeout=3)
(out/'result.json').write_text(json.dumps(record,indent=2));print(json.dumps({'status':record['status'],'actual_child_pid':child_id,'no_running_members':result['no_running_members']}))
