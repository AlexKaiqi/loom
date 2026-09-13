"""Observe DBOS database, OS threads and actual fixture effects across process loss."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WORKER=HERE/'worker.py'

def read_rows(path):
    if not path.exists():return {}
    try:
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as c:
            c.row_factory=sqlite3.Row
            return {t:[dict(x) for x in c.execute('SELECT * FROM '+t)] for t in ['workflow_status','workflow_input','workflow_output','operation_outputs','notifications']}
    except sqlite3.OperationalError:return {}

def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []

def dump(path,value):path.write_text(json.dumps(value,indent=2,default=str)+'\n')

def main(batch):
    out=HERE/'evidence'/batch;out.mkdir(parents=True,exist_ok=False)
    state=ROOT/'research/.cache/dbos'/batch;state.mkdir(parents=True,exist_ok=False)
    normal=state/'normal';normal.mkdir();uncertain=state/'uncertain';uncertain.mkdir()
    result={'scope':'G2 actual source-installed DBOS with local SQLite. No production or Postgres claim',
            'protocol_sha256':hashlib.sha256((HERE/'protocol-001.json').read_bytes()).hexdigest(),
            'sources_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),WORKER]},
            'dbos_version':importlib.metadata.version('dbos'),'observations':{},'checks':[],'errors':[]}
    o=result['observations'];processes=[];logs=[]
    def check(name,ok):
        result['checks'].append({'id':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    def start(directory,mode):
        log=(out/(mode+'.log')).open('w');logs.append(log)
        env={k:v for k,v in os.environ.items() if k in ['PATH','HOME','LANG','LC_ALL']}
        p=subprocess.Popen([sys.executable,str(WORKER),str(directory),mode],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        processes.append(p);return p
    def wait_for(p,predicate,label):
        end=time.monotonic()+30
        while time.monotonic()<end:
            if predicate():return
            if p.poll() is not None:raise RuntimeError(f'{label}: worker exited {p.returncode}')
            time.sleep(.05)
        raise TimeoutError(label)
    def kill(p):
        os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
        check('process_reaped_'+str(p.pid),p.returncode==-9 and not Path(f'/proc/{p.pid}').exists())
    try:
        p=start(normal,'start')
        def ready():
            d=read_rows(normal/'system.sqlite')
            if len(d.get('workflow_status',[]))!=3 or not (normal/'stacks.json').exists():return False
            stacks=json.loads((normal/'stacks.json').read_text())
            return len([x for x in stacks if '_sys_db.py' in ''.join(x['stack']) and 'recv' in ''.join(x['stack'])])>=3
        wait_for(p,ready,'three persisted blocked workflows')
        before=read_rows(normal/'system.sqlite');dump(out/'database-before-kill.json',before)
        stacks=json.loads((normal/'stacks.json').read_text());dump(out/'thread-stacks.json',stacks)
        blocked=[x for x in stacks if '_sys_db.py' in ''.join(x['stack']) and 'recv' in ''.join(x['stack'])]
        o['waiting_threads']=[{'native_id':x['native_id'],'wchan':Path(f'/proc/{p.pid}/task/{x["native_id"]}/wchan').read_text()} for x in blocked]
        check('D03_actual_wait_threads',len(o['waiting_threads'])>=3)
        confirmed=rows(normal/'confirmed-effects.jsonl');o['confirmed_before']=confirmed
        outputs=[x for x in before['operation_outputs'] if x['workflow_uuid']=='flow-1' and x['function_name']=='confirmed_result']
        check('D01_saved_step_receipt',len(confirmed)==1 and len(outputs)==1 and json.loads(outputs[0]['output'])==confirmed[0])
        kill(p);afterkill=read_rows(normal/'system.sqlite');dump(out/'database-after-kill.json',afterkill)
        check('D03_pending_without_old_process',len([x for x in afterkill['workflow_status'] if x['status']=='PENDING'])==3)
        p=start(normal,'recover');wait_for(p,lambda:(normal/'conflict.json').exists(),'recover result and conflict');p.wait(timeout=10)
        check('D01_recovery_worker_success',p.returncode==0)
        o['recovered']=json.loads((normal/'recovered.json').read_text());o['confirmed_after']=rows(normal/'confirmed-effects.jsonl')
        check('D01_original_result_no_reexecution',o['recovered']=={'saved':confirmed[0],'message':'resume'} and o['confirmed_after']==confirmed)
        o['conflicting_resubmit']=json.loads((normal/'conflict.json').read_text());after=read_rows(normal/'system.sqlite');dump(out/'database-after-recovery.json',after)
        o['stored_workflow_input']=[x['inputs'] for x in after['workflow_input'] if x['workflow_uuid']=='flow-1']
        check('D02_original_content_preserved','original' in o['stored_workflow_input'][0] and 'changed' not in o['stored_workflow_input'][0] and rows(normal/'confirmed-effects.jsonl')==confirmed)
        p=start(uncertain,'uncertain-start');wait_for(p,lambda:len(rows(uncertain/'uncertain-effects.jsonl'))==1,'effect before saved return')
        first=read_rows(uncertain/'system.sqlite');dump(out/'uncertain-before-kill.json',first)
        check('D04_effect_without_saved_step',not any(x['function_name']=='effect_before_result' for x in first['operation_outputs']))
        kill(p);(uncertain/'release-effect').write_text('release')
        p=start(uncertain,'uncertain-recover');wait_for(p,lambda:(uncertain/'uncertain-result.json').exists(),'unknown effect recovery');p.wait(timeout=10)
        o['uncertain_effects']=rows(uncertain/'uncertain-effects.jsonl');o['uncertain_result']=json.loads((uncertain/'uncertain-result.json').read_text())
        dump(out/'uncertain-after-recovery.json',read_rows(uncertain/'system.sqlite'))
        check('D04_repeated_effect_observed',len(o['uncertain_effects'])==2 and o['uncertain_result']=='effect-confirmed')
    except Exception as e:result['errors'].append({'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
    finally:
        for p in processes:
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
        for log in logs:log.close()
        result['status']='PASS' if not result['errors'] else 'FAIL'
        dump(out/'result.json',result);print(json.dumps({'batch':batch,'status':result['status'],'checks':result['checks'],'errors':result['errors']}))
    return 0 if not result['errors'] else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
