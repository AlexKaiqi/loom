"""Non-Docker prerequisite controls: exact projected dependency copies, never product."""
from pathlib import Path,PurePosixPath
import argparse,copy,hashlib,json,os,stat,time
ROOT=Path(__file__).resolve().parents[3]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for by in iter(lambda:f.read(1024*1024),b''):h.update(by)
 return h.hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def target(root,name):
 p=PurePosixPath(name)
 if not p.is_absolute() or '..' in p.parts or not (name.startswith('/opt/node/') or name.startswith('/opt/lore/')):raise ValueError('outside fixed dependency namespace')
 return root.joinpath(*p.parts[1:])
def verify(root,manifest):
 expected=set();errors=[]
 for row in manifest['files']:
  p=target(root,row['target']);expected.add(p.relative_to(root).as_posix())
  if p.is_symlink() or not p.is_file() or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256'] or p.stat().st_mode&0o222:errors.append(row['target'])
 for row in manifest['links']:
  p=target(root,row['target']);expected.add(p.relative_to(root).as_posix())
  if not p.is_symlink() or os.readlink(p)!=row['link'] or p.resolve()!=target(root,row['resolved_target']).resolve():errors.append(row['target'])
 actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
 if expected!=actual:errors.append('full member set differs')
 if errors:raise ValueError('invalid readonly projection: '+repr(errors[:10]))
 return {'files':len(manifest['files']),'links':len(manifest['links']),'bytes':sum(x['bytes'] for x in manifest['files']),'exact_member_set':True}
def main():
 a=argparse.ArgumentParser();a.add_argument('--batch',required=True);args=a.parse_args()
 if not args.batch.replace('-','').isalnum():a.error('fresh batch')
 out=Path(__file__).parent/'evidence'/args.batch;out.mkdir(parents=True,exist_ok=False);root=out/'projection';root.mkdir();design=ROOT/'design/g3/x-node-profile';manifest=json.loads((design/'dependencies.json').read_text());profile=json.loads((design/'profile.json').read_text())
 if sha(design/'dependencies.json')!=profile['dependency_manifest']['sha256']:raise ValueError('profile dependency source changed')
 report={'scope':'NON_DOCKER_PREPARATION_ONLY','started':time.time(),'cases':[],'inputs':{},'runtime_or_X_executed':False}
 for p in [Path(__file__),*design.glob('*.json'),design/'contract.md']:
  q=out/'inputs'/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());report['inputs'][str(p)]={'sha256':sha(p),'saved':str(q)}
 for row in manifest['files']:
  source=Path(row['source']);dest=target(root,row['target']);dest.parent.mkdir(parents=True,exist_ok=True)
  if source.is_symlink() or sha(source)!=row['sha256']:raise ValueError('original source drift '+str(source))
  with source.open('rb') as src,dest.open('xb') as dst:
   for by in iter(lambda:src.read(1024*1024),b''):dst.write(by)
  os.chmod(dest,row['mode']&~0o222)
 for row in manifest['links']:
  source=Path(row['source'])
  if os.readlink(source)!=row['link']:raise ValueError('original selected link drift')
  dest=target(root,row['target']);dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(row['link'])
 def check(name,fn,should_reject=False):
  try:result=fn();ok=not should_reject;error=None
  except ValueError as e:result=None;ok=should_reject;error=str(e)
  report['cases'].append({'id':name,'pass':ok,'expected_rejection':should_reject,'observation':result,'error':error});save(out/'assessment.json',report)
 check('actual-882-file-four-link-projection',lambda:verify(root,manifest))
 bad=copy.deepcopy(manifest);bad['files'][0]['sha256']='0'*64;check('wrong-actual-content-digest',lambda:verify(root,bad),True)
 bad=copy.deepcopy(manifest);bad['files'].pop();check('omitted-manifest-member',lambda:verify(root,bad),True)
 bad=copy.deepcopy(manifest);bad['links'][0]['resolved_target']='/etc';check('link-outside-dependency-namespace',lambda:verify(root,bad),True)
 bad=copy.deepcopy(manifest);bad['files'][0]['target']='/var/run/docker.sock';check('forbidden-host-socket-target',lambda:verify(root,bad),True)
 # Corrupt one actual small copied source in place, retain original bytes, then restore.
 item=min(manifest['files'],key=lambda x:x['bytes']);file=target(root,item['target']);original=file.read_bytes();(out/'actual-original.bin').write_bytes(original);os.chmod(file,0o600);bad_bytes=bytearray(original);bad_bytes[0]^=1;file.write_bytes(bad_bytes);os.chmod(file,item['mode']&~0o222)
 check('same-length-actual-copy-corruption',lambda:verify(root,manifest),True);(out/'actual-corrupt.bin').write_bytes(file.read_bytes());os.chmod(file,0o600);file.write_bytes(original);os.chmod(file,item['mode']&~0o222)
 check('restored-original-full-projection',lambda:verify(root,manifest))
 report['status']='PASS_PREPARATION_ONLY' if len(report['cases'])==7 and all(x['pass'] for x in report['cases']) else 'FAIL';report['finished']=time.time();report['remaining']='XN01-XN12 real Node/Pi/X/F/Engine observations UNVERIFIED; root owns Docker schedule.';save(out/'assessment.json',report);print(json.dumps({'status':report['status'],'cases':len(report['cases'])}));return 0 if report['status']=='PASS_PREPARATION_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
