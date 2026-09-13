"""Finite actual R/E/JetStream tests for the synchronous original-reference adapter."""
import argparse,asyncio,copy,hashlib,importlib,json,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'validation/components/e')]
from support import Server,WireProxy,BINARY,BINARY_SHA
from fixture import AUTHORITY,profile
from lore_control import ControlStore
from lore_events import EventService
from lore_events.values import encode,sha

def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def fact(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def same(a,b):return encode(a)==encode(b)

async def probe(out,module,mode):
    server=Server(out/'nats');proxy=WireProxy(server,out);reader=control=events=observer=None
    cases=[];thread_before=set(threading.enumerate());sources=[]
    for folder in ['lore_control','lore_events']:
        sources.extend(fact(p) for p in sorted((ROOT/folder).glob('*.py')))
    sources.extend(fact(ROOT/'lore_runtime'/n) for n in ['event_authority.py','event_reader.py'])
    sources.append(fact(Path(__file__)))
    save(out/'sources-before.json',sources)
    def check(ok,label):
        if not ok:raise AssertionError(label)
    def reject(ref,purpose,expected,label):check(authority(ref,purpose,expected) is False,label)
    def originals():
        return {'sql':list(control.db.iterdump()),'files':{str(p):fact(p) for folder in [out/'inputs',out/'event-receipts'] if folder.exists() for p in folder.rglob('*') if p.is_file()},'application_publishes':sum(x['direction']=='publish' for x in proxy.audit)}
    def run(cid,fn):
        start=time.monotonic()
        try: detail=fn();cases.append({'id':cid,'status':'PASS','seconds':time.monotonic()-start,'detail':detail})
        except Exception as exc:cases.append({'id':cid,'status':'FAIL','error':repr(exc)});raise
    try:
        await server.start();await proxy.start()
        control=ControlStore(out/'R.sqlite',AUTHORITY,reference_checker=lambda *a:False)
        prof=profile(out,max_bytes=1024,page_size=8)
        events=EventService(proxy.url,control,prof);reader=module.JetStreamReader(server.url).open()
        actual=module.EventReferences(control,events,reader)
        def observed(ref,purpose,expected=None):
            before=(control.db.in_transaction,control.db.total_changes)
            answer=True if mode=='bad' else actual(ref,purpose,expected)
            check(before==(control.db.in_transaction,control.db.total_changes),'reference checker changed its surrounding R transaction')
            return answer
        authority=observed
        href={'owner':'test-only-harness','path':str(out/'harness-source'),'sha256':sha(b'not executed')};(out/'harness-source').write_bytes(b'not executed')
        control.reference_checker=lambda ref,purpose,expected=None:(same(ref,href) and sha(Path(href['path']).read_bytes())==href['sha256']) if purpose=='harness' else authority(ref,purpose,expected)
        await events.start();observer=await server.connect();js=observer.jetstream()
        (out/'surface').mkdir();resource=control.register('runtime','reg','surface','n1','surface',str(out/'surface'),href,{'alice':['read','write'],'runtime':['read','write']})
        await events.submit('alice','event-positive','n1','notice',{'text':'original 雪'})
        event=control.query('runtime','event-positive');receipt=event['receipt_ref'];expected=control._receipt_expected(control._get_request('event-positive'))
        context={'surface_ref':{'owner':'R','resource_id':'surface','revision':resource['revision']},'previous_session_ref':None,'execution_targets':[{'resource_id':'surface','path':resource['path'],'revision':resource['revision']}]}
        selector=dict(namespace='n1',source='alice',start_sequence=1,filters={},page_size=8,**context)
        control.accept('alice',dict(id='step',namespace='n1',kind='invocation',payload={'resource_id':'surface','resource_revision':resource['revision'],'harness_ref':href,'input_binding':selector}))
        input_result=await events.prepare_input('alice','step','n1',1,{},out/'inputs',input_context=context)
        bound=control.query_input('runtime','step');iref=bound['input_ref'];iexpected={'invocation_id':'step','binding':selector}
        before=originals()
        def positive():
            check(authority(receipt,'receipt',expected),'actual positive receipt denied')
            check(authority(iref,'input',iexpected),'actual original input denied')
            check(before==originals(),'read changed original R/files/published new event')
            return {'receipt':receipt,'input_ref':iref,'original_input':input_result,'readonly':True}
        run('EA01',positive)
        def variations():
            count=0
            for k in ('request_id','namespace','source','delivery_owner','request_digest'):
                changed=copy.deepcopy(expected);changed[k]='wrong';reject(receipt,'receipt',changed,'accepted wrong expected '+k);count+=1
                changed=copy.deepcopy(receipt);changed[k]='wrong';reject(changed,'receipt',expected,'accepted changed '+k);count+=1
            for k,v in [('sequence',receipt['facility_ref']['sequence']+1),('subject','wrong'),('sha256','0'*64),('source','bob')]:
                changed=copy.deepcopy(receipt);changed['facility_ref'][k]=v;reject(changed,'receipt',expected,'accepted wrong original locator '+k);count+=1
            changed=copy.deepcopy(iexpected);changed['binding']['source']='bob';reject(iref,'input',changed,'accepted another input source');count+=1
            changed=copy.deepcopy(iref);changed['root']['ino']+=1;reject(changed,'input',iexpected,'accepted replaced input inode');count+=1
            check(before==originals(),'negative reference resolution mutated sources');return {'rejections':count}
        run('EA02',variations)
        def corrupt():
            target=Path(iref['path'])/'events.jsonl';raw=target.read_bytes();bad=bytearray(raw);bad[-3]^=1
            target.write_bytes(bad)
            try:reject(iref,'input',iexpected,'accepted same-length changed input');check(target.read_bytes()==bytes(bad),'repaired corrupt original')
            finally:target.write_bytes(raw)
            return {'same_length_corruption_rejected':True}
        run('EA03',corrupt)
        rejected=await events.submit('alice','event-negative','n2','oversize',{'text':'x'*2048});nrow=control.query('runtime','event-negative');nref=nrow['receipt_ref'];nexpected=control._receipt_expected(control._get_request('event-negative'))
        def negative():
            check(rejected['status']=='REJECTED' and authority(nref,'receipt',nexpected),'actual NATS rejection not verified')
            for key in ['namespace','sha256']:
                changed=copy.deepcopy(nref);changed['facility_ref'][key]='wrong';reject(changed,'receipt',nexpected,'accepted corrupt negative '+key)
            return {'original_negative':nref}
        run('EA05',negative)
        binding_raw,response_raw=control.db.execute('SELECT binding_json,response_json FROM operations WHERE id=?',('reg',)).fetchone()
        oref=dict(owner='R',kind='registration',id='reg',namespace='n1',resource_id='surface',revision=resource['revision'],sha256=sha(response_raw.encode()))
        oexpected=dict(namespace='n1',source='runtime',event_name='surface.registered')
        def observation():
            check(authority(oref,'observation',oexpected),'actual R registration denied')
            for key in ['owner','revision','resource_id','sha256']:
                changed=copy.deepcopy(oref);changed[key]='wrong';reject(changed,'observation',oexpected,'accepted forged observation '+key)
            changed=dict(oexpected,source='alice');reject(oref,'observation',changed,'accepted forged registering principal');return {'original':oref}
        run('EA06',observation)
        before=originals();oldreader=reader;oldreader.close();reader=module.JetStreamReader(server.url).open();actual.reader=reader
        run('EA07',lambda:(check(authority(receipt,'receipt',expected) and authority(iref,'input',iexpected),'fresh reader cannot resolve original'),check(before==originals(),'fresh reader changed R/files/events'),{'fresh_thread':True})[-1])
        await js.delete_msg('LORE_n1',receipt['facility_ref']['sequence'])
        run('EA04',lambda:(reject(receipt,'receipt',expected,'accepted unavailable original sequence'),reject(iref,'input',iexpected,'accepted input without original NATS source'),{'test_owned_original_deleted':True})[-1])
    finally:
        if reader is not None:reader.close()
        if observer is not None:await observer.close()
        if events is not None:await events.close()
        if control is not None:control.close()
        await proxy.close();server.close()
        source_unchanged=all(fact(Path(x['path']))==x for x in sources)
        new_threads=[t.name for t in threading.enumerate() if t not in thread_before]
        save(out/'assessment.json',dict(status='PASS' if len(cases)==7 and all(x['status']=='PASS' for x in cases) and source_unchanged and not new_threads and (server.proc is None or server.proc.poll() is not None) else 'FAIL',cases=cases,tests_run=len(cases),source_unchanged=source_unchanged,live_new_threads=new_threads,server_pid_reaped=server.proc is None or server.proc.poll() is not None,scope='Actual R/E/JetStream original-reference seam; no X/S/model/system claim'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--mode',choices=['normal','bad'],default='normal');a=p.parse_args();assert Path(a.batch).name==a.batch
    out=ROOT/'validation/event-authority-evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
    save(out/'environment.json',{'NATS_binary':fact(BINARY),'expected_sha256':BINARY_SHA,'python':sys.version,'mode':a.mode})
    assert sha(BINARY.read_bytes())==BINARY_SHA
    try: module=importlib.import_module('lore_runtime.event_authority')
    except ModuleNotFoundError as error:save(out/'assessment.json',{'status':'MISSING','tests_run':0,'error':str(error)});print('MISSING/0');return 2
    try:asyncio.run(probe(out,module,a.mode))
    except Exception as error:save(out/'error.json',{'error':repr(error)})
    result=json.loads((out/'assessment.json').read_text());print(json.dumps({k:v for k,v in result.items() if not isinstance(v,(dict,list))}));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
