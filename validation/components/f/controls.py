"""G3 verifier rejection controls only, not a substitute F implementation."""
import copy, json, os, stat, sys, hashlib, datetime, subprocess
from pathlib import Path
from observer import snapshot, assert_tree, assert_ref, git_archive, manifest_for, assert_bundle
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'validation/components/f/evidence'/sys.argv[1];OUT.mkdir(parents=True,exist_ok=False)
p=OUT/'observed';p.mkdir();(p/'ignored').write_bytes(b'REQUIRED\x00');(p/'empty').mkdir();(p/'normal').write_bytes(b'N');(p/'normal').chmod(0o640)
expected=snapshot(p);(OUT/'expected.json').write_text(json.dumps(expected,indent=2))
results=[]
def test(name,operation,rejected):
 try:operation();actual=False;error=None
 except (AssertionError,ValueError,FileNotFoundError) as e:actual=True;error={'type':type(e).__name__,'message':str(e)}
 results.append({'id':name,'expected_rejected':rejected,'actual_rejected':actual,'pass':rejected==actual,'error':error})
test('complete_fixture',lambda:assert_tree(p,expected),False)
def restore_existing_metadata():
 for name,e in expected['entries'].items():
  q=p/name
  if q.exists():q.chmod(e['mode']);os.utime(q,ns=(e['mtime_ns'],e['mtime_ns']),follow_symlinks=False)
def isolated_missing(name):
 actual=snapshot(p);missing=sorted(set(expected['entries'])-set(actual['entries']));extra=sorted(set(actual['entries'])-set(expected['entries']));changed=sorted(k for k in set(actual['entries']) & set(expected['entries']) if actual['entries'][k]!=expected['entries'][k])
 assert missing==[name] and not extra and not changed and actual['hardlink_groups']==expected['hardlink_groups']
 (OUT/(name+'-isolated-difference.json')).write_text(json.dumps({'missing':missing,'extra':extra,'changed_common_entries':changed,'actual':actual},indent=2))
(p/'ignored').rename(OUT/'held-ignored');restore_existing_metadata();isolated_missing('ignored');test('missing_ignored',lambda:assert_tree(p,expected),True);(OUT/'held-ignored').rename(p/'ignored');restore_existing_metadata();test('restored_after_ignored',lambda:assert_tree(p,expected),False)
(p/'empty').rmdir();restore_existing_metadata();isolated_missing('empty');test('missing_empty_directory',lambda:assert_tree(p,expected),True);(p/'empty').mkdir();restore_existing_metadata();test('restored_after_empty',lambda:assert_tree(p,expected),False)
# Restore the exact fixture timestamps, not a revised oracle.
for name,e in expected['entries'].items():os.utime(p/name,ns=(e['mtime_ns'],e['mtime_ns']),follow_symlinks=False)
(p/'normal').chmod(0o644);test('wrong_mode',lambda:assert_tree(p,expected),True);(p/'normal').chmod(0o640)
ref={'resource_id':'S1','domain':'surface','git_ref':'refs/lore/versions/v1','archive_sha256':'a'*64,'manifest_sha256':'b'*64,'profile':'host-v1'}
test('good_binding',lambda:assert_ref(ref,'S1','surface'),False)
test('wrong_domain',lambda:assert_ref(ref,'S1','workspace'),True)
incomplete=dict(ref);incomplete.pop('archive_sha256');test('missing_observation',lambda:assert_ref(incomplete,'S1','surface'),True)
test('missing_actual_tree',lambda:assert_tree(OUT/'does-not-exist',expected),True)
facility=ROOT/'validation/components/f/evidence/facilities-001';fac=json.loads((facility/'result.json').read_text())['cases'];good={'git_ref':fac['FP02']['rooted_commit'],'archive_sha256':fac['FP01']['archive_sha256']}
test('actual_rooted_archive',lambda:git_archive(facility/'fixture',good),False)
bad=dict(good);bad['archive_sha256']='0'*64;test('corrupt_archive_binding',lambda:git_archive(facility/'fixture',bad),True)

# Known bundle fixture created directly with existing Git; this is not a FileStore substitute.
bundle_root=OUT/'bundle-control';bundle_root.mkdir();empty=bundle_root/'empty-template';empty.mkdir()
git_env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_AUTHOR_NAME':'oracle fixture','GIT_AUTHOR_EMAIL':'fixture@invalid','GIT_COMMITTER_NAME':'oracle fixture','GIT_COMMITTER_EMAIL':'fixture@invalid'}
subprocess.run(['git','init','--bare','--template='+str(empty),str(bundle_root/'versions.git')],env=git_env,capture_output=True,check=True)
def fixture_git(*args,data=None):
 p1=subprocess.run(['git','--git-dir='+str(bundle_root/'versions.git'),'-c','core.hooksPath=/dev/null',*args],env=git_env,input=data,capture_output=True,check=True,timeout=15);return p1.stdout.strip().decode()
source_tree=json.loads((facility/'source-observation.json').read_text());archive_data=(facility/'complete.tar').read_bytes();archive_path=bundle_root/'archive.tar';archive_path.write_bytes(archive_data)
manifest=manifest_for(source_tree,'S1','surface');manifest_path=bundle_root/'manifest.json';manifest_path.write_text(json.dumps(manifest,sort_keys=True))
def fixture_bundle(name,mp):
 ab=fixture_git('hash-object','--no-filters','-w','--stdin',data=archive_data);mb=fixture_git('hash-object','--no-filters','-w','--stdin',data=mp.read_bytes())
 tree=fixture_git('mktree',data=('100644 blob '+ab+'\tarchive.tar\n100644 blob '+mb+'\tmanifest.json\n').encode().decode('unicode_escape').encode())
 commit=fixture_git('commit-tree',tree,'-m',name);ref='refs/lore/versions/'+name;fixture_git('update-ref',ref,commit)
 return {'version_ref':{'resource_id':'S1','domain':'surface','profile':'host-v1','git_ref':ref,'archive_sha256':hashlib.sha256(archive_data).hexdigest(),'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest()},'archive_path':str(archive_path),'manifest_path':str(mp)}
bundle=fixture_bundle('known-good',manifest_path)
test('actual_complete_bundle',lambda:assert_bundle(bundle,bundle_root,source_tree,'S1','surface'),False)
for field in ['archive_path','manifest_path']:
 absent=copy.deepcopy(bundle);absent[field]=str(bundle_root/('absent-'+field));test('missing_'+field,lambda:assert_bundle(absent,bundle_root,source_tree,'S1','surface'),True)
bad=copy.deepcopy(bundle);bad['version_ref']['manifest_sha256']='0'*64;test('wrong_manifest_hash',lambda:assert_bundle(bad,bundle_root,source_tree,'S1','surface'),True)
forged=copy.deepcopy(manifest);forged['tree']['entries']['ignored-input']['size']+=1;mp=bundle_root/'forged-manifest.json';mp.write_text(json.dumps(forged,sort_keys=True));forged_bundle=fixture_bundle('forged-member-with-valid-hash',mp)
test('forged_member_valid_hash',lambda:assert_bundle(forged_bundle,bundle_root,source_tree,'S1','surface'),True)
(OUT/'bundle-controls.json').write_text(json.dumps({'known_good':bundle,'forged_with_consistent_hash':forged_bundle,'independent_source':str(facility/'source-observation.json')},indent=2))

result={'scope':'G3 independent oracle controls only','registered_protocol_sha256':hashlib.sha256((ROOT/'design/g3/f/cases.json').read_bytes()).hexdigest(),'observer_sha256':hashlib.sha256((Path(__file__).parent/'observer.py').read_bytes()).hexdigest(),'controls_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'results':results,'passed':all(x['pass'] for x in results),'count':len(results)}
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
