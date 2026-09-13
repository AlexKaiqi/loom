"""Independent bounded writer/lease-break handshake; no F imports."""
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path

def attempt_under_lease(target,evidence,timeout=2,on_started=None):
 target=Path(target);evidence=Path(evidence);evidence.mkdir(exist_ok=False)
 ready=evidence/'ready.json';before=target.read_bytes();signals=[];prior=signal.getsignal(signal.SIGIO);child=None;valid=False
 def relay(sig,frame):
  signals.append({'signal':sig,'monotonic':time.monotonic()})
 signal.signal(signal.SIGIO,relay)
 try:
  child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('writer_worker.py')),str(target),str(ready)],env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  if on_started is not None:on_started(child)
  deadline=time.monotonic()+timeout;message=None
  while time.monotonic()<deadline:
   if ready.exists():
    message=json.loads(ready.read_text())
    if message!={'pid':child.pid,'target':str(target),'stage':'immediately_before_write_open'}:raise AssertionError('wrong writer ready identity')
   if message and signals:
    if child.poll() is not None:raise AssertionError('writer already completed while original lease should block')
    if target.read_bytes()!=before:raise AssertionError('bytes changed while original lease should block')
    valid=True;break
   if child.poll() is not None:raise AssertionError('writer exited before observed lease-break handshake')
   time.sleep(.01)
  if not valid:raise AssertionError('bounded writer ready/SIGIO handshake not observed')
  if callable(prior):prior(signal.SIGIO,None)
  return child
 finally:
  record={'pid':child.pid if child else None,'target':str(target),'signals':signals,'observed':valid,'before_sha256':hashlib.sha256(before).hexdigest(),'writer_exit_at_handshake':child.poll() if child else None,'scope':'actual atomic child ready plus delivered SIGIO and still-blocked writer; verification checkpoint defers and then relays original SIGIO handler after observing ready/blocked state'}
  (evidence/'observation.json').write_text(json.dumps(record,indent=2)+'\n');signal.signal(signal.SIGIO,prior)
  if not valid and child is not None:
   if child.poll() is None:child.kill()
   stdout,stderr=child.communicate(timeout=5);(evidence/'writer.stdout').write_bytes(stdout);(evidence/'writer.stderr').write_bytes(stderr)
