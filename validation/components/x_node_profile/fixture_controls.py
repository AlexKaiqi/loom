from pathlib import Path
import argparse,json
from artifacts import canonical,save,snapshot,strict_json,sha_bytes
from fixtures import dependencies,Fixture,tree

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
 rows=[]
 try:
  dep=dependencies(out/'shared')
  manifest=strict_json(Path(dep['manifest_ref']['path']).read_bytes());entries=manifest['entries']
  assert sum(v['kind']=='file'for v in entries.values())==883
  assert sum(v['kind']=='symlink'for v in entries.values())==4
  assert 'lore/config/tsconfig.json'in entries and tree(Path(dep['source']['path']))==entries
  rows.append({'id':'FIX01','pass':True,'actual_dependency_files':883,'original_links':4,'formal_generated_tsconfig_present':True})
  fixture=Fixture(out/'normal',dep)
  snap=snapshot(fixture.snapshot_ref,fixture.expected_scope)
  assert not snap['files'] and fixture.request['base_version']==sha_bytes(canonical(fixture.snapshot_ref))
  assert all('@fixture.'not in str(value)for value in [fixture.request,fixture.authority,fixture.config])
  assert fixture.request['command_argv'][4]=='channel'and fixture.config['transport_principal']=='trusted-S'
  for mount in fixture.mounts:
   original=strict_json(Path(mount['manifest_ref']['path']).read_bytes());assert tree(Path(mount['source']['path']))==original['entries']
  assert all(row['accepted']for row in fixture.f.calls)
  rows.append({'id':'FIX02','pass':True,'actual_F_calls':len(fixture.f.calls),'request_digest':sha_bytes(canonical(fixture.request))})
  large=Fixture(out/'large',dep,'read-files',large=True)
  workspace=Path(large.mounts[3]['source']['path']);members=tree(workspace)
  assert len(members)==578 and sum(v['kind']=='file'for v in members.values())==513
  assert len((workspace/'workspace.diff').read_bytes().splitlines())==4096
  assert all(row['accepted']for row in large.f.calls)
  rows.append({'id':'FIX03','pass':True,'actual_F_members':len(members),'regular_files':513,'diff_lines':4096})
  status='PASS_FIXTURE_PREPARATION_ONLY';error=None
 except Exception as exc:status='FAIL';error=repr(exc)
 report={'status':status,'checks':rows,'error':error,'scope':'Actual copied F and Node dependency files; no X/Node execution. Three fixture construction checks, not XN12 or S pass.'};save(out/'assessment.json',report);print(json.dumps({'status':status,'checks':len(rows),'error':error}));return 0 if status=='PASS_FIXTURE_PREPARATION_ONLY'else 1
if __name__=='__main__':raise SystemExit(main())
