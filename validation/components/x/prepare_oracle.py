"""Recompute preparation verdicts from saved raw bytes; ignores probe status/checks."""
from pathlib import Path
import json,hashlib
from oracle import archive,EvidenceError
PAYLOAD=b'fixed-bytes-\x00-\xff-\xe9\x9b\xaa'
def check_bundle(raw):
 def j(name):return json.loads(raw[name])
 a=archive(raw['checkpoint-1.tar']);b=archive(raw['checkpoint-2.tar']);f=a['files'];g=b['files']
 required={'payload.bin','hardlink','alias','external-link','empty','locked.bin','heartbeat','.'}
 if set(f)!=required or set(g)!=required:raise EvidenceError('complete fixture member set differs')
 for entries in [f,g]:
  if entries['payload.bin']['sha256']!=hashlib.sha256(PAYLOAD).hexdigest():raise EvidenceError('payload bytes')
  if entries['payload.bin']['mtime_ns']!=1700000000123456789:raise EvidenceError('mtime ns')
  if entries['payload.bin']['mode']!=0o751:raise EvidenceError('mode')
  if entries['locked.bin']['sha256']!=hashlib.sha256(b'locked-but-required').hexdigest() or entries['locked.bin']['mode']!=0:raise EvidenceError('mode000 omitted')
  if entries['empty']['type']!='directory' or entries['alias']['type']!='symlink' or entries['external-link']['linkname']!='/not-authorized/canary':raise EvidenceError('ordinary links/directories')
  if entries['hardlink']['sha256']!=entries['payload.bin']['sha256']:raise EvidenceError('hardlink data')
 if g['heartbeat']['count']<=f['heartbeat']['count']:raise EvidenceError('resume did not advance actual file')
 quota=j('020.stdout');inode=j('021.stdout')
 if quota['bytes_total']!=4194304 or quota['bytes_free']!=0:raise EvidenceError('physical byte quota')
 if inode['inodes_total']!=128 or inode['inodes_free']!=0 or inode['errno']!=28:raise EvidenceError('physical inode quota')
 keeper=j('024.stdout')[0];helper=j('031.stdout')[0]
 def mount(x):return next(m for m in x['Mounts'] if m['Destination']=='/work')
 if not keeper['State']['Paused'] or not keeper['State']['Running']:raise EvidenceError('freeze not actual')
 km,hm=mount(keeper),mount(helper)
 if km['Name']!=hm['Name'] or km['Source']!=hm['Source'] or hm['RW'] or not km['RW']:raise EvidenceError('same readonly export object')
 if [x.removeprefix('CAP_') for x in helper['HostConfig']['CapAdd']]!=['DAC_OVERRIDE'] or helper['Config']['User']!='0:0':raise EvidenceError('bounded read authority')
 pre=j('046.stdout');post=j('053.stdout')
 if not pre['actual_pids'] or post['actual_pids'] or pre['namespace']!=post['namespace'] or j('050.stdout')[0]['State']['Running']:raise EvidenceError('actual old writer remains')
 life=archive(raw['lifecycle/after-exit.tar']);task=j('lifecycle/004.stdout')
 if task['uid']!=1000 or task['kill_keeper_errno']!=1:raise EvidenceError('keeper task identity')
 if not j('lifecycle/005.stdout')[0]['State']['Running']:raise EvidenceError('keeper lost before export')
 if j('lifecycle/010.stderr')['write_errno']!=30:raise EvidenceError('exporter may write')
 if life['files']['locked.bin']['sha256']!=hashlib.sha256(b'preserved-after-command-exit').hexdigest():raise EvidenceError('post-exit file lost')
 if j('lifecycle/014.stdout')[0]['State']['Running']:raise EvidenceError('keeper not stopped')
 return {'accepted_prepare_facts':True,'archive_sha256':[a['sha256'],b['sha256']],'namespace':pre['namespace'],'before_pids':pre['actual_pids'],'after_pids':post['actual_pids']}
def load(root):
 keys=['checkpoint-1.tar','checkpoint-2.tar','020.stdout','021.stdout','024.stdout','031.stdout','046.stdout','053.stdout','050.stdout'];a=root/'storage-preparation-001';b=root/'lifecycle-preparation-002';raw={k:(a/k).read_bytes() for k in keys}
 for k in ['after-exit.tar','004.stdout','005.stdout','010.stderr','014.stdout']:raw['lifecycle/'+k]=(b/k).read_bytes()
 return raw
