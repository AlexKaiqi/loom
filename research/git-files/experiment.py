"""Finite ordinary-file/Git mechanism comparison, not a restoration product."""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import traceback
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main(batch):
    out=HERE/'evidence'/batch;out.mkdir(parents=True,exist_ok=False)
    state=ROOT/'research/.cache/git-files'/batch;state.mkdir(parents=True,exist_ok=False)
    result={'protocol_sha256':hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'git_version':subprocess.check_output(['git','--version'],text=True).strip(),'commands':[],'checks':[],'observations':{},'errors':[]}
    def command(args,cwd):
        env={'PATH':'/usr/bin:/bin','HOME':str(state),'LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1'}
        p=subprocess.run(args,cwd=cwd,env=env,capture_output=True)
        result['commands'].append({'argv':args,'cwd':str(cwd),'returncode':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr':p.stderr.decode()})
        if p.returncode:raise RuntimeError(p.stderr.decode())
        return p.stdout
    def setup(name,files):
        work=state/name;work.mkdir();meta=state/(name+'.git')
        for path,value in files.items():f=work/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(value)
        command(['git','init','--bare',str(meta)],state)
        return work,meta
    def git(pair,*args):
        work,meta=pair
        return command(['git','--git-dir='+str(meta),'--work-tree='+str(work),'-c','core.hooksPath=/dev/null',*args],work)
    def capture(pair,force):
        git(pair,'add','--all',*(['--force'] if force else []),'--','.')
        return git(pair,'write-tree').decode().strip()
    def restore(pair,tree,name):
        data=git(pair,'archive','--format=tar',tree);(out/(name+'.tar')).write_bytes(data)
        dest=state/name;dest.mkdir()
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                assert m.isfile() or m.isdir()
                assert (dest/m.name).resolve().is_relative_to(dest.resolve())
            t.extractall(dest)
        return {str(p.relative_to(dest)):p.read_text() for p in dest.rglob('*') if p.is_file()}
    def check(name,ok):
        result['checks'].append({'id':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    try:
        original={'template.md':'T0','blocks/goal.md':'B0','.gitignore':'ignored-input\n','ignored-input':'NEEDED0'}
        surface=setup('surface',original);workspace=setup('workspace',{'report.txt':'REPORT0'})
        noforce=setup('wrong-tracked-only',original);wrong=capture(noforce,False)
        o=result['observations'];o['wrong_archive']=restore(noforce,wrong,'wrong-restored')
        check('G04_ignored_input_omission','ignored-input' not in o['wrong_archive'] and (noforce[0]/'ignored-input').read_text()=='NEEDED0')
        s0=capture(surface,True);w0=capture(workspace,True)
        raw=command(['python3','-c','from pathlib import Path; print(Path("template.md").read_text()+"/"+Path("blocks/goal.md").read_text())'],surface[0]).decode().strip()
        check('G01_ordinary_python_files',raw=='T0/B0' and not (surface[0]/'.git').exists())
        (surface[0]/'template.md').write_text('T1');mixed=capture(surface,True)
        o['mixed_archive']=restore(surface,mixed,'mixed-restored')
        check('G03_commit_does_not_imply_application_consistency',o['mixed_archive']['template.md']=='T1' and o['mixed_archive']['blocks/goal.md']=='B0')
        (surface[0]/'blocks/goal.md').write_text('B1');(workspace[0]/'report.txt').write_text('REPORT1');s1=capture(surface,True);w1=capture(workspace,True)
        effect=state/'control-effects.jsonl';effect.write_text('{"operation":"op1","count":1}\n')
        o['surface_restored']=restore(surface,s0,'surface-restored');o['workspace_current']=restore(workspace,w1,'workspace-current')
        o['external_fact']=effect.read_text();o['version_tuple']={'s0':s0,'s1':s1,'w0':w0,'w1':w1,'mixed':mixed}
        check('G01_governed_ignored_file_restored',o['surface_restored']==original)
        check('G02_separate_domain_and_fact',o['workspace_current']=={'report.txt':'REPORT1'} and json.loads(o['external_fact'])['count']==1)
        o['surface_tree']=git(surface,'ls-tree','-r',s0).decode();o['workspace_tree']=git(workspace,'ls-tree','-r',w1).decode()
    except Exception as e:result['errors'].append({'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
    result['status']='PASS' if not result['errors'] else 'FAIL';(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'batch':batch,'status':result['status'],'checks':result['checks'],'errors':result['errors']}))
    return 0 if not result['errors'] else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
