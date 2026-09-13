"""Original three groups on actual Docker; reuses existing X external Collector."""
import argparse,base64,copy,io,json,sys,tarfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from validation.runtime_input_mount.run import Fixture,save,sha,need,sources,reject
sys.path.insert(0,str(ROOT/'validation/components/x'))
from validation.components.x.collector import Collector
from validation.x_tool_inode_probe import exact_cleanup
from lore_execution import ExecutionStore
from lore_execution.journal import canonical,digest
from lore_execution.errors import ExecutionError
SCRIPT=r"""import errno,json,hashlib
from pathlib import Path
p=Path('/input/report.json')
try: raw=p.read_bytes(); read={'sum':json.loads(raw)['sum'],'sha256':hashlib.sha256(raw).hexdigest()}
except OSError as e: read={'error':e.errno}
try: p.write_bytes(b'FORBIDDEN'); denied=False; code=None
except OSError as e: denied=True; code=e.errno
Path('/work/notes.md').write_text('[report](/input/report.json)\n')
Path('/work/effect').write_bytes(b'one\n')
print(json.dumps({'read':read,'write_denied':denied,'write_errno':code}),flush=True)
"""

def archive_files(raw):
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as src:
        return {v.name.removeprefix('./'):src.extractfile(v).read() for v in src if v.isfile()}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);a=ap.parse_args()
    need(a.batch.replace('-','').isalnum(),'unsafe batch')
    out=ROOT/'validation/runtime_input_mount/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
    before=sources();before[str(Path(__file__))]=sha(__file__);save(out/'source-before.json',before)
    checks=[];errors=[];store=None;observer=None;owned=[];cleanup=[]
    def check(case,name,yes,**facts):
        row=dict(case=case,check=name,passed=bool(yes),**facts);checks.append(row);save(out/'checks.json',checks);need(yes,name)
    try:
        f=Fixture(out/'fixture');base=f.peer.capture(f.fx['target'],'surface')
        original={p.name:p.read_bytes() for p in f.fx['target'].iterdir() if p.is_file()}
        f.request['script_base64']=base64.b64encode(SCRIPT.encode()).decode();f.authority=f.authorize(f.request)
        observer=Collector(out,f.fx)
        store=ExecutionStore(str(f.state),trusted_config=str(f.config_path),trusted_config_sha256=sha(f.config_path))
        # Rejected actual API requests must create no Engine object, not merely report failure.
        before_objects=(observer.ids('container'),observer.ids('volume'));negative=[]
        for name,change in [('task',lambda q:q.update(domain='task')),('rw',lambda q:q['readonly_mounts'][0].update(read_only=False)),('target',lambda q:q['readonly_mounts'][0].update(target='/other')),('version',lambda q:q['readonly_mounts'][0]['content_ref']['version_ref'].update(archive_sha256='0'*64))]:
            q=copy.deepcopy(f.request);q['execution_id']+='-'+name;change(q);f.fx['execution_ids'].add(q['execution_id']);auth=f.authorize(q)
            negative.append(dict(name=name,**reject(lambda:store.execute(q,auth))))
        check('RI02','actual_rejections_created_no_objects',before_objects==(observer.ids('container'),observer.ids('volume')),rejections=negative)
        def run_one(legacy):
            label='legacy' if legacy else 'input';folder=out/label;folder.mkdir()
            q=copy.deepcopy(f.request);q['execution_id']+='-'+label
            if legacy:q.pop('readonly_mounts')
            auth=f.authorize(q);f.fx['execution_ids'].add(q['execution_id']);f.fx['request']=q;f.fx['authority']=auth
            observer.fx=f.fx
            save(folder/'request.json',q);save(folder/'authority.json',auth)
            started=store.execute(q,auth);binding=started['binding'];owned.append((copy.deepcopy(q),copy.deepcopy(binding)))
            save(folder/'started.json',started)
            initial=observer.capture(started,binding,label+'-initial')
            mounts=initial['physical']['container']['Mounts'];inputs=[m for m in mounts if m['Destination']=='/input']
            check('RI01',label+'_actual_mount',not inputs if legacy else len(inputs)==1 and inputs[0]['Type']=='bind' and not inputs[0]['RW'] and inputs[0]['Source']==f.mount['source']['path'],mounts=inputs)
            result=store.await_exit(q['execution_id'],auth,timeout=10);save(folder/'exit.json',result)
            check('RI01',label+'_actual_output_complete',result['result'].get('exit_code')==0 and result['result']['output_state']=='COMPLETE')
            stdout=Path(result['artifacts']['stdout']['path']).read_bytes();need(digest(stdout)==result['artifacts']['stdout']['sha256'],'original stdout hash')
            observed=json.loads(stdout);save(folder/'observed.json',observed)
            check('RI01',label+'_actual_history_read_and_write_denied',(observed['read']=={'error':2} if legacy else observed['read']=={'sum':10,'sha256':digest(f.old)}) and observed['write_denied'] and (observed['write_errno']==2 if legacy else observed['write_errno'] in (1,13,30)),observed=observed)
            cp=store.checkpoint(q['execution_id'],auth,'history-original','ordinary-tool');save(folder/'checkpoint.json',cp)
            ref=cp['artifacts']['checkpoint'];binding=cp['binding'];owned[-1]=(copy.deepcopy(q),copy.deepcopy(binding))
            raw=Path(ref['path']).read_bytes();need(digest(raw)==ref['sha256'],'original checkpoint hash')
            files=archive_files(raw);expected={**original,'notes.md':b'[report](/input/report.json)\n','effect':b'one\n'}
            check('RI03',label+'_whole_work_checkpoint',files==expected,files={k:digest(v) for k,v in files.items()})
            stopped=store.seal(q['execution_id'],auth,ref);save(folder/'stopped.json',stopped)
            observed_stop=observer.capture(stopped,binding,label+'-stopped')
            check('RI03',label+'_namespace_actually_stopped',not observed_stop['physical']['container_running'] and observed_stop['physical']['namespace_pids']==[])
            if not legacy:
                # Existing F import with explicit fixture authority over this actual stopped X source.
                rid=base['bundle']['version_ref']['resource_id'];grant=dict(owner='runtime-input-fixture',execution_id=q['execution_id'])
                st=f.fx['target'].stat();fb=dict(resource_id=rid,domain='surface',path=str(f.fx['target']),root=dict(dev=st.st_dev,ino=st.st_ino),revision=1,authorization=grant)
                context=dict(schema='lore-f-authority-context/v1',operation='import_archive',request_id='runtime-input-import',binding=fb,actual_root=fb['root'],profile='host-v1',base_ref=base['bundle']['version_ref'],source_ref=ref,archive=dict(path=ref['path'],bytes=len(raw),sha256=digest(raw)))
                f.peer.allow('authorization','import_archive',grant,context);f.peer.allow('reference','source',ref,context)
                imported=f.peer.store.import_archive('runtime-input-import',fb,ref['path'],ref,base['bundle']['version_ref'],'host-v1');save(folder/'F-import.json',imported)
                git=observer.run(['/usr/bin/git','--git-dir='+str(f.peer.root/'F-control/versions.git'),'cat-file','blob',imported['version_ref']['git_ref']+':archive.tar'])[1]
                check('RI03','actual_F_Git_archive_equals_whole_X',git==raw and archive_files(git)==expected and sha(imported['archive_path'])==digest(raw))
                conflict=copy.deepcopy(q);conflict['readonly_mounts'][0]['content_ref']['version_ref']['archive_sha256']='1'*64
                rejected=reject(lambda:store.execute(conflict,f.authorize(conflict)))
                check('RI03','same_ID_different_mount_rejected',rejected['code']=='ID_CONFLICT',error=rejected)
            released=store.release(q['execution_id'],auth);save(folder/'released.json',released)
            cleanup.extend(exact_cleanup(observer,f.fx,binding))
            query=store.query(q['execution_id'],auth);save(folder/'query.json',query)
            check('RI03',label+'_original_query_no_reexecution',query['binding']==released['binding'] and query['artifacts']['checkpoint']==ref and Path(ref['path']).read_bytes()==raw and Path(query['artifacts']['stdout']['path']).read_bytes()==stdout)
            check('RI03',label+'_old_F_bytes_unchanged',f.peer.read_F(f.file_ref)==f.old and (Path(f.mount['source']['path'])/'report.json').read_bytes()==f.old and (f.original/'report.json').read_bytes()==b'{"sum":999}\n')
        run_one(True);run_one(False)
    except Exception as exc:errors.append(dict(error=repr(exc),traceback=traceback.format_exc()))
    finally:
        if observer:
            for q,b in owned:
                try:
                    observer.fx=dict(f.fx,request=q);cleanup.extend(exact_cleanup(observer,observer.fx,b))
                except Exception as exc:errors.append(dict(cleanup_error=repr(exc)))
            try:check('RI03','Engine_baseline_preserved',observer.ids('container')==observer.baseline_containers and observer.ids('volume')==observer.baseline_volumes)
            except Exception as exc:errors.append(dict(final_cleanup_error=repr(exc)))
        if store:store.journal.close()
    after={p:sha(p) for p in before};stable=before==after
    loaded={str(Path(m.__file__).resolve()):sha(m.__file__) for name,m in list(sys.modules.items()) if name.startswith(('lore_execution','lore_files')) and getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py'}
    bound=all(before.get(p)==h for p,h in loaded.items())
    result=dict(status='PASS' if not errors and checks and all(c['passed'] for c in checks) and stable and bound else 'FAIL',scope='ACTUAL_X_SINGLE_RUNTIME_INPUT_AND_F_IMPORT_ONLY; fixture authority; no R install/M01',checks=checks,errors=errors,source_unchanged=stable,loaded_source_bound=bound,loaded_source=loaded,cleanup=cleanup)
    save(out/'source-after.json',after);save(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('checks','loaded_source','cleanup')},ensure_ascii=False));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
