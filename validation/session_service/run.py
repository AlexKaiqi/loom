"""Original S018 bytes + actual SessionRun/SnapshotStore; scripted facilities, no Engine."""
import argparse
import base64
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lore_session.snapshots import SnapshotStore
from lore_session.snapshot_files import canonical, sha, SnapshotError
HERE = Path(__file__).resolve().parent
D = copy.deepcopy

def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def hashfile(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class NoEngineX:
    """Only the existing X API shape. No claim these scripted CIDs are live."""
    def __init__(self, root, fixture, script, log, corrupt=False):
        self.root, self.f, self.script, self.log = root, fixture, D(script), log
        first=fixture['originals'][script[0][0]]['request']['checkpoint_full_ref']
        self.binding=D(first['source_binding']);self.binding['channel_id']='noengine-channel'
        self.id=self.binding['execution_id'];self.phase=script[0][0];self.serial=0
        self.paused=False;self.stopped=False;self.writes=[];self.journal=self
        self.raws={k:Path(v['archive']).read_bytes() for k,v in fixture['originals'].items()}
        if corrupt:
            old=io.BytesIO(self.raws[self.phase]);out=io.BytesIO()
            with tarfile.open(fileobj=old) as src, tarfile.open(fileobj=out,mode='w',format=tarfile.PAX_FORMAT) as dst:
                for member in src:
                    data=src.extractfile(member).read() if member.isfile() else None
                    if member.name.endswith('.jsonl'):
                        data += b'{broken complete line}\n';member.size=len(data)
                    dst.addfile(member,io.BytesIO(data) if data is not None else None)
            self.raws[self.phase]=out.getvalue()
    def read(self, ref, cap):
        raw=Path(ref['path']).read_bytes();assert len(raw)<=cap
        assert sha(raw)==ref['sha256'] and len(raw)==ref.get('size',ref.get('bytes'))
        return raw
    def execute(self, request, authority):
        assert authority=={'fixture':'NO_ENGINE_ONLY'} and request['execution_id']==self.id
        self.log.append('start');return {'binding':D(self.binding)}
    def channel_write(self, execution_id, authority, raw, fields):
        assert not self.paused and not self.stopped
        assert fields['method']=='channel_write' and fields['byte_offset']==sum(len(x) for x in self.writes)
        assert all(fields[k]==self.binding[k] for k in ('execution_id','object_generation','request_digest','channel_id'))
        self.writes.append(raw);self.log.append('write:'+json.loads(raw).get('type','request'))
        p=self.root/('call-'+str(len(self.writes))+'.json');save(p,{'state':'CONFIRMED','written_bytes':len(raw)})
        return {'call_ref':{'path':str(p),'bytes':p.stat().st_size,'sha256':hashfile(p)}}
    def channel_read(self, execution_id, authority, stream, maximum, fields):
        assert not self.paused and not self.stopped and maximum<=65536
        assert all(fields[k]==self.binding[k] for k in ('execution_id','object_generation','request_digest','channel_id'))
        raw=b'';state='PENDING'
        if stream=='stdout':
            if self.script:
                self.phase,frame=self.script.pop(0)
                raw=canonical(frame)+b'\n' if frame is not None else b''
            else: state='COMPLETE'
        else:state='COMPLETE'
        return {'data_base64':base64.b64encode(raw).decode(),'byte_offset':fields['byte_offset'],
                'next_byte_offset':fields['byte_offset']+len(raw),'result':{'output_state':state},
                'artifacts':{'stdout':{'size':fields['byte_offset']+len(raw)}}}
    def close_stdin(self, *args):self.log.append('close');return {'closed':True}
    def checkpoint(self, execution_id, authority, checkpoint_id, purpose):
        self.serial+=1;self.paused=True;self.log.append('checkpoint:'+self.phase)
        self.binding['freeze_generation']=self.serial
        full=D(self.f['originals'][self.phase]['request']['checkpoint_full_ref'])
        p=self.root/('x-'+str(self.serial)+'.tar');p.write_bytes(self.raws[self.phase])
        full.update(path=str(p),size=p.stat().st_size,sha256=hashfile(p),freeze_generation=self.serial,
                    source_binding=D(self.binding))
        return {'binding':D(self.binding),'artifacts':{'checkpoint':full}}
    def resume(self, *args):assert self.paused and not self.stopped;self.paused=False;self.log.append('resume');return {'resumed':True}
    def seal(self, *args):assert self.paused;self.stopped=True;self.log.append('seal');return {'fixture_stop':True,'binding':D(self.binding)}
    def release_checkpoint(self,*args):self.log.append('release_checkpoint');return {'released':True}
    def release(self,*args):assert self.stopped;self.log.append('release');return {'fixture_release':True}
    def request_stop(self,*args):self.log.append('request_stop');return {'requested':True}

class Plans:
    def __init__(self,x):self.x=x
    def session(self,request,*,execution_id):
        return {'request':{'schema_version':2,'domain':'session','execution_id':execution_id,
                'session_binding':D(self.x.f['originals']['provider']['request']['original_binding']['binding']['session_scope']),
                'source_result':D(request['source_result_ref'])},'authority':{'fixture':'NO_ENGINE_ONLY'}}

    def resolve_read(self, original_ref, descriptor):
        if original_ref!=self.x.f['replies'][1]['result_ref']:
            raise SnapshotError('invalid_frame','original read authority mismatch')
        self.x.log.append('plans.resolve_read')
        p=self.x.root/'resolved-read.raw';p.write_bytes(base64.b64decode(self.x.f['replies'][1]['stdout']['data_b64']))
        return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashfile(p)}

class Provider:
    def __init__(self, fixture, log, mode):self.f,self.log,self.mode=fixture,log,mode
    def complete(self,binding,frame):
        self.log.append('provider.complete');self.complete_args=(D(binding),D(frame))
        return {'status':'UNKNOWN' if self.mode=='unknown_provider' else 'RECEIVED','fresh':self.mode!='retained_provider',
                'effect_id':frame['effect_id'],'wire':{'accepted':True,'normalized':{'message':D(self.f['replies'][0]['message'])}},
                'receipt_ref':{'fixture':'NO_HTTP_ONLY'}}
    def query(self,effect_id,binding):
        self.log.append('provider.query');self.query_args=(effect_id,D(binding))
        return {'status':'UNKNOWN' if self.mode=='provider_query_unknown' else 'RECEIVED','effect_id':effect_id}

class Tools:
    def __init__(self,fixture,root,log,mode):self.f,self.root,self.log,self.mode=fixture,root,log,mode
    def execute(self,binding,frame,snapshot):
        self.log.append('tools.execute');self.execute_args=(D(binding),D(frame),D(snapshot))
        reply=self.f['replies'][1];p=self.root/'stdout.raw';p.write_bytes(base64.b64decode(reply['stdout']['data_b64']))
        ref={'path':str(p),'bytes':p.stat().st_size,'sha256':hashfile(p)}
        if self.mode=='bad_stdout':p.write_bytes(b'wrong original bytes')
        return {'status':'RECEIVED','fresh':True,'result_ref':D(reply['result_ref']),'stdout_ref':ref}
    def query(self,effect_id,binding):self.log.append('tools.query');return {'status':'UNKNOWN','effect_id':effect_id}

def exercise(module, fixture, out, control):
    checks=[];f=fixture;accepted,provider,tool,saved=f['frames']
    for case in json.loads((HERE/'protocol.json').read_bytes())['cases']:
        name=case['id'];home=out/name;home.mkdir();log=[];error=None;result=None
        request=D(f['request']);request['action']='drive'
        script=[('provider',provider),('tool',tool),('saved',saved)]
        if name in ('accept','failed_accept'):
            request['action']='accept';frame=D(accepted)
            if name=='failed_accept':frame.update(boundary_kind='blocked_invalid',error={'code':'session_corrupt'})
            script=[('accepted',frame)]
        if name=='query_saved':request['action']='query';script=[('saved',saved)]
        if name in ('provider_query_known','provider_query_unknown','effect_query'):
            request['action']='query';is_tool=name=='effect_query';pending=tool if is_tool else provider
            query={k:D(pending[k]) for k in ('session_id','operation_id','effect_id')}
            query['type']='effect.query' if is_tool else 'provider.query'
            final={'type':'result','operation_id':'op-1','boundary_kind':'paused_reconciliation_required' if name=='provider_query_known' else 'paused_unknown','error':{'code':'original_pending'}}
            phase='tool' if is_tool else 'provider';script=[(phase,query),(phase,final)]
        if name in ('bad_response_id','bad_effect_id','bad_binding','query_attempts_dispatch'):
            bad=D(provider)
            if name=='bad_response_id':bad['response_entry_id']='wrong-original-id'
            if name=='bad_effect_id':bad['effect_id']='wrong-stable-id'
            if name=='bad_binding':request['input_ref']['sha256']='0'*64
            if name=='query_attempts_dispatch':request['action']='query'
            script=[('provider',bad)]
        if name=='bad_tool_args':
            bad=D(tool);bad['request']['script']='different script';script=[('tool',bad)]
        if name=='bad_final':
            bad=D(saved);bad['decision_proposal']['continue']=False;script=[('saved',bad)]
        if name=='short_eof':script=[('provider',None)]
        if name=='SS21-confirmation-failed':script=[('provider',provider)]
        if name in ('export_read','export_bad_source'):
            request['action']='export_read';request['read_ref']=D(f['replies'][1]['result_ref'])
            if name=='export_bad_source':request['read_ref']['request_digest']='0'*64
            read_frame={'type':'result','operation_id':'op-1','boundary_kind':'accepted',
                        'operation_result_ref':D(saved['operation_result_ref']),
                        'read_result_ref':dict(path='/input/originals/saved-stdout',**{k:f['replies'][1]['stdout'][k] for k in ('bytes','sha256')})}
            script=[('saved',read_frame)]
        x=NoEngineX(home,f,script,log,corrupt=name in ('failed_accept','SS21-confirmation-failed'))
        store=SnapshotStore(home/'owners',f['originals']['provider']['request']['expected_scope']['namespace'],lambda *args:log.append('S.register'),global_budget_bytes=67108864)
        provider_port=Provider(f,log,name);tools=Tools(f,home,log,name)
        def cut(label,facts):
            log.append('hook:'+label)
            save(home/('hook-'+str(len(log))+'.json'),facts)
            if name=='checkpoint_cut' and label=='before_dispatch':raise RuntimeError('PREDECLARED_NOENGINE_CUT')
        try:
            service=module.SessionService(x,store,provider_port,Plans(x),tools,checkpoint=cut)
            if control:result={'frame':D(saved)}
            else:result=service.invoke(request,execution_id=x.id,deadline_monotonic=time.monotonic()+3)
        except Exception as exc:error={'type':type(exc).__name__,'code':getattr(exc,'code',None),'evidence':getattr(exc,'evidence',None),'message':str(exc)}
        writes=[json.loads(v) for v in x.writes];side=[v for v in log if v in ('provider.complete','provider.query','tools.execute','tools.query')]
        try:
            if name=='accept':assert result['frame']==accepted and not side and result['confirmation_request_id'] and store.query(result['confirmation_request_id'])
            elif name=='drive':
                assert result['frame']==saved and side==['provider.complete','tools.execute']
                assert [v for v in writes if v.get('type')=='provider.reply']==[f['replies'][0]]
                assert [v for v in writes if v.get('type')=='tool.reply']==[f['replies'][1]]
                assert log.index('checkpoint:provider')<log.index('provider.complete') and log.index('checkpoint:tool')<log.index('tools.execute')
            elif name=='query_saved':assert result['frame']==saved and not side
            elif name in ('provider_query_known','provider_query_unknown','effect_query'):
                assert result['frame']==final and side==['tools.query' if name=='effect_query' else 'provider.query']
                assert writes[1]['effect_id']==query['effect_id'] and writes[1]['result']['status']==('RECEIVED' if name=='provider_query_known' else 'UNKNOWN')
            elif name in ('bad_response_id','bad_effect_id','bad_binding','bad_tool_args','query_attempts_dispatch','bad_final'):
                assert error and error['code']=='invalid_frame' and not side
            elif name in ('retained_provider','unknown_provider'):
                assert error and error['code']==('paused_unknown' if name=='unknown_provider' else 'paused_reconciliation_required')
                assert side==['provider.complete'] and not any(v.get('type')=='provider.reply' for v in writes)
            elif name=='failed_accept':
                assert result['frame']==frame and result.get('confirmation_request_id') is None and not result.get('original_session_snapshot_ref') and result['retained_quarantine']
                assert not side and not any(p.name.startswith('s-') for p in home.glob('empty*'))
            elif name=='short_eof':assert error and error['code']=='paused_unknown' and not side
            elif name=='SS21-confirmation-failed':
                assert error and not side and x.serial==1 and not error['evidence'].get('cleanup_error')
                q=error['evidence']['retained_quarantine'];owner=json.loads(Path(q['owner_record_ref']['path']).read_bytes())
                assert store.query_quarantine(owner['confirmation_request_id'])==q
                full=owner['source']['original_checkpoint_full_ref']
                assert full['path']==str(home/'x-1.tar') and hashfile(q['quarantine_ref']['archive_path'])==hashfile(home/'x-1.tar')
                receipts=[json.loads(p.read_bytes()) for p in (home/'owners').glob('receipt-*.json')]
                assert len(receipts)==1 and receipts[0]['old_checkpoint_full_ref']==full and receipts[0]['handoff_kind']=='sealed_ownership_transfer'
                assert not error['evidence'].get('original_session_snapshot_ref')
            elif name=='checkpoint_cut':assert error and not side and error['evidence'].get('original_session_snapshot_ref')
            elif name=='bad_stdout':assert error and error['code']=='invalid_frame' and not any(v.get('type')=='tool.reply' for v in writes)
            elif name=='export_read':
                assert result['frame']==read_frame and not side and 'plans.resolve_read' in log
                ref=result['resolved_read_ref'];assert hashfile(ref['path'])==read_frame['read_result_ref']['sha256'] and Path(ref['path']).stat().st_size==read_frame['read_result_ref']['bytes']
            elif name=='export_bad_source':assert error and error['code']=='invalid_frame' and error['message']=='original read authority mismatch' and not side and 'plans.resolve_read' not in log
            assert log[-1]=='release' and log.index('seal')<log.index('release')
            if result and result.get('confirmation_request_id'):assert store.query(result['confirmation_request_id'])
            passed=True
        except Exception as exc:passed=False;check_error=repr(exc)
        save(home/'observed.json',{'facility_scope':'SCRIPTED_NO_ENGINE_NO_HTTP','log':log,'writes':writes,'result':result,'error':error})
        checks.append({'id':name,'passed':passed,**({} if passed else {'assertion_error':check_error})})
    return checks

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch',required=True);parser.add_argument('--control',choices=['always-green']);args=parser.parse_args()
    assert args.batch and all(c.isalnum() or c in '-_' for c in args.batch)
    out=HERE/'evidence'/args.batch;out.mkdir(parents=True)
    f=json.loads((HERE/'fixtures.json').read_bytes());protocol=json.loads((HERE/'protocol.json').read_bytes())
    files=[HERE/'run.py',HERE/'fixtures.json',HERE/'protocol.json',ROOT/'design/g3/s/service-contract.md']+list((ROOT/'lore_session').glob('*.py'))
    before={str(p):hashfile(p) for p in files};record={'status':'MISSING','tests_run':0,'source_before':before,'original_sources':f['source_files']}
    try:
        assert hashfile(HERE/'fixtures.json')==protocol['fixtures_sha256']
        assert all(hashfile(p)==h for p,h in f['source_files'].items())
        try:module=importlib.import_module('lore_session.service')
        except ModuleNotFoundError as e:
            if e.name!='lore_session.service':raise
            record['missing']=str(e);save(out/'result.json',record);print('MISSING 0');return 2
        checks=exercise(module,f,out,args.control)
        after={str(p):hashfile(p) for p in files};intact=all(hashfile(p)==h for p,h in f['source_files'].items())
        record.update(tests_run=len(checks),checks=checks,source_after=after,source_unchanged=before==after,original_sources_unchanged=intact,actual_module_path=module.__file__)
        record['status']='PASS' if len(checks)==len(protocol['cases']) and all(c['passed'] for c in checks) and before==after and intact else 'FAIL'
    except Exception as e:record.update(status='FAIL',error=repr(e))
    save(out/'result.json',record);print(json.dumps({k:record.get(k) for k in ('status','tests_run','error')}));return 0 if record['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
