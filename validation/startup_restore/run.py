"""Two original startup reentry stages around real R/F exchange; no Engine instance."""
from pathlib import Path
import argparse,copy,hashlib,json,os,shutil,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));HERE=Path(__file__).parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def load(p):return json.loads(Path(p).read_bytes())
def need(v,m):
 if not v:raise AssertionError(m)
def identity(p):
 s=Path(p).stat();return dict(dev=s.st_dev,ino=s.st_ino)
def host_bytes(root):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}

def reload_child(home,output):
 from lore_runtime.startup_assets import StartupAssets
 from lore_runtime.host_files import HostFiles
 from lore_control import ControlStore
 from lore_files import FileStore
 original=load(home/'fixture-original.json');control=None
 try:
  assets=StartupAssets(home/'host',original['config'])
  control=ControlStore(home/'R.sqlite',{'operator':dict(namespaces=['startup-test'],roles=['admin','runtime','submit'])})
  owner=HostFiles(control,assets.host);files=FileStore(home/'F',owner.authorization,owner.reference,limits=original['limits']);owner.files=files;control.reference_checker=owner.control_reference
  result=assets.build(files);need(result==original['build'],'fresh process changed original initial refs/host/config')
  current=control.resolve('operator','startup-test','original-workspace','read')
  reference=load(home/'publication.json')['F_query']['version_ref'] if (home/'publication.json').exists() else original['build']['initial_refs']['workspace_version_ref']
  view=owner.resolve(reference,'F-view',dict(registration=current));need(view['materialized']['root']==identity(home/'workspace'),'current view does not use actual R registered root')
  for name in ('harness_ref','capability_ref'):files.read_reference(result['initial_refs'][name],assets.host['authorization'])
  save(output,dict(status='PASS',pid=os.getpid(),source=__file__,build=result,current=current,view=view));return 0
 except BaseException as exc:
  save(output,dict(status='FAIL',pid=os.getpid(),error=repr(exc),traceback=traceback.format_exc()));return 1
 finally:
  if control is not None:control.close()

def fresh(home,out,label):
 destination=out/(label+'.json');command=[sys.executable,'-B',str(Path(__file__)), '--reload',str(home),'--result',str(destination)]
 save(out/(label+'-command.json'),dict(argv=command,cwd=str(ROOT)))
 with (out/(label+'.stdout')).open('xb') as stdout,(out/(label+'.stderr')).open('xb') as stderr:
  proc=subprocess.run(command,cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE='1'),stdout=stdout,stderr=stderr,timeout=45)
 result=load(destination);need(result['pid']!=os.getpid(),'not a fresh process');return proc.returncode,result

class PublicationFixture:
 """Only source/stop authorization is controlled; R/F installation is real."""
 def __init__(self,f):
  from lore_runtime.file_publication import FilePublication
  self.f=f;self.calls=[];self.exchanges=0;self.oldauth=f.files.authorization_checker;self.oldref=f.files.reference_checker;self.oldr=f.control.reference_checker
  self.resource=f.control.resolve('operator','startup-test','original-workspace','write');self.base=f.result['initial_refs']['workspace_version_ref'];self.grant=f.assets.host['authorization']
  draft=Path(f.assets.host['artifact_root'])/'publication-source';shutil.copytree(f.root/'workspace',draft);(draft/'numbers.json').write_text('[7,11]\n')
  bundle=f.assets._capture(f.files,draft,'startup-restore-draft','workspace');self.archive=dict(path=bundle['archive_path'],bytes=Path(bundle['archive_path']).stat().st_size,sha256=sha(bundle['archive_path']))
  self.binding=dict(resource_id=self.resource['id'],domain=self.resource['kind'],path=self.resource['path'],root=identity(self.resource['path']),revision=self.resource['revision'],authorization=self.grant)
  self.source=dict(owner='no-Engine-source-fixture',original_execution_ref=dict(execution_id='fixture-publish',object_generation=1),archive_ref=self.archive)
  self.stop=dict(owner='no-Engine-stop-fixture',execution_id='fixture-publish',generation=1)
  self.pub=FilePublication(f.control,f.files,self.stopped)
  f.files.authorization_checker=self.auth;f.files.reference_checker=self.ref;f.control.reference_checker=self.rref
  f.files.checkpoint=self.checkpoint
  self.output=f.files.import_archive('restore-import',self.binding,self.archive['path'],self.source,self.base,'host-v1')
  self.material=f.files.materialize('restore-stage',self.output['version_ref'],str(Path(f.assets.host['plan_root'])/'restore-stage'),self.grant)
  self.args=dict(principal='operator',namespace='startup-test',install_id='restore-install',resource=self.resource,base_ref=self.base,materialization_request_id='restore-stage',stopped_ref=self.stop,authorization=self.grant)
 def checkpoint(self,label,facts):
  self.calls.append(dict(owner='actual-F',label=label,facts=facts))
  if label=='after_exchange_before_record':self.exchanges+=1
 def auth(self,ref,purpose,ctx):
  if purpose=='import_archive':return ref==self.grant and ctx['binding']==self.binding and ctx['base_ref']==self.base and ctx['archive']==self.archive and ctx['source_ref']==self.source
  if purpose=='install':return ref==self.grant and self.pub.file_reference(ctx['intent']['intent_ref'],'intent',ctx) and self.pub.file_reference(ctx['stopped_ref'],'stop',ctx)
  return self.oldauth(ref,purpose,ctx)
 def ref(self,ref,purpose,ctx):
  if purpose=='source':return ref==self.source and ctx['archive']==self.archive and ctx['base_ref']==self.base and ctx['binding']==self.binding
  if purpose in ('intent','stop'):return self.pub.file_reference(ref,purpose,ctx)
  return self.oldref(ref,purpose,ctx)
 def rref(self,ref,purpose,ctx):
  if purpose=='base':return ref==self.base and ctx==dict(resource_id=self.resource['id']) and bool(self.f.files.versions.load(ref))
  if purpose in ('staged','stopped','installation','published'):return self.pub.control_reference(ref,purpose,ctx)
  return self.oldr(ref,purpose,ctx)
 def stopped(self,ref,purpose,scope):
  self.calls.append(dict(owner='NO_ENGINE_fixture',ref=ref,purpose=purpose,scope=scope))
  exact=dict(principal='operator',namespace='startup-test',resource=self.resource,base_ref=self.base,execution_id='fixture-publish',generation=1,materialization_request_id='restore-stage',materialization=self.material)
  return ref==self.stop and purpose=='stopped' and all(scope.get(k)==v for k,v in exact.items()) and scope['provenance']['source_ref']==self.source and sha(self.archive['path'])==self.archive['sha256']

def worker(out):
 from lore_runtime.startup_assets import StartupAssets
 from validation.startup_assets_probe import Fixture
 f=None;rows=[]
 try:
  f=Fixture(out/'actual',StartupAssets);save(f.root/'fixture-original.json',dict(config=f.config,build=f.result,limits=f.files.limits))
  oldroot=identity(f.root/'workspace');oldrefs=copy.deepcopy(f.result);oldhost=sha(f.root/'host/host.json');oldinputs=sha(f.root/'host/startup-inputs.json')
  rc,first=fresh(f.root,out,'before-install-fresh');need(rc==0,'unchanged original startup reentry failed');rows.append(dict(id='SR01',status='PASS',fresh=first))
  fixture=PublicationFixture(f);stageroot=identity(fixture.material['path']);publication=fixture.pub.publish(**fixture.args);save(f.root/'publication.json',publication)
  current=f.control.resolve('operator','startup-test','original-workspace','read');view=f.owner.resolve(fixture.output['version_ref'],'F-view',dict(registration=current))
  need(fixture.exchanges==1 and identity(f.root/'workspace')==stageroot and identity(fixture.material['path'])==oldroot,'not one actual inode exchange')
  need(current['revision']==2 and {k:current[k] for k in ('dev','ino')}==stageroot,'R did not retain current installed inode')
  need(list(f.control.db.execute('SELECT * FROM holders'))==[],'original holder retained after successful publication')
  need((f.root/'workspace/numbers.json').read_bytes()==b'[7,11]\n' and (Path(fixture.material['path'])/'numbers.json').read_bytes()==b'[2,3,5]\n','original/current ordinary bytes lost')
  need(f.files.versions.load(fixture.output['version_ref'])[0]==Path(fixture.archive['path']).read_bytes(),'new F archive differs from actual imported bytes')
  need(f.files.versions.load(oldrefs['initial_refs']['workspace_version_ref'])[2]['numbers.json']==b'[2,3,5]\n','old initial F bytes lost')
  save(out/'actual-installation.json',dict(publication=publication,old_root=oldroot,new_root=stageroot,current=current,HostFiles_current_view=view,actual_exchange_count=fixture.exchanges,authority_scope='NoEngine source/stop fixture; actual R/F/Git/install/SQL',calls=fixture.calls))
  try:f.assets.build(f.files);old_object={'unexpected':'accepted'}
  except Exception as exc:old_object=dict(error=repr(exc),code=getattr(exc,'code',None))
  rc,second=fresh(f.root,out,'after-install-fresh');need(sha(f.root/'host/host.json')==oldhost and sha(f.root/'host/startup-inputs.json')==oldinputs,'failed/reloaded startup rewrote immutable ownership')
  rows.append(dict(id='SR02',status='PASS' if rc==0 else 'FAIL',old_object_build=old_object,fresh=second,original_host_inputs_unchanged=True))
 except BaseException as exc:rows.append(dict(id='SETUP_OR_EXECUTION',status='FAIL',error=repr(exc),traceback=traceback.format_exc()))
 finally:
  if f is not None:f.close()
 save(out/'assessment.json',rows);passed=len(rows)==2 and all(x['status']=='PASS' for x in rows);save(out/'result.json',dict(status='PASS_STARTUP_REENTRY_NOENGINE_ONLY' if passed else 'FAIL',actual_stages=len(rows),checks=[dict(id=x['id'],status=x['status']) for x in rows]));return 0 if passed else 1

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch');ap.add_argument('--worker',action='store_true');ap.add_argument('--reload');ap.add_argument('--result');a=ap.parse_args()
 if a.reload:return reload_child(Path(a.reload),Path(a.result))
 if a.worker:return worker(Path(a.batch))
 need(Path(a.batch).name==a.batch,'invalid batch');out=HERE/'evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);work=out/'workspace';work.mkdir()
 from validation.startup_assets_probe import CODES
 paths=[Path(__file__).relative_to(ROOT),Path('validation/startup_restore/contract.md'),Path('validation/startup_assets_probe.py'),Path('design/g3/system/startup-assets.md'),*[Path(n) for n in CODES]]
 for package in ['lore_runtime','lore_control','lore_files','lore_events','lore_execution','lore_session']:paths += [p.relative_to(ROOT) for p in (ROOT/package).glob('*') if p.is_file() and p.suffix in ('.py','.json')]
 host=[Path('design/g3/x-node-profile')/n for n in ('profile.json','request-template.json')]+[Path('validation/components/x_node_profile/evidence/node-independent-full-001/actual/shared/dependencies-manifest.json')];paths+=host
 before={str(p):sha(ROOT/p) for p in paths}
 for p in paths:(work/p).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p,work/p)
 (work/'original-host').mkdir()
 for p in host:shutil.copy2(work/p,work/'original-host'/p.name)
 save(out/'source-before.json',before);command=[sys.executable,'-B',str(work/'validation/startup_restore/run.py'),'--worker','--batch',str(out)];save(out/'command.json',dict(argv=command,cwd=str(work)))
 with (out/'stdout').open('xb') as stdout,(out/'stderr').open('xb') as stderr:proc=subprocess.run(command,cwd=work,env=dict(os.environ,PYTHONPATH=str(work),PYTHONDONTWRITEBYTECODE='1'),stdout=stdout,stderr=stderr,timeout=120)
 result=load(out/'result.json') if (out/'result.json').exists() else dict(status='FAIL',actual_stages=0,error='missing worker result')
 result.update(exit_code=proc.returncode,source_unchanged=all(sha(ROOT/p)==v for p,v in before.items()),copied_source=all(sha(work/p)==v for p,v in before.items()));save(out/'result.json',result);print(json.dumps(result));return proc.returncode if result['source_unchanged'] and result['copied_source'] else 1
if __name__=='__main__':raise SystemExit(main())
