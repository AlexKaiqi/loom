"""One short-lived caller; peer EOF never means task stdin closure."""
from pathlib import Path
import socket,sys
path,request=sys.argv[1:]
raw=Path(request).read_bytes()
if len(raw)>2097152:raise SystemExit('finite peer cap')
with socket.socket(socket.AF_UNIX)as peer:
 peer.settimeout(30);peer.connect(path);peer.sendall(raw);result=bytearray()
 while not result.endswith(b'\n'):
  part=peer.recv(65536)
  if not part:raise SystemExit('partial original reply')
  result+=part
  if len(result)>2097152:raise SystemExit('reply cap')
 sys.stdout.buffer.write(result)
