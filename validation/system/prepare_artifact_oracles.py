"""Finite verifier controls, never production M/X evidence."""
from pathlib import Path
import hashlib,json,sys,platform
from importlib.metadata import distribution
from artifact_oracles import sum_files,ArtifactError
ROOT=Path(__file__).resolve().parents[2];out=Path(__file__).parent/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
dependency_manifest=ROOT/'validation/system/dependencies/markdown-001/manifest.json'
lock=json.loads(dependency_manifest.read_text());dependency_observation={'python':platform.python_version(),'executable':sys.executable,'packages':[]}
for package in lock['packages']:
 installed=distribution(package['distribution']);actual={'distribution':package['distribution'],'version':installed.version,'sources':{}}
 if installed.version!=package['version']:raise RuntimeError('parser dependency version differs')
 for source in package['sources']:
  path=Path(installed.locate_file(source['relative']));value=hashlib.sha256(path.read_bytes()).hexdigest()
  if value!=source['sha256']:raise RuntimeError('parser dependency source differs')
  actual['sources'][str(path)]=value
 dependency_observation['packages'].append(actual)
inputs=json.loads((ROOT/'design/g3/system/inputs.json').read_text())['integer_inputs'];results=[]
def case(name,numbers,report,notes,want):
 d=out/name;d.mkdir();(d/'input.json').write_bytes(numbers);(d/'report.json').write_bytes(report);(d/'notes.md').write_bytes(notes)
 try:detail=sum_files(d/'input.json',d/'report.json',d/'notes.md','/artifacts/report.json');accepted=True
 except (ArtifactError,FileNotFoundError) as e:accepted=False;detail={'error':str(e)}
 results.append({'id':name,'expected_accept':want,'accepted':accepted,'pass':accepted==want,'detail':detail})
for name,values in inputs.items():case(name,json.dumps(values).encode(),json.dumps({'sum':sum(values)}).encode(),b'[report](/artifacts/report.json)',True)
case('wrong-result',b'[2,3,5]',b'{"sum":999,"status":"PASS"}',b'[report](/artifacts/report.json)',False)
case('wrong-link',b'[2,3,5]',b'{"sum":10}',b'[report](/other/report.json)',False)
case('plain-success',b'[2,3,5]',b'{"sum":10}',b'Success, report written /artifacts/report.json',False)
case('changed-original',b'[2,3,6]',b'{"sum":10}',b'[report](/artifacts/report.json)',False)
case('float-result',b'[2,3,5]',b'{"sum":10.0}',b'[report](/artifacts/report.json)',False)
case('bool-input',b'[true]',b'{"sum":1}',b'[report](/artifacts/report.json)',False)
case('duplicate-key',b'[2,3,5]',b'{"sum":999,"sum":10}',b'[report](/artifacts/report.json)',False)
case('nonfinite',b'[NaN]',b'{"sum":10}',b'[report](/artifacts/report.json)',False)
case('partial',b'[2,3,5]',b'{"sum":10',b'[report](/artifacts/report.json)',False)
case('oversize',b'[2,3,5]',b'{"sum":10}',b'[report](/artifacts/report.json)'+b' '*65537,False)
case('inline-code-link',b'[2,3,5]',b'{"sum":10}',b'`[report](/artifacts/report.json)`',False)
case('fenced-code-link',b'[2,3,5]',b'{"sum":10}',b'```text\n[report](/artifacts/report.json)\n```',False)
case('escaped-link',b'[2,3,5]',b'{"sum":10}',b'\\[report](/artifacts/report.json)',False)
case('indented-code-link',b'[2,3,5]',b'{"sum":10}',b'    [report](/artifacts/report.json)',False)
case('html-comment-link',b'[2,3,5]',b'{"sum":10}',b'<!--[report](/artifacts/report.json)-->',False)
case('reference-style-link',b'[2,3,5]',b'{"sum":10}',b'[report][r]\n\n[r]: /artifacts/report.json',True)
case('angle-destination-link',b'[2,3,5]',b'{"sum":10}',b'[report](</artifacts/report.json>)',True)
missing=out/'missing-file';missing.mkdir()
try:sum_files(missing/'input',missing/'report',missing/'notes','/artifacts/report.json');ok=False
except FileNotFoundError:ok=True
results.append({'id':'missing-file','pass':ok})
r={'scope':'G3 artifact oracle preparation, not system execution','status':'PASS' if all(x['pass'] for x in results) else 'FAIL','checks':results,'dependency_observation':dependency_observation,'source_hashes':{str(q.relative_to(ROOT)):hashlib.sha256(q.read_bytes()).hexdigest() for q in [Path(__file__),Path(__file__).with_name('artifact_oracles.py'),ROOT/'design/g3/system/artifact-oracle-contract.md',ROOT/'design/g3/system/inputs.json',dependency_manifest,ROOT/'validation/system/requirements.txt',ROOT/'validation/system/sa01-repair-protocol.md']}};(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'checks':len(results)}));sys.exit(0 if r['status']=='PASS' else 1)
