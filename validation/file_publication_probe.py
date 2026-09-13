"""Six finite R/F publication cases; original X stop evidence is replayed, no Docker."""
import argparse, copy, hashlib, importlib, json, os, shutil, subprocess, sys, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'validation/components/x/evidence/independent-full-001/workspace/validation/components/x/evidence/actual/X016-0/f-handoff'
IDS = ['FP01','FP02','FP03','FP04','FP05','FP06']

def raw(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(value): return hashlib.sha256(value).hexdigest()
def load(path): return json.loads(Path(path).read_bytes())
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(json.dumps(value,indent=2,sort_keys=True).encode()+b'\n')
def require(value,message):
    if not value: raise AssertionError(message)
def ident(path):
    s=Path(path).lstat();return dict(dev=s.st_dev,ino=s.st_ino)
def snapshot(root):
    from lore_files.metadata import walk
    from lore_files.util import DEFAULT_LIMITS
    return walk(Path(root),DEFAULT_LIMITS)[0]
def expect_error(call,codes):
    try: call()
    except Exception as exc:
        require(getattr(exc,'code',None) in codes, 'wrong error: '+repr(exc))
        return dict(type=type(exc).__name__,code=exc.code,message=str(exc))
    raise AssertionError('invalid original input was accepted')

class Cut(BaseException): pass

class Fixture:
    def __init__(self,root,cls):
        self.root=Path(root);self.root.mkdir(parents=True)
        self.cls=cls;self.pub=None;self.exchanges=0;self.cut=None;self.calls=[]
        self.originals=ROOT/'originals'
        self.oldbase=load(self.originals/'base.json')
        self.originalstop=load(self.originals/'actual-stop.json')
        self.prepared=load(self.originals/'prepared-source.json')
        self.base=self.oldbase['bundle']['version_ref']
        self.binding=self.prepared['binding']
        self.principal='operator';self.namespace='publication-test'
        self.grant=dict(owner='trusted-publication-fixture',principal=self.principal,namespace=self.namespace,resource_id=self.base['resource_id'])
        proof=self.root/'original-X-stop.json';shutil.copy2(self.originals/'actual-stop.json',proof)
        fact=dict(path=str(proof),size=proof.stat().st_size,sha256=sha(proof.read_bytes()))
        self.stop=dict(owner='X-original-stop',execution_id=self.binding['execution_id'],generation=self.binding['object_generation'],original=fact,original_binding=self.binding)
        self.control_dir=self.root/'F';self.control_dir.mkdir()
        shutil.copytree(self.originals/'versions.git',self.control_dir/'versions.git')
        self.open_stores()
        self.files.materialize('base-materialize',self.base,str(self.root/'current'),self.grant)
        self.resource=self.control.register(self.principal,'register',self.base['resource_id'],self.namespace,self.base['domain'],str(self.root/'current'),{'owner':'fixture-harness','id':'h'}, {self.principal:['read','write']})
        self.fbinding=dict(resource_id=self.resource['id'],domain=self.resource['kind'],path=self.resource['path'],root=ident(self.resource['path']),revision=self.resource['revision'],authorization=self.grant)
        self.source=dict(owner='X-original-archive',original_binding=self.binding,original_archive=self.prepared['archive'],stopped_ref=self.stop)
        self.output=self.files.import_archive('import',self.fbinding,str(self.originals/'original-checkpoint.tar'),self.source,self.base,'host-v1')
        self.materialized=self.files.materialize('output-materialize',self.output['version_ref'],str(self.root/'stage'),self.grant)
        self.expected_base=snapshot(self.root/'current');self.expected_output=snapshot(self.root/'stage')
        self.old_root=ident(self.root/'current');self.stage_root=ident(self.root/'stage')
        self.args=dict(principal=self.principal,namespace=self.namespace,install_id='install',resource=self.resource,base_ref=self.base,materialization_request_id='output-materialize',stopped_ref=self.stop,authorization=self.grant)
        self.pub=cls(self.control,self.files,self.stop_validator)
        save(self.root/'original-inputs.json',dict(args=self.args,materialized=self.materialized,output=self.output,old_root=self.old_root,stage_root=self.stage_root,expected_base=self.expected_base,expected_output=self.expected_output))
    def open_stores(self):
        from lore_control import ControlStore
        from lore_files import FileStore
        authority={self.principal:dict(namespaces=[self.namespace],roles=['admin','runtime','submit'])}
        self.control=ControlStore(self.root/'R.sqlite',authority,reference_checker=self.rref)
        self.files=FileStore(self.control_dir,self.auth,self.fref,checkpoint=self.checkpoint)
    def reopen(self):
        self.control.close();self.open_stores();self.pub=self.cls(self.control,self.files,self.stop_validator)
    @classmethod
    def restored(cls,root,product):
        self=cls.__new__(cls);self.root=Path(root);self.cls=product;self.pub=None;self.exchanges=0;self.cut=None;self.calls=[]
        self.originals=ROOT/'originals';self.oldbase=load(self.originals/'base.json');self.originalstop=load(self.originals/'actual-stop.json');self.prepared=load(self.originals/'prepared-source.json')
        facts=load(self.root/'original-inputs.json');self.args=facts['args'];self.resource=self.args['resource'];self.base=self.args['base_ref'];self.stop=self.args['stopped_ref'];self.grant=self.args['authorization'];self.principal=self.args['principal'];self.namespace=self.args['namespace'];self.binding=self.prepared['binding']
        self.materialized=facts['materialized'];self.output=facts['output'];self.expected_base=facts['expected_base'];self.expected_output=facts['expected_output'];self.old_root=facts['old_root'];self.stage_root=facts['stage_root']
        self.control_dir=self.root/'F';self.open_stores()
        self.source=self.files.journal.get('import')['inputs']['source_ref'];self.fbinding=self.files.journal.get('import')['inputs']['binding'];self.pub=product(self.control,self.files,self.stop_validator)
        return self
    def child_resume(self):
        self.control.close()
        command=[sys.executable,'-B',str(Path(__file__)), '--batch',str(self.root),'--resume']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=45)
        (self.root/'resume.stdout').write_bytes(result.stdout);(self.root/'resume.stderr').write_bytes(result.stderr)
        require(result.returncode==0,'original new-process recovery failed: '+result.stderr.decode(errors='replace'))
        child=load(self.root/'resume-result.json');require(child['pid']!=os.getpid() and child['exchanges']==0,'recovery did not run in new process or exchanged again')
        self.open_stores();self.pub=self.cls(self.control,self.files,self.stop_validator)
        return child['result']
    def checkpoint(self,label,facts):
        if label=='after_exchange_before_record':self.exchanges+=1
        self.calls.append(dict(owner='F',label=label,facts=facts))
        if label==self.cut:self.cut=None;raise Cut(label)
    def auth(self,ref,purpose,context):
        if ref!=self.grant or context.get('operation')!=purpose:return False
        if purpose=='materialize':return str(context['target_path']).startswith(str(self.root)+'/') and context['version_ref']['resource_id']==self.base['resource_id']
        if purpose=='import_archive':return context['binding']==self.fbinding and context['base_ref']==self.base
        if purpose=='install':return context['intent']['binding']==self.fbinding
        return False
    def fref(self,ref,purpose,context):
        if purpose=='source':
            return ref==self.source and context['base_ref']==self.base and context['archive']['sha256']==self.prepared['archive']['sha256'] and context['archive']['bytes']==self.prepared['archive']['size']
        return self.pub is not None and self.pub.file_reference(ref,purpose,context)
    def rref(self,ref,purpose,expected):
        if purpose=='harness':return ref=={'owner':'fixture-harness','id':'h'}
        if purpose=='base':
            return ref==self.base and expected=={'resource_id':self.base['resource_id']} and self.files.versions.load(ref)[0]==(self.originals/'base-archive.tar').read_bytes()
        return self.pub is not None and self.pub.control_reference(ref,purpose,expected)
    def stop_validator(self,ref,purpose,expected):
        self.calls.append(dict(owner='stop-validator',purpose=purpose,ref=ref,expected=expected))
        if ref!=self.stop or purpose!='stopped':return False
        fact=ref['original'];bytes_=Path(fact['path']).read_bytes()
        if len(bytes_)!=fact['size'] or sha(bytes_)!=fact['sha256']:return False
        obs=json.loads(bytes_);r=obs['reference'];e=obs['Engine'];process=obs['processes']
        if e['Id']!=self.binding['container_id'] or e['State']['Running'] or e['State']['Pid']!=0:return False
        if process['namespace']!=self.prepared['namespace'] or process['namespace_pids']!=[]:return False
        if r['execution_id']!=self.binding['execution_id'] or r['generation']!=self.binding['object_generation'] or r['request_sha256']!=self.binding['request_digest']:return False
        if sha(raw(self.base))!=self.oldbase['opaque_base_version'] or sha((self.originals/'original-checkpoint.tar').read_bytes())!=r['archive_sha256']:return False
        values=dict(principal=self.principal,namespace=self.namespace,resource=self.resource,base_ref=self.base,execution_id=self.binding['execution_id'],generation=self.binding['object_generation'],materialization_request_id='output-materialize',materialization=self.materialized)
        if any(expected.get(k)!=v for k,v in values.items()):return False
        provenance=expected.get('provenance',{})
        return provenance.get('operation')=='import_archive' and provenance.get('source_ref')==self.source and provenance.get('base_ref')==self.base and self.output['version_ref']['archive_sha256']==r['archive_sha256']
    def publish(self,**changes):return self.pub.publish(**(copy.deepcopy(self.args)|changes))
    def sql(self):
        return {name:[dict(row) for row in self.control.db.execute('SELECT * FROM '+name)] for name in ['resources','holders','installations','releases']}
    def verify_installed(self,result):
        facts=self.sql();r=facts['resources'][0]
        require(self.exchanges==1,'must perform exactly one actual F exchange')
        require(ident(self.root/'current')==self.stage_root and ident(self.root/'stage')==self.old_root,'original directory objects not exchanged exactly')
        require(snapshot(self.root/'current')==self.expected_output and snapshot(self.root/'stage')==self.expected_base,'full actual bytes/metadata differ from independent original trees')
        require(r['revision']==2 and {'dev':r['dev'],'ino':r['ino']}==self.stage_root,'R actual registration not installed exactly once')
        require(facts['holders']==[] and len(facts['releases'])==1,'original holder not released')
        require(len(facts['installations'])==1 and facts['installations'][0]['installation_ref_json'] is not None,'actual original install confirmation missing')
        require(result['installation_ref']==json.loads(facts['installations'][0]['installation_ref_json']),'returned receipt differs from original R stored projection')
        require(result['F_query']==self.files.query_install('install'),'returned F observation differs from actual F query')
        require(result['registration']==self.control.resolve(self.principal,self.namespace,self.resource['id'],'write'),'returned registration differs')
        require(result['F_query']['version_ref']==self.output['version_ref'],'original full F version lost')
        require(result['installation_ref']['staged_ref']==result['R_intent']['staged_ref'],'original full R staged ref lost')
        raw_output=self.files.versions.load(self.output['version_ref'])[0]
        require(raw_output==(self.originals/'original-checkpoint.tar').read_bytes(),'actual F Git archive not exact original X bytes')
        return facts
    def finish(self):
        save(self.root/'calls.json',self.calls);save(self.root/'sql.json',self.sql())
        save(self.root/'actual.json',dict(exchange_count=self.exchanges,current_root=ident(self.root/'current'),stage_root=ident(self.root/'stage'),current=snapshot(self.root/'current'),stage=snapshot(self.root/'stage')))
        (self.root/'R.sql').write_text('\n'.join(self.control.db.iterdump())+'\n');self.control.close()

def run_case(case,out,cls):
    f=Fixture(out,cls);result={}
    try:
        if case=='FP01':
            result=f.publish();f.verify_installed(result)
        elif case=='FP02':
            result=f.publish();f.verify_installed(result);old=copy.deepcopy(result)
            require(f.publish()==old,'same-call replay changed receipt')
            require(f.child_resume()==old,'new process changed original receipt');f.verify_installed(old)
            variants=[dict(namespace='other'),dict(principal='other'),dict(authorization={'owner':'other'}),dict(resource=f.resource|{'revision':2}),dict(base_ref=f.base|{'manifest_sha256':'0'*64}),dict(materialization_request_id='base-materialize'),dict(stopped_ref=f.stop|{'generation':f.stop['generation']+1})]
            result=dict(original=old,rejections=[expect_error(lambda v=v:f.publish(**v),{'reference_invalid','conflict','denied','stale'}) for v in variants]);f.verify_installed(old)
            original_authorizer=f.files.authorization_checker
            try:
                f.files.authorization_checker=lambda ref,purpose,context:False
                result['revoked_original_authorization']=expect_error(f.publish,{'UNAUTHORIZED'})
            finally:f.files.authorization_checker=original_authorizer
            f.verify_installed(old)
        elif case=='FP03':
            variants=[dict(stopped_ref=f.stop|{'execution_id':'other'}),dict(stopped_ref=f.stop|{'generation':f.stop['generation']+1}),dict(base_ref=f.base|{'resource_id':'other'}),dict(materialization_request_id='base-materialize'),dict(resource=f.resource|{'path':str(f.root/'stage')})]
            result['rejections']=[expect_error(lambda v=v:f.publish(**v),{'reference_invalid','conflict','denied','stale','not_found'}) for v in variants]
            require(f.exchanges==0 and f.sql()['installations']==[],'bad references formed install/exchange')
            proof=Path(f.stop['original']['path']);original=proof.read_bytes()
            try:
                proof.write_bytes(original[:-1]+(b'X' if original[-1:]!=b'X' else b'Y'))
                result['corrupt_original_stop']=expect_error(f.publish,{'reference_invalid'})
            finally:proof.write_bytes(original)
            # Same registered staged path now names another real inode; actual source result remains unchanged.
            (f.root/'stage').rename(f.root/'retained-stage');shutil.copytree(f.root/'retained-stage',f.root/'stage',copy_function=shutil.copy2)
            result['replaced_stage']=expect_error(f.publish,{'reference_invalid','STALE_BINDING','CONFLICT'})
            require(f.exchanges==0 and f.sql()['installations']==[],'replaced stage was published')
        elif case=='FP04':
            (f.root/'current/human-edit').write_bytes(b'actual-human-edit')
            result['first_error']=expect_error(f.publish,{'BASE_CHANGED'})
            require(f.exchanges==0 and len(f.sql()['holders'])==1 and len(f.sql()['installations'])==1,'manual edit lost original responsibility')
            f.reopen();result['recovery_error']=expect_error(f.publish,{'PUBLICATION_UNKNOWN','BASE_CHANGED'})
            require((f.root/'current/human-edit').read_bytes()==b'actual-human-edit' and ident(f.root/'current')==f.old_root and ident(f.root/'stage')==f.stage_root,'manual bytes or original roots overwritten')
            require(f.sql()['installations'][0]['installation_ref_json'] is None and len(f.sql()['holders'])==1,'conflict acknowledged or holder erased')
        elif case=='FP05':
            f.cut='after_exchange_before_record'
            try:f.publish()
            except Cut as exc:result['cut']=str(exc)
            else:raise AssertionError('actual F cut did not happen')
            require(f.exchanges==1 and f.sql()['installations'][0]['installation_ref_json'] is None,'cut not between exchange and R confirmation')
            result['recovered']=f.child_resume();f.verify_installed(result['recovered'])
        elif case=='FP06':
            original=f.control.confirm_install
            def lost(*a,**kw):
                original(*a,**kw);raise Cut('R confirm commit before reply')
            f.control.confirm_install=lost
            try:f.publish()
            except Cut as exc:result['cut']=str(exc)
            else:raise AssertionError('R committed-ACK cut absent')
            require(f.sql()['resources'][0]['revision']==2 and len(f.sql()['holders'])==1,'cut not between confirmed revision and release')
            result['recovered']=f.child_resume();f.verify_installed(result['recovered'])
        return result
    finally:f.finish()

def worker(batch,mode):
    try:
        if mode=='bad':
            class FilePublication:
                def __init__(self,*a):pass
                def publish(self,**kw):return {'status':'PASS'}
        else:FilePublication=importlib.import_module('lore_runtime.file_publication').FilePublication
    except ModuleNotFoundError:
        save(batch/'assessment.json',dict(status='MISSING',actual_runs=0,cases=[]));return 2
    rows=[]
    for case in IDS:
        try:result=run_case(case,batch/'actual'/case,FilePublication);rows.append(dict(id=case,status='PASS',result=result))
        except BaseException as exc:
            rows.append(dict(id=case,status='FAIL',error=repr(exc),traceback=traceback.format_exc()))
        save(batch/'assessment.json',dict(status='PASS' if len(rows)==len(IDS) and all(x['status']=='PASS' for x in rows) else 'FAIL',actual_runs=len(rows),cases=rows))
    return 0 if all(x['status']=='PASS' for x in rows) else 1

def main():
    a=argparse.ArgumentParser();a.add_argument('--batch',required=True);a.add_argument('--worker',action='store_true');a.add_argument('--resume',action='store_true');a.add_argument('--mode',choices=['normal','bad'],default='normal');args=a.parse_args()
    if args.resume:
        product=importlib.import_module('lore_runtime.file_publication').FilePublication
        f=Fixture.restored(Path(args.batch),product)
        try:
            result=f.publish();save(f.root/'resume-result.json',dict(result=result,pid=os.getpid(),source=importlib.import_module('lore_runtime.file_publication').__file__,exchanges=f.exchanges,sql=f.sql(),calls=f.calls))
        finally:f.control.close()
        return 0
    if args.worker:return worker(Path(args.batch),args.mode)
    batch=ROOT/'validation/file-publication-evidence'/args.batch;batch.mkdir(parents=True)
    workspace=batch/'workspace';workspace.mkdir()
    files=[]
    for package in ['lore_control','lore_files']:
        files.extend((ROOT/package).glob('*.py'))
    product=ROOT/'lore_runtime/file_publication.py'
    if product.exists():files.append(product)
    files.extend([Path(__file__),ROOT/'design/g3/file-publication/contract.md',ROOT/'design/g3/file-publication/cases.json'])
    before={str(f.relative_to(ROOT)):sha(f.read_bytes()) for f in files}
    for f in files:
        dest=workspace/f.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
    original_files=[SOURCE/n for n in ['base.json','prepared-source.json','actual-stop.json','original-checkpoint.tar']]
    original_files.extend((SOURCE/'control/versions.git').rglob('*'));original_files=[x for x in original_files if x.is_file()]
    old_hash={str(f):sha(f.read_bytes()) for f in original_files}
    originals=workspace/'originals';originals.mkdir()
    for f in original_files:
        rel=f.relative_to(SOURCE);rel=Path('versions.git')/f.relative_to(SOURCE/'control/versions.git') if str(rel).startswith('control/versions.git/') else rel
        dest=originals/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
    base=load(SOURCE/'base.json');shutil.copy2(base['bundle']['archive_path'],originals/'base-archive.tar')
    command=[sys.executable,'-B',str(workspace/'validation/file_publication_probe.py'),'--worker','--batch',str(batch),'--mode',args.mode]
    env=dict(os.environ,PYTHONPATH=str(workspace),PYTHONDONTWRITEBYTECODE='1')
    save(batch/'source-before.json',before);save(batch/'original-X-source.json',old_hash);save(batch/'command.json',dict(argv=command,cwd=str(workspace)))
    with (batch/'stdout').open('wb') as out,(batch/'stderr').open('wb') as err:
        result=subprocess.run(command,cwd=workspace,env=env,stdout=out,stderr=err,timeout=180)
    after={str(f.relative_to(ROOT)):sha(f.read_bytes()) for f in files}
    copied={name:sha((workspace/name).read_bytes()) for name in before}
    original_unchanged=all(sha(Path(name).read_bytes())==value for name,value in old_hash.items())
    assessment=load(batch/'assessment.json') if (batch/'assessment.json').exists() else dict(status='FAIL',actual_runs=0,error='missing assessment')
    ok=before==after==copied and original_unchanged
    final=dict(status=assessment['status'] if ok else 'FAIL',actual_runs=assessment['actual_runs'],exit_code=result.returncode,source_unchanged=before==after,copied_source=before==copied,original_X_unchanged=original_unchanged)
    save(batch/'result.json',final);print(json.dumps(final));return result.returncode if ok else 1

if __name__=='__main__':raise SystemExit(main())
