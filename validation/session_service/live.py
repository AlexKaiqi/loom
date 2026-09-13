"""Finite real SessionService glue. Grants/F coordination/tool owner are test fixtures."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
D = copy.deepcopy
FIXTURES = ('PW01-text', 'PW02-native', 'PW16-cached-reasoning')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def check(value, message):
    if not value: raise AssertionError(message)

def proxy_protocol():
    return json.loads((ROOT/'design/g4/session-service-real-preparation-001/protocol.json').read_bytes())

def apply_goal(driver, goal):
    # Real F source bytes; no model response or native tool result is synthesized.
    (driver.root/'surface/template.md').write_text(goal['goal']+'\n{{notes.md}}\n')
    (driver.root/'surface/notes.md').write_text('Finite non-sensitive provider mechanism validation. Follow only the current operation goal.\n')
    (driver.root/'input/feedback.txt').write_bytes(b'')
    (driver.root/'input/events.jsonl').write_text(json.dumps(dict(source='explicit-test-input',operation=goal['operation']))+'\n')
    refs=driver.port('f','prepare_fixture_input',surface=str(driver.root/'surface'),workspace=str(driver.root/'workspace'),input_dir=str(driver.root/'input'),originals=str(driver.root/'originals'),version=goal['operation'],authority=driver.target['fixture_authority'])
    driver.binding.update({k:refs[k] for k in ('input_ref','harness_ref','capability_ref')})
    return refs

def profile_config(path):
    check(sha(path)==proxy_protocol()['profile_sha256'],'frozen trusted profile differs')
    profile=json.loads(path.read_bytes());check(profile['provider_model']=='gpt-5.6-terra' and profile['api_base_path']=='/v1','fixed verified proxy model/path')
    check(str(path) and profile['credential_file']=='/home/USER/.config/lore/credentials/openai-proxy.key','only original trusted credential path')
    endpoint=urlsplit(profile['endpoint']);check(endpoint.scheme in ('http','https') and endpoint.path in ('','/') and not endpoint.username and not endpoint.password and not endpoint.query,'trusted fixed endpoint')
    return profile,dict(scheme=endpoint.scheme,host=endpoint.hostname,port=endpoint.port or (443 if endpoint.scheme=='https' else 80))

class ProxyBudget:
    def __init__(self, bridge, root, deadline):self.bridge,self.root,self.deadline=bridge,root,deadline
    def complete(self, binding, frame):
        _,_,raw=self.bridge._prepared(binding,frame)  # Read-only full validation before lazy key retrieval.
        originals=list(self.root.glob('*/prepared.json'))
        check(len(originals)<3 and time.monotonic()<self.deadline,'three global original attempts/batch deadline')
        check(len(raw)<=8192,'additional conservative request-byte guard before credential read')
        return self.bridge.complete(binding,frame)
    def query(self, effect_id, binding):return self.bridge.query(effect_id,binding)

def prepare_proxy(out,target_path,profile_path):
    sys.path[:0]=[str(ROOT),str(ROOT/'validation/components/s')]
    from collector import CaseDriver
    from live_ports import load_target
    from validation.components.s.f_peer import Peer
    profile,_=profile_config(profile_path);protocol=proxy_protocol();target=load_target(target_path)
    d=CaseDriver(dict(setup=dict(session_id='session-service-real-prepare')),target,out/'fixture');rows=[]
    for goal in protocol['goals']:
        refs=apply_goal(d,goal);peer=Peer(d.ports['f'].fixture_root,target['fixture_authority'])
        view=peer.lookup('inputs',refs['input_ref'])['document']['source_F']['surface']
        ref,fact=peer.original_file(view,'template.md');raw=peer.read_F(ref)
        check(raw==(goal['goal']+'\n{{notes.md}}\n').encode(),'actual F goal bytes differ')
        rows.append(dict(operation=goal['operation'],input_ref=refs['input_ref'],actual_template=ref,actual_template_file=fact))
    check('wire_fixture' not in protocol['goals'][2]['goal'],'third goal must not contain marker')
    result=dict(status='PASS_PURE_PREPARATION_ONLY',HTTP=0,Docker=0,credential_reads=0,model=profile['provider_model'],goals=rows,source_sha256=sha(Path(__file__)),protocol_sha256=sha(ROOT/'design/g4/session-service-real-preparation-001/protocol.json'))
    save(out/'result.json',result);print(json.dumps({k:result[k] for k in ('status','HTTP','Docker','credential_reads','model')}));return 0

class HTTPFixture:
    """Three original response bodies, actual received HTTP bytes, one connection at a time."""
    def __init__(self, root, responses):
        self.root, self.responses, self.records, self.errors = root, responses, [], []
        root.mkdir(); self.stop = threading.Event(); self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0)); self.listener.listen(1); self.listener.settimeout(.1)
        self.endpoint = dict(scheme='http', host='127.0.0.1', port=self.listener.getsockname()[1])
        self.thread = threading.Thread(target=self.serve, name='finite-session-http'); self.thread.start()
    def serve(self):
        start = time.monotonic()
        while not self.stop.is_set() and time.monotonic()-start < 180:
            try: conn, address = self.listener.accept()
            except socket.timeout: continue
            except OSError: break
            raw = bytearray(); index = len(self.records); row = dict(index=index+1, peer=list(address), started=time.monotonic())
            try:
                check(index < 3, 'fourth HTTP request is forbidden'); conn.settimeout(3)
                while b'\r\n\r\n' not in raw:
                    part = conn.recv(4096); check(part and len(raw)+len(part)<=73728, 'invalid HTTP header'); raw.extend(part)
                head, _, body = raw.partition(b'\r\n\r\n'); check(len(head)<=8192, 'HTTP header cap')
                lines = head.decode('ascii').split('\r\n'); headers = {}
                for line in lines[1:]:
                    key, value = line.split(':',1); check(key.lower() not in headers, 'duplicate HTTP header'); headers[key.lower()]=value.strip()
                check(lines[0]=='POST /v1/chat/completions HTTP/1.1' and 'authorization' not in headers, 'only local credential-free original POST')
                length=int(headers['content-length']); check(0<=length<=65536 and 'transfer-encoding' not in headers, 'bounded original body')
                while len(body)<length:
                    part=conn.recv(min(4096,length-len(body))); check(part, 'short request'); raw.extend(part); body.extend(part)
                check(len(body)==length, 'original request length'); response=self.responses[index]
                outgoing=(f'HTTP/1.1 200 OK\r\nContent-Length: {len(response)}\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n').encode()+response
                (self.root/f'{index+1:03}-request.http').write_bytes(raw); (self.root/f'{index+1:03}-request.body').write_bytes(body)
                (self.root/f'{index+1:03}-response.http').write_bytes(outgoing)
                conn.sendall(outgoing); conn.shutdown(socket.SHUT_WR)
                row.update(request_complete=True, request_sha256=hashlib.sha256(body).hexdigest(), response_complete=True,
                           response_sha256=hashlib.sha256(response).hexdigest())
            except Exception as error: row['error']=repr(error); self.errors.append(repr(error))
            finally:
                conn.close(); row.update(closed=True, finished=time.monotonic()); self.records.append(row); save(self.root/'connections.json',self.records)
    def close(self):
        self.stop.set(); self.listener.close(); self.thread.join(4)
        check(not self.thread.is_alive(), 'HTTP fixture thread remains')

class PlanFixture:
    def __init__(self, plans, scope): self.plans, self.scope, self.original = plans, scope, None
    def session(self, request, *, execution_id):
        original={k:D(request[k]) for k in ('operation_id','input_ref','harness_ref','capability_ref','source_result_ref')}
        original.update(session_scope=D(self.scope), session_snapshot_ref=D(request['session_ref']) if 'snapshot_ref' in request['session_ref'] else None)
        self.original=D(original)
        return self.plans.session(original, execution_id=execution_id)

class ToolFixture:
    """Existing complete_tool performs actual X/F work; this wrapper is not production R authority."""
    def __init__(self, x, plans, adapter, root): self.x,self.plans,self.adapter,self.root=x,plans,adapter,root; self.calls=[]; self.saved={}
    def execute(self, binding, frame, snapshot):
        from validation.components.s.tool_results import complete_tool
        from lore_session.tool_authority import require_tool_target
        target,script=frame['request']['target'],frame['request']['script']; require_tool_target(target,script)
        check((target,script)==('workspace','printf wire_fixture') and not self.calls, 'only the one original fixture native action')
        original=D(self.adapter.original); check(all(binding[k]==original[k] for k in ('operation_id','input_ref','harness_ref','capability_ref','source_result_ref')), 'original tool full binding')
        check(snapshot['session_id']==binding['session_id'], 'original Session owner differs')
        plan=self.plans.tool(original,target,script,execution_id=frame['effect_id'],source_result_ref=frame['source_result_ref'])
        result=complete_tool(self.x,self.plans,plan,dict(target=target),self.plans.peer)
        ref=result['stdout_ref']; raw=self.x.journal.read(ref,65536)
        result['stdout_ref']=dict(path=ref['path'],sha256=ref['sha256'],bytes=len(raw))
        answer=dict(status='RECEIVED',fresh=True,effect_id=frame['effect_id'],**result)
        row=dict(binding=D(binding),frame=D(frame),snapshot=D(snapshot),plan=plan,result=answer)
        self.calls.append(row); self.saved[frame['effect_id']]=row; save(self.root/'actual-tool.json',row)
        check(raw==b'wire_fixture','actual original X tool stdout'); return answer
    def query(self, effect_id, binding):
        row=self.saved.get(effect_id)
        if row is None:return dict(status='UNKNOWN')
        check(row['binding']==binding,'original tool query full binding')
        self.x.query(effect_id,row['plan']['authority']); return D(row['result'])|dict(fresh=False)

def collect(out, target_path, mode='localhost', profile_path=None):
    sys.path[:0]=[str(ROOT),str(ROOT/'validation/components/s')]
    from collector import CaseDriver
    from live_ports import load_target
    from validation.components.s.f_peer import Peer
    from validation.components.s.execution_plans import ExecutionPlans
    from lore_execution import ExecutionStore
    from lore_session.service import SessionService
    from lore_session.provider import ProviderBridge
    from lore_session.snapshot_files import archive, decode, read_ref
    from oracle import pi_jsonl
    target=load_target(target_path); d=x=http=None; results=[]; hooks=[]; cleanup=[]; rescued=False
    started=time.monotonic(); proxy=mode=='proxy'; profile,endpoint=profile_config(profile_path) if proxy else (None,None); scope=dict(namespace=target['fixture_authority']['namespace'],surface_id='fixture-surface',session_id='session-service-live',session_generation=1)
    report=dict(status='FAIL',scope='actual SessionService finite test-only glue; no Runtime/R publication',requests=[],checks=[])
    def test(label, condition): report['checks'].append(dict(label=label,passed=bool(condition))); check(condition,label)
    def original(envelope):
        _,raw=read_ref(envelope['original_archive']); _,files,_=archive(raw); meta=decode(files['metadata.json'])
        path=PurePosixPath(meta['path']).relative_to(meta['cwd']).as_posix(); return files[path],pi_jsonl(files[path])
    def hook(label, value):
        hooks.append(dict(label=label,value=value)); save(out/'service-hooks.json',hooks)
    def http_count():return len(list((out/'provider').glob('*/prepared.json'))) if proxy else len(http.records)
    try:
        d=CaseDriver(dict(setup=dict(session_id=scope['session_id'])),target,out/'fixture')
        peer=Peer(d.ports['f'].fixture_root,target['fixture_authority'])
        plans=ExecutionPlans(d.root/'peer-state/live-plans',peer,scope['namespace'],deps_mount=target['fixture_authority']['deps_mount'])
        x=ExecutionStore(plans.state_root,trusted_config=str(plans.config_path),trusted_config_sha256=plans.config_sha)
        adapter=PlanFixture(plans,scope); tools=ToolFixture(x,plans,adapter,out)
        cases={c['id']:c for c in json.loads((ROOT/'design/g3/provider/cases.json').read_bytes())['cases']}
        responses=[]
        for cid in FIXTURES:
            c=cases[cid]; raw=(ROOT/c['response']['body_path']).read_bytes(); check(hashlib.sha256(raw).hexdigest()==c['response']['sha256'],'frozen original response');responses.append(raw)
        if not proxy:http=HTTPFixture(out/'http',responses)
        def credential():
            path=Path(profile['credential_file']);check(path.stat().st_mode & 0o077 == 0,'restricted credential file required')
            return path.read_text('utf8').strip()
        service=None
        session_ref=dict(owner='S',session_id=scope['session_id']); previous=None; serial=0
        for number,(op,expected) in enumerate([('op-text','answer_saved'),('op-tool','tool_feedback_saved'),('op-follow','answer_saved')]):
            if proxy:
                goal=proxy_protocol()['goals'][number];refs=apply_goal(d,goal);save(out/(op+'-fixed-F-input.json'),dict(goal=goal,refs=refs))
            model_scope=dict(model='gpt-5.6-terra',max_completion_tokens=1024 if proxy else 128,session_scope=scope,**{k:D(d.binding[k]) for k in ('input_ref','harness_ref','capability_ref')})
            bridge=ProviderBridge(out/'provider',endpoint if proxy else http.endpoint,model_scope,credential_provider=credential if proxy else None,timeout=min(60,started+180-time.monotonic()))
            provider=ProxyBudget(bridge,out/'provider',started+180) if proxy else bridge
            service=SessionService(x,plans.snapshots,provider,adapter,tools,checkpoint=hook)
            request=dict(protocol='lore.s/1',session_ref=session_ref,operation_id=op,source_result_ref=previous,**{k:D(d.binding[k]) for k in ('input_ref','harness_ref','capability_ref')})
            drive=None
            for action in ('accept','drive','query'):
                check(time.monotonic()-started<180,'batch deadline');serial+=1; request.update(action=action,session_ref=session_ref)
                before_http=http_count();before_tools=len(tools.calls);before_raw=original(session_ref)[0] if 'snapshot_ref' in session_ref else None
                invoked=time.monotonic()
                result=service.invoke(request,execution_id='live-session-'+str(serial),deadline_monotonic=min(started+180,time.monotonic()+60))
                results.append(dict(action=action,request=D(request),result=result,started=invoked,finished=time.monotonic())); save(out/'invocations.json',results)
                session_ref=result['original_session_snapshot_ref']; raw,native=original(session_ref)
                (out/(op+'-'+action+'.jsonl')).write_bytes(raw)
                test(op+'-'+action+'-released',x.journal.get('live-session-'+str(serial)).get('released') is True)
                if action=='accept':test(op+'-actual-accepted',result['frame']['boundary_kind']=='accepted' and before_http==http_count() and before_tools==len(tools.calls))
                elif action=='drive':
                    drive=result; test(op+'-actual-boundary',result['frame']['boundary_kind']==expected)
                    test(op+'-saved-proposal-source',result['frame']['decision_proposal']['source_result_ref']==result['frame']['operation_result_ref'])
                    if proxy and op!='op-tool':
                        final=result['frame']['decision_proposal']['final']['content'];text=''.join(part.get('text','') for part in final)
                        test(op+'-real-goal-response',text==('LORE_REAL_TEXT_OK' if op=='op-text' else 'wire_fixture'))
                else:
                    test(op+'-query-zero-effects',http_count()==before_http and len(tools.calls)==before_tools)
                    test(op+'-query-exact-original',raw==before_raw and result['frame']==drive['frame'])
            previous=drive['frame']['operation_result_ref']
        test('three-real-HTTP-one-native-tool',http_count()==3 and len(tools.calls)==1 and (proxy or not http.errors))
        raw,native=original(session_ref); entries={v['id']:v for v in native['entries']}
        effects=[v['value'] for v in hooks if v['label']=='effect_received' and v['value']['callback']['type']=='provider.request']
        test('three-original-complete-Pi-Messages',len(effects)==3 and all(entries[v['callback']['response_entry_id']]['message']==v['owner_result']['wire']['normalized']['message'] for v in effects))
        tool_parts=[part for part in effects[1]['owner_result']['wire']['normalized']['message']['content'] if part.get('type')=='toolCall'];test('one-original-native-tool',len(tool_parts)==1)
        actual=json.loads(Path(effects[2]['owner_result']['wire']['artifacts']['request_path']).read_bytes())
        test('actual-third-HTTP-original-tool-feedback',any(m.get('role')=='tool' and m.get('tool_call_id')==tool_parts[0]['id'] and m.get('content')=='wire_fixture' for m in actual['messages']))
        report['real_model_observations']=[]
        for i in range(3):
            wire=effects[i]['owner_result']['wire'];raw_response=Path(wire['artifacts']['response_path']).read_bytes()
            if proxy:
                body=json.loads(raw_response);usage=body['usage'];report['real_model_observations'].append(dict(model_reported=body.get('model'),raw_finish_reason=body['choices'][0].get('finish_reason'),usage=usage,transport=wire['transport'],original_response_path=wire['artifacts']['response_path'],original_request_path=wire['artifacts']['request_path']))
                test('real-'+str(i+1)+'-original-token-budget',usage['prompt_tokens']<=8192 and usage['completion_tokens']<=1024)
            else:
                actual_response=(out/f'http/{i+1:03}-response.http').read_bytes().split(b'\r\n\r\n',1)[1]
                test('HTTP-'+str(i+1)+'-original-response-bytes',actual_response==responses[i])
        test('per-invocation-and-batch-time',all(v['finished']-v['started']<=60 for v in results) and time.monotonic()-started<=180)
        report['status']='PASS'
    except Exception as error:
        report['error']=repr(error);report['traceback']=traceback.format_exc()
        if hasattr(error,'evidence'):report['failure_evidence']=error.evidence
    finally:
        if http:
            http.close();report['http_records']=http.records;report['http_errors']=http.errors
        if x:
            for path in sorted(x.journal.root.glob('*/record.json')):
                record=json.loads(path.read_bytes());binding=record['binding'];cid=binding.get('container_id');volume=binding.get('volume_id')
                before_c=x.engine.inspect(cid) if cid else None;before_v=x.engine.call('GET','/volumes/'+volume,missing=True) if volume else None
                row=dict(record_path=str(path),binding=binding,released=record.get('released'),before_cleanup_container=before_c,before_cleanup_volume=before_v,checkpoint_observations=[])
                if record['request'].get('schema_version')==2:
                    for cp in record.get('checkpoints',{}).values():
                        artifact=cp.get('artifact');row['checkpoint_observations'].append(dict(artifact=artifact,retention=cp.get('retention'),path_exists=Path(artifact['path']).exists() if artifact else None))
                if before_c is not None or before_v is not None:
                    rescued=True
                    if cid:x.engine.call('DELETE','/containers/'+cid+'?force=true',missing=True)
                    if volume:x.engine.call('DELETE','/volumes/'+volume,missing=True)
                row['absent_after_cleanup']=(not cid or x.engine.inspect(cid) is None) and (not volume or x.engine.call('GET','/volumes/'+volume,missing=True) is None);cleanup.append(row)
            x.journal.close()
        report.update(cleanup=cleanup,test_cleanup_needed=rescued,elapsed_seconds=time.monotonic()-started,mode=mode,original_provider_prepared=[str(p) for p in sorted((out/'provider').glob('*/prepared.json'))],original_provider_transports=[str(p) for p in sorted((out/'provider').glob('*/wire/transport.json'))])
        if rescued or not cleanup or not all(v['released'] and v['absent_after_cleanup'] and all(c['retention'].get('state')=='RELEASED' and c['path_exists'] is False for c in v['checkpoint_observations']) for v in cleanup):report['status']='FAIL'
        save(out/'assessment.json',report)
        modules={name:str(Path(m.__file__).resolve()) for name,m in sys.modules.items() if getattr(m,'__file__',None) and (name.startswith('lore_') or name.startswith('validation.'))}
        save(out/'actual-imports.json',modules)
    print(json.dumps({k:report.get(k) for k in ('status','error','elapsed_seconds','test_cleanup_needed')}));return 0 if report['status']=='PASS' else 1

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch');parser.add_argument('--target',type=Path);parser.add_argument('--collect',type=Path);parser.add_argument('--mode',choices=('localhost','proxy'),default='localhost');parser.add_argument('--profile',type=Path);parser.add_argument('--prepare-proxy',action='store_true');a=parser.parse_args()
    if a.profile:a.profile=a.profile.resolve()
    if a.collect:return collect(a.collect,a.target,a.mode,a.profile)
    check(a.batch and Path(a.batch).name==a.batch,'fresh batch name')
    out=ROOT/'validation/session_service/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False)
    if a.prepare_proxy:
        check(a.target and a.profile,'explicit trusted target/profile required');return prepare_proxy(out,a.target,a.profile)
    if a.mode=='proxy' and a.profile is None:
        save(out/'result.json',dict(status='MISSING',reason='Real proxy invocation not authorized for this finite run; trusted endpoint/credential configuration must be separately provided',HTTP=0,Docker=0));print('MISSING: real proxy mode is preparation only');return 2
    check(a.target and a.target.is_file(),'actual original target required');workspace=out/'workspace';sources=[]
    for folder in ['lore_session','lore_session/node','harnesses/minimal','lore_execution','lore_files','lore_provider','validation/session_service','validation/components/s','validation/components/x','validation/components/x_node_profile','design/g3/s','design/g3/x-node-profile','design/g3/system','design/g3/provider','design/g3/provider/fixtures']:
        for source in sorted((ROOT/folder).iterdir()):
            if source.is_file():
                target=workspace/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);sources.append(dict(original=str(source),copy=str(target),sha256=sha(source)))
    source=ROOT/'research/docker-linux/seccomp.json';target=workspace/'research/docker-linux/seccomp.json';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);sources.append(dict(original=str(source),copy=str(target),sha256=sha(source)))
    if a.profile:
        check(a.profile.resolve()==(ROOT/'validation/profiles/openai-proxy.json').resolve(),'fixed trusted profile only')
        for source in [a.profile,ROOT/'design/g4/session-service-real-preparation-001/protocol.json']:
            target=workspace/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);sources.append(dict(original=str(source),copy=str(target),sha256=sha(source)))
    save(out/'sources.json',sources);target=json.loads(a.target.read_bytes())
    for key in ('x_command','f_command'):target[key]=[p.replace(str(ROOT),str(workspace)) if 'validation/components/s/' in p else p for p in target[key]]
    target['artifact_roots']=[str(out),*target.get('artifact_roots',[])];save(out/'target.json',target)
    actual=out/'actual';actual.mkdir();argv=[sys.executable,'-B',str(workspace/'validation/session_service/live.py'),'--collect',str(actual),'--target',str(out/'target.json'),'--mode',a.mode]
    if a.profile:argv.extend(['--profile',str(workspace/a.profile.relative_to(ROOT))])
    with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
        p=subprocess.run(argv,cwd=workspace,env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1'),stdout=stdout,stderr=stderr,timeout=210)
    unchanged=all(sha(v['original'])==v['sha256']==sha(v['copy']) for v in sources)
    result=dict(status='PASS' if p.returncode==0 and unchanged else 'FAIL',exit_code=p.returncode,source_unchanged=unchanged,source_count=len(sources),source_manifest_sha256=sha(out/'sources.json'),argv=argv)
    save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
