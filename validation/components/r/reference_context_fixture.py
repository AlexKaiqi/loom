"""Independent owner context fixtures; never imported by product R."""
import hashlib,json
from pathlib import Path

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def save_context(refroot,ref,purpose,context):
 root=Path(refroot).parent/'owner-contexts';root.mkdir(exist_ok=True)
 raw=canonical({'reference':ref,'purpose':purpose,'context':context})
 (root/(ref['id']+'.'+purpose+'.json')).write_bytes(raw)
def matches_context(refroot,ref,purpose,expected):
 if expected is None:return True
 try:
  p=Path(refroot).parent/'owner-contexts'/(ref['id']+'.'+purpose+'.json');record=json.loads(p.read_bytes())
  return record['reference']==ref and record['purpose']==purpose and all(canonical(record['context'].get(k))==canonical(v) for k,v in expected.items())
 except (OSError,KeyError,ValueError,TypeError):return False
