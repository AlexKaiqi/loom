"""Finite original F historical input + external projection; no Engine/provider."""
import argparse,copy,hashlib,json,os,shutil,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def h(raw):return hashlib.sha256(raw).hexdigest()
def raw(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def save(p,v):p.write_bytes(json.dumps(v,indent=2).encode()+b'\n')
def need(v,m):
    if not v:raise AssertionError(m)
def rejected(fn):
    try:fn()
    except Exception as error:
        need(getattr(error,'code',None) in ('INVALID_REQUEST','VERSION_CORRUPT','VERSION_MISSING','STALE_BINDING','CONFLICT','LIMIT_EXCEEDED','UNAUTHORIZED'),'unexpected rejection: '+repr(error));return True
    return False

def exercise(out):
    from lore_files import FileStore
    from lore_files.metadata import walk
    from lore_files.util import identity
    from lore_runtime.session_plan_files import InputFiles
    grant={'fixture':'fixed local F paths only'}
    def auth(ref,purpose,context):
        if ref!=grant:return False
        if purpose=='capture':return Path(context['binding']['path']).is_relative_to(out)
        if purpose=='materialize':return Path(context['target_path']).is_relative_to(out)
        if purpose=='read_reference':return True
        return False
    files=FileStore(out/'F',auth,lambda ref,purpose,context: purpose=='coordination')
    surface=out/'surface';workspace=out/'workspace-source';surface.mkdir();workspace.mkdir()
    (surface/'template.md').write_text('HISTORY_GOAL {{notes.md}}');(surface/'notes.md').write_text('preserve actual Surface originals')
    (workspace/'report.txt').write_text('REPORT_VERSION_ONE_DO_NOT_PRELOAD')
    (workspace/'empty').mkdir();(workspace/'.git').mkdir();(workspace/'.git/ordinary').write_bytes(b'ordinary git member')
    (workspace/'.gitignore').write_text('ignored.dat');(workspace/'ignored.dat').write_bytes(b'ignored original')
    os.link(workspace/'report.txt',workspace/'report-alias');os.symlink('report.txt',workspace/'report-link')
    def capture(path,domain,id):
        b=dict(resource_id=domain+'-history',domain=domain,path=str(path),root=identity(path),revision=1,authorization=grant)
        bundle=files.capture(id,b,{'fixture':'coordinated local source'})
        material=files.materialize(id+'-read',bundle['version_ref'],str(out/(id+'-read')),grant)
        return dict(bundle=bundle,materialized=material)
    s=capture(surface,'surface','surface-original');v1=capture(workspace,'workspace','version-one')
    (workspace/'report.txt').write_text('REPORT_VERSION_TWO_DO_NOT_PRELOAD');v2=capture(workspace,'workspace','version-two')
    before_surface=walk(surface,files.limits)[0];inputs=InputFiles(files,dict(plan_root=str(out/'plans'),authorization=grant),lambda *a:None)
    events={'events.jsonl':b'[]'};versions=[v1,v2];prepared=[]
    def catalog(v):return [dict(version_ref=v['bundle']['version_ref'],read_path='/input/history/'+h(raw(v['bundle']['version_ref'])))]
    def prepare(directory,v,config=None):
        directory.mkdir(exist_ok=True)
        cfg=config or {'input':{'history_views':catalog(v)}}
        return inputs.input(directory,'invocation',s,events,{},b'original feedback',cfg,{'original':v['bundle']['version_ref']},history_view=v)
    rows=[]
    def group(id,fn):
        try:fn();rows.append(dict(id=id,status='PASS'))
        except Exception as e:rows.append(dict(id=id,status='FAIL',error=repr(e),traceback=traceback.format_exc()))
    def exact():
        for i,v in enumerate(versions):
            directory=out/'plans'/('input-'+str(i));plan=prepare(directory,v);prepared.append(plan)
            root=Path(plan['materialized']['path']);expected=catalog(v)[0];path=root/'history'/expected['read_path'].split('/')[-1]
            _,tree,_=files.versions.load(v['bundle']['version_ref']);need(walk(path,files.limits)[0]==tree,'history complete metadata/tree differs')
            need(walk(root/'surface',files.limits)[0]==before_surface,'projected Surface changed')
            need(prepare(directory,v)==plan,'same immutable input changed')
        old=Path(prepared[0]['materialized']['path'])/'history'/catalog(v1)[0]['read_path'].split('/')[-1]
        new=Path(prepared[1]['materialized']['path'])/'history'/catalog(v2)[0]['read_path'].split('/')[-1]
        need(old!=new and (old/'report.txt').read_bytes()==b'REPORT_VERSION_ONE_DO_NOT_PRELOAD' and (new/'report.txt').read_bytes()==b'REPORT_VERSION_TWO_DO_NOT_PRELOAD','current report replaced historical report')
        need(walk(surface,files.limits)[0]==before_surface,'source Surface changed')
    group('HIN01',exact)
    def faults():
        bad=copy.deepcopy(v1);bad['bundle']['version_ref']['archive_sha256']='0'*64
        need(rejected(lambda:prepare(out/'bad-version',bad)),'bad actual F version admitted')
        wrong={'input':{'history_views':[dict(catalog(v1)[0],read_path='/input/history/../surface')]}}
        need(rejected(lambda:prepare(out/'bad-path',v1,wrong)),'traversal catalog admitted')
        wrong={'input':{'history_views':catalog(v2)}}
        need(rejected(lambda:prepare(out/'swapped-version',v1,wrong)),'new full ref labels old bytes')
        directory=out/'plans/input-0';target=directory/'input-source/history'/catalog(v1)[0]['read_path'].split('/')[-1]/'report.txt'
        original=target.read_bytes()
        try:target.write_bytes(b'changed retained input');need(rejected(lambda:prepare(directory,v1)),'same input accepted changed historical bytes')
        finally:target.write_bytes(original)
    group('HIN02',faults)
    def projection():
        needed=[]
        for i,v in enumerate(versions):
            root=Path(prepared[i]['materialized']['path']);payload=dict(paths=dict(surface=str(root/'surface'),events=str(root/'events.jsonl'),feedback=str(root/'feedback.txt'),runtime='/input/surface',workspace='/workspace'),history_views=catalog(v))
            needed.append(dict(name='valid-'+str(i),input=payload))
        for name,path in [('traversal','/input/history/../surface'),('wrong-digest','/input/history/'+'0'*64)]:
            item=copy.deepcopy(needed[0]);item['name']=name;item['input']['history_views'][0]['read_path']=path;needed.append(item)
        bad=copy.deepcopy(needed[0]);bad['name']='wrong-domain';bad['input']['history_views'][0]['version_ref']['domain']='surface';needed.append(bad)
        save(out/'projection-input.json',needed)
        command=['/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node','--import','/path/to/loom/research/repos/pi/node_modules/tsx/dist/loader.mjs',str(ROOT/'validation/history_input_projection.mts'),str(out/'projection-input.json'),str(out/'projection-output.json')]
        save(out/'projection-command.json',command);p=subprocess.run(command,capture_output=True,timeout=20);(out/'node-stdout').write_bytes(p.stdout);(out/'node-stderr').write_bytes(p.stderr);need(p.returncode==0,'actual projection process failed')
        actual=json.loads((out/'projection-output.json').read_bytes())
        for i in range(2):
            need(actual[i]['ok'],'valid actual catalog rejected');text=actual[i]['text'];blocks=json.loads(text)['context_blocks'];catalogs=[json.loads(x)['history_views'] for x in blocks if x.startswith('{') and 'history_views' in x]
            need(catalogs==[catalog(versions[i])] and 'HISTORY_GOAL' in text and 'REPORT_VERSION_' not in text,'model projection lacks exact catalog or preloads body')
        need(all(not v['ok'] for v in actual[2:]),'bad catalog projected')
    group('HIN03',projection)
    def budget():
        # Existing per-tree limit fits both originals; aggregate copied input must exceed it.
        old=files.limits['max_entries'];counts=[len(files.versions.load(v['bundle']['version_ref'])[1]['entries']) for v in [s,v1]];files.limits['max_entries']=max(counts)+2
        try:need(rejected(lambda:prepare(out/'budget',v1)),'aggregate original F file budget omitted')
        finally:files.limits['max_entries']=old
    group('HIN04',budget)
    save(out/'original-versions.json',dict(surface=s,workspace_versions=versions,prepared=prepared,scope='real F files; explicit local permission fixture; no Engine/provider'))
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--worker',action='store_true');p.add_argument('--out');a=p.parse_args();assert a.batch and all(c.isalnum() or c in '-_' for c in a.batch)
    out=Path(a.out) if a.out else ROOT/'validation/history-input-evidence'/a.batch
    if not a.worker:
        out.mkdir(parents=True,exist_ok=False);w=out/'source';w.mkdir()
        names=[p.relative_to(ROOT) for pkg in ('lore_files','lore_execution') for p in (ROOT/pkg).iterdir() if p.suffix in ('.py','.json')]
        names += [Path(n) for n in ['lore_runtime/__init__.py','lore_runtime/session_plan_files.py','lore_runtime/session_plans.py','harnesses/minimal/projection.mts','lore_session/node/common.mts','validation/history_input_probe.py','validation/history_input_projection.mts','design/g4/history-input-001/contract.md']]
        hashes={str(n):h((ROOT/n).read_bytes()) for n in names}
        for n in names:(w/n).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,w/n)
        save(out/'sources.json',hashes);p=subprocess.run([sys.executable,'-B',str(w/'validation/history_input_probe.py'),'--worker','--batch',a.batch,'--out',str(out)],capture_output=True,cwd=w,timeout=60)
        (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr);result=json.loads((out/'result.json').read_bytes()) if (out/'result.json').exists() else {'status':'FAIL','error':'worker result absent'}
        result.update(exit_code=p.returncode,source_unchanged=all(h((ROOT/n).read_bytes())==h0 and h((w/n).read_bytes())==h0 for n,h0 in hashes.items()),source_count=len(hashes));save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' and result['source_unchanged'] else 1
    try:
        cases=exercise(out);result=dict(status='PASS' if len(cases)==4 and all(c['status']=='PASS' for c in cases) else 'FAIL',cases=cases)
    except Exception as e:result=dict(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    save(out/'result.json',result);return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
