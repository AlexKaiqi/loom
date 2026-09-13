"""Freeze the exact existing Node/Pi projection, wire source and mechanism probe."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'validation/components/x'));from source_closure import AUDIT

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def main():
 a=argparse.ArgumentParser();a.add_argument('--batch',required=True);a.add_argument('--pi-manifest',type=Path);args=a.parse_args();assert args.batch.replace('-','').isalnum()
 out=HERE/'evidence'/args.batch;out.mkdir(parents=True,exist_ok=False);projection=out/'projection';ws=projection/'opt/lore';ws.mkdir(parents=True);rows=[];links=[]
 manifest=json.loads((ROOT/'design/g3/x-node-profile/dependencies.json').read_text());gate=json.loads((ROOT/'design/g4/provider-gate.json').read_text());assert gate['status']=='PASS'
 derived=json.loads(args.pi_manifest.read_text()) if args.pi_manifest else None;derived_files={row['path']:row for row in derived['files']} if derived else {}
 def cp(src,dst,wanted=None,mode=None):
  src=Path(src);dst.parent.mkdir(parents=True,exist_ok=True);assert not src.is_symlink();raw=src.read_bytes();digest=hashlib.sha256(raw).hexdigest();assert wanted in (None,digest);dst.write_bytes(raw)
  if mode is not None:os.chmod(dst,mode)
  rows.append({'original':str(src),'copy':str(dst),'sha256':digest})
 for entry in manifest['files']:
  src=Path(entry['source']);wanted=entry['sha256']
  if derived and src.is_relative_to(Path(derived['upstream'])):
   rel=str(src.relative_to(Path(derived['upstream'])));row=derived_files[rel];assert row['original_sha256']==wanted;src=Path(derived['derived'])/rel;wanted=row['derived_sha256']
  cp(src,projection/entry['target'].lstrip('/'),wanted,entry['mode']&~0o222)
 for entry in manifest['links']:
  p=projection/entry['target'].lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);assert os.readlink(entry['source'])==entry['link'];p.symlink_to(entry['link']);links.append({'original':entry['source'],'copy':str(p),'target':entry['link']})
 for file,digest in gate['implementation'].items():p=Path(file);cp(p,ws/p.relative_to(ROOT),digest)
 extras=[*HERE.glob('*.py'),*HERE.glob('*.mts'),*HERE.glob('*.mjs'),ROOT/'validation/components/s/oracle.py',ROOT/'validation/components/provider/collector.py',ROOT/'validation/components/x/source_closure.py',ROOT/'design/g3/provider/cases.json',*list((ROOT/'design/g3/provider/fixtures').glob('*.raw')),ROOT/'design/g3/x-node-profile/dependencies.json',ROOT/'design/g4/provider-gate.json',ROOT/'design/g4/s-wire-pi-preparation/protocol.json',ROOT/'research/pi/tsconfig.json']
 if args.pi_manifest:extras.extend([args.pi_manifest,Path(derived['patch']['path'])])
 for p in extras:cp(p,ws/p.relative_to(ROOT))
 config=json.loads((ROOT/'research/pi/tsconfig.json').read_text());config['compilerOptions']['baseUrl']=str(ws/'research/repos/pi');save(ws/'tsconfig.json',config);(ws/'sitecustomize.py').write_text(AUDIT);generated={str(ws/'tsconfig.json'):sha(ws/'tsconfig.json'),str(ws/'sitecustomize.py'):sha(ws/'sitecustomize.py')}
 record={'scope':'WIRE_PI_MECHANISM_PREPARATION_ONLY','inputs':rows,'links':links,'generated':generated};save(out/'before.json',record);argv=[sys.executable,'-B',str(ws/'validation/components/s_wire_pi/bridge_probe.py'),str(out/'actual')];record['argv']=argv
 with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:p=subprocess.run(argv,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws),'PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout,stderr=stderr,timeout=60)
 record['exit']=p.returncode;record['source_unchanged']=all(sha(x[k])==x['sha256'] for x in rows for k in ('original','copy')) and all(sha(p)==h for p,h in generated.items()) and all(os.readlink(x[k])==x['target'] for x in links for k in ('original','copy'))
 known={x['copy']:x['sha256'] for x in rows}|generated;events=[json.loads(line) for path in (out/'actual').glob('*.node-imports.jsonl') for line in path.read_text().splitlines()];record['node_loaded_events']=events;record['all_node_loaded_files_bound']=bool(events) and all(known.get(e['path'])==e['sha256'] for e in events)
 # Python audit locates its own snapshot parent by source_closure's original convention.
 audit_files=list(out.rglob('imports/*.jsonl'));py=[json.loads(line) for path in audit_files for line in path.read_text().splitlines()];execs=[e for e in py if e['kind']=='exec'];record['python_execution']=py;record['all_python_executed_sources_bound']=bool(execs) and all(known.get(e['filename'])==e['sha256'] for e in execs)
 record['status']='PASS_PREPARATION_ONLY' if p.returncode==0 and record['source_unchanged'] and record['all_node_loaded_files_bound'] and record['all_python_executed_sources_bound'] else 'FAIL';save(out/'assessment.json',record);print(json.dumps({k:record[k] for k in ('status','exit','source_unchanged','all_node_loaded_files_bound','all_python_executed_sources_bound')}));return 0 if record['status']=='PASS_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
