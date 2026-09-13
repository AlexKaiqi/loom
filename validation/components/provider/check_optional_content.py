"""Eight fixed offline raw cases and the original paused receipt; no HTTP or Engine."""
import argparse,hashlib,importlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
DESIGN=ROOT/'design/g3/provider/optional-native-content'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def inventory(root):return {str(p):(sha(p),p.stat().st_dev,p.stat().st_ino,p.stat().st_size) for p in root.rglob('*') if p.is_file()}
def worker(out,phase):
    sys.path.insert(0,str(ROOT));from lore_provider.response import normalize
    from lore_session.provider import ProviderBridge
    suite=json.loads((DESIGN/'cases.json').read_bytes());rows=[];checking=False;events=[]
    def audit(event,args):
        if not checking:return
        if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen'):
            events.append(event);raise RuntimeError('offline observer forbids external execution/network')
        if event=='open' and isinstance(args[2],int) and args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
            events.append('write');raise RuntimeError('candidate original resolution cannot write')
    sys.addaudithook(audit)
    for case in suite['cases']:
        raw=(ROOT/case['raw']['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==case['raw']['sha256']
        try:
            checking=True;value=normalize(raw,case['transport']);actual=dict(accepted=True,normalized=value)
        except Exception as error:actual=dict(accepted=False,reason=getattr(error,'reason',type(error).__name__))
        finally:checking=False
        rows.append(dict(id=case['id'],actual=actual,expected=case['expected'],passed=actual==case['expected']))
    legacy=suite['legacy_query'];prepared=json.loads(Path(legacy['prepared_path']).read_bytes());root=Path(legacy['provider_root']);before=inventory(root);reads=[]
    def credential():reads.append(True);raise AssertionError('readonly query cannot read a credential')
    bridge=ProviderBridge(root,prepared['endpoint'],prepared['model_scope'],credential_provider=credential,timeout=prepared['timeout'])
    try:
        checking=True;answer=bridge.query(prepared['effect_id'],prepared['binding'])
        legacy_actual='RECEIVED_REJECTED_WIRE' if answer['status']=='RECEIVED' and answer['wire']['accepted'] is False and answer['fresh'] is False else 'WRONG_ORIGINAL_RESULT'
    except Exception as error:legacy_actual=getattr(error,'code',getattr(error,'reason',type(error).__name__))
    finally:checking=False
    expected=legacy[phase+'_expected'];legacy_ok=legacy_actual==expected and inventory(root)==before and not reads and not events
    result=dict(status='PASS' if all(v['passed'] for v in rows) and legacy_ok else 'FAIL',cases=rows,tests_run=len(rows),legacy_query=dict(actual=legacy_actual,expected=expected,passed=legacy_ok,original_files_unchanged=inventory(root)==before,credential_reads=len(reads)),forbidden_events=events,HTTP=0,Docker=0)
    save(out/'actual.json',result);print(json.dumps({k:result[k] for k in ('status','tests_run','HTTP','Docker')}));return 0 if result['status']=='PASS' else 1

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch');parser.add_argument('--phase',choices=('before','after'),required=True);parser.add_argument('--worker',type=Path);a=parser.parse_args()
    if a.worker:return worker(a.worker,a.phase)
    assert a.batch and Path(a.batch).name==a.batch;out=ROOT/'validation/components/provider/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';sources=[]
    originals=[*sorted((ROOT/'lore_provider').glob('*.py')),ROOT/'lore_session/provider.py',Path(__file__),*sorted(DESIGN.glob('*'))]
    for source in originals:
        if not source.is_file():continue
        dest=workspace/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);sources.append(dict(original=str(source),copy=str(dest),sha256=sha(source)))
    save(out/'sources.json',sources)
    argv=[sys.executable,'-B',str(workspace/Path(__file__).relative_to(ROOT)),'--worker',str(out),'--phase',a.phase]
    p=subprocess.run(argv,cwd=workspace,env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1'),capture_output=True,timeout=15)
    (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
    unchanged=all(sha(v['original'])==v['sha256']==sha(v['copy']) for v in sources)
    result=dict(status='PASS' if p.returncode==0 and unchanged else 'FAIL',exit_code=p.returncode,source_unchanged=unchanged,source_count=len(sources),sources_sha256=sha(out/'sources.json'),phase=a.phase)
    save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
