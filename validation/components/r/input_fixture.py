"""Real-file E authority fixture for R validation; does not implement E or R."""
import hashlib,json,os,stat
from pathlib import Path

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def make_input(root,invocation,binding,label='original'):
 root=Path(root);root.mkdir()
 data={'events.jsonl':canonical({'fixture_event':label})+b'\n','invocation.json':canonical({'invocation_id':invocation,'binding':binding}),'execution-targets.json':canonical(binding['execution_targets'])}
 for name,raw in data.items():(root/name).write_bytes(raw)
 manifest={'fixture_schema':'e-authority-for-r/v1','invocation_id':invocation,'binding':binding,'range':{'start_sequence':binding['start_sequence'],'end_sequence':2,'high_watermark':2,'next_sequence':3},'event_refs':[{'owner':'E','id':'event-'+label}],'complete':True,'files':{name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in data.items()}}
 (root/'manifest.json').write_bytes(canonical(manifest));s=root.stat()
 return {'owner':'E','kind':'input','id':invocation,'path':str(root),'root':{'dev':s.st_dev,'ino':s.st_ino},'manifest_sha256':hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()}

def check_input_ref(ref,expected,allowed_root):
 try:
  if not isinstance(ref,dict) or set(ref)!={'owner','kind','id','path','root','manifest_sha256'} or ref['owner']!='E' or ref['kind']!='input':return False
  root=Path(ref['path']);s=root.lstat()
  if not stat.S_ISDIR(s.st_mode) or not root.resolve().is_relative_to(Path(allowed_root).resolve()) or {'dev':s.st_dev,'ino':s.st_ino}!=ref['root']:return False
  if set(p.name for p in root.iterdir())!={'events.jsonl','invocation.json','execution-targets.json','manifest.json'}:return False
  for p in root.iterdir():
   if not stat.S_ISREG(p.lstat().st_mode):return False
  raw=(root/'manifest.json').read_bytes()
  if hashlib.sha256(raw).hexdigest()!=ref['manifest_sha256']:return False
  manifest=json.loads(raw)
  if manifest['fixture_schema']!='e-authority-for-r/v1' or manifest['invocation_id']!=ref['id'] or manifest['complete'] is not True:return False
  if expected and canonical(expected)!=canonical({'invocation_id':ref['id'],'binding':manifest['binding']}):return False
  if set(manifest['files'])!={'events.jsonl','invocation.json','execution-targets.json'}:return False
  if canonical(json.loads((root/'invocation.json').read_bytes()))!=canonical({'invocation_id':ref['id'],'binding':manifest['binding']}):return False
  if canonical(json.loads((root/'execution-targets.json').read_bytes()))!=canonical(manifest['binding']['execution_targets']):return False
  for name,item in manifest['files'].items():
   raw=(root/name).read_bytes()
   if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:return False
  return True
 except (OSError,ValueError,KeyError,TypeError):return False
