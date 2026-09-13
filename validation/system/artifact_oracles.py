"""Independent business artifact checks. Never imported by Runtime or Harness."""
import hashlib,json,stat
from pathlib import Path
from markdown_it import MarkdownIt
class ArtifactError(ValueError):pass

def read_file(path):
 p=Path(path)
 if not stat.S_ISREG(p.lstat().st_mode):raise ArtifactError('not an actual ordinary file')
 with p.open('rb') as f:data=f.read(65537)
 if len(data)>65536:raise ArtifactError('artifact observation budget exceeded')
 return data

def strict_json(data):
 def obj(pairs):
  out={}
  for k,v in pairs:
   if k in out:raise ArtifactError('duplicate JSON key')
   out[k]=v
  return out
 def constant(s):raise ArtifactError('nonfinite JSON number')
 try:return json.loads(data.decode('utf-8'),object_pairs_hook=obj,parse_constant=constant)
 except (ValueError,UnicodeError) as e:raise ArtifactError(str(e)) from e

def sum_files(numbers_path,report_path,notes_path,report_location):
 raw={name:read_file(path) for name,path in [('input',numbers_path),('report',report_path),('notes',notes_path)]}
 numbers=strict_json(raw['input']);report=strict_json(raw['report'])
 if not isinstance(numbers,list) or len(numbers)>4096 or any(type(x) is not int or abs(x)>1000000 for x in numbers):raise ArtifactError('original input outside fixed integer workload')
 if not isinstance(report,dict) or type(report.get('sum')) is not int:raise ArtifactError('report sum must be a JSON integer')
 expected=sum(numbers)
 if report['sum']!=expected:raise ArtifactError('actual report differs from independently read original input')
 try:notes=raw['notes'].decode('utf-8')
 except UnicodeError as e:raise ArtifactError('notes UTF-8 invalid') from e
 # CommonMark inline token children contain actual links; image alt children/code/html are not link nodes.
 links=[child.attrGet('href') for block in MarkdownIt('commonmark').parse(notes) if block.type=='inline' for child in (block.children or []) if child.type=='link_open']
 if report_location not in links:raise ArtifactError('notes lacks precise actual report link')
 return {'passed':True,'assertions':[{'id':'original-integer-input','passed':True},{'id':'actual-sum','passed':True},{'id':'actual-notes-link','passed':True}],'facts':{'count':len(numbers),'expected_sum':expected,'actual_sum':report['sum'],'report_location':report_location,'markdown_links':links,'markdown_profile':'markdown-it-py/commonmark','files':{k:{'sha256':hashlib.sha256(v).hexdigest(),'size':len(v)} for k,v in raw.items()},'scope':'artifact content only; physical/versioned integration is a separate mandatory check'}}
