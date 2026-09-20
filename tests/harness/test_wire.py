"""An independent loom/1 peer exercises the real Python Harness process.

This verifies protocol composition and large record publication, not Linux role
isolation. Those boundaries require the separate real facility acceptance.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class HarnessWireTests(unittest.TestCase):
    def test_large_projection_uses_record_and_explicit_model_start(self):
        with tempfile.TemporaryDirectory(prefix='loom-harness-wire-') as temporary:
            root = Path(temporary)
            (root/'surface').mkdir();(root/'outputs').mkdir()
            large = '长期上下文。' * 300000
            (root/'surface/main.md').write_text('```include\npath="surface/reference.md"\n```\n```facts\n```\n')
            (root/'surface/reference.md').write_text(large)
            payload = json.dumps({'text':'fixed input'}).encode()
            payload_path = root/'input.json';payload_path.write_bytes(payload)
            ref = {'sha256':hashlib.sha256(payload).hexdigest(),'size_bytes':str(len(payload)),'media_type':'application/json'}
            with sqlite3.connect(root/'facts.sqlite') as db:
                db.executescript('CREATE TABLE view_meta(schema_version,view_id,fact_watermark);'
                    'INSERT INTO view_meta VALUES(1,"fixed-view","1");'
                    'CREATE TABLE facts(ordinal,fact_id,kind,source,record_ref,record_path);')
                db.execute('INSERT INTO facts VALUES(1,"F1","work.message","host",?,?)',(json.dumps(ref),str(payload_path)))
            parent,child=socket.socketpair();parent.settimeout(15)
            env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TMPDIR')}
            process=subprocess.Popen([sys.executable,str(ROOT/'harnesses/kernel/worker.py')],env=env,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                pass_fds=(child.fileno(),3),preexec_fn=lambda:os.dup2(child.fileno(),3))
            child.close();stream=parent.makefile('rwb',buffering=0)
            records={};callbacks=[]
            def send(value):
                raw=json.dumps(value,separators=(',',':')).encode()
                self.assertLess(len(raw),65536,'test accidentally sends bulk data on control channel')
                stream.write(raw+b'\n')
            def request(identity,method,params):
                send({'jsonrpc':'2.0','id':identity,'method':method,'params':params})
                while True:
                    raw=stream.readline(65538)
                    self.assertTrue(raw.endswith(b'\n'))
                    self.assertLess(len(raw),65536,'Harness returned bulk projection on control channel')
                    value=json.loads(raw)
                    if value.get('id')==identity:
                        self.assertNotIn('error',value)
                        return value['result']
                    p=value['params'];method=value['method'];callbacks.append(method)
                    if method=='record.put':
                        path=root/'outputs'/p['path']
                        self.assertEqual(path.parent,root/'outputs')
                        data=path.read_bytes()
                        saved={'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':str(len(data)),'media_type':p['media_type']}
                        records[saved['sha256']]=data
                        result=saved
                    elif method=='projection.publish':
                        self.assertEqual(p['content_version'],'fixed-content')
                        self.assertEqual(p['view_id'],'fixed-view')
                        self.assertIn(p['record_ref']['sha256'],records)
                        result={'projection_ref':p['record_ref']}
                    elif method=='model.start':
                        self.assertIn(p['projection_ref']['sha256'],records)
                        result={'accepted':True,'projection_ref':p['projection_ref'],'request_key':p['request_key']}
                    elif method=='checkpoint.commit':
                        self.assertEqual(p['previous_checkpoint_id'],'native-checkpoint')
                        self.assertEqual(p['resource_copies'],[])
                        result={'checkpoint_id':'policy-checkpoint'}
                    elif method=='round.handoff':
                        self.assertEqual(p['checkpoint_id'],'policy-checkpoint')
                        self.assertEqual(p['handled_input_ids'],['F1'])
                        self.assertEqual(p['intent'],'wait')
                        result={'accepted':True,'execution_fencing':'pending'}
                    else:
                        self.fail('unexpected callback: '+method)
                    send({'jsonrpc':'2.0','id':value['id'],'result':result})
            try:
                send({'jsonrpc':'2.0','id':'missing-capability','method':'session.hello','params':{
                    'protocol_version':'loom/1','schema_version':1,'role':'runtime','peer_role':'harness',
                    'max_frame_bytes':4194304,'capabilities':[],'required_capabilities':['harness/1']}})
                denied=json.loads(stream.readline(65538))
                self.assertEqual(denied['id'],'missing-capability')
                self.assertIn('error',denied,'reference Harness silently disabled required feedback')
                hello=request('hello','session.hello',{'protocol_version':'loom/1','schema_version':1,'role':'runtime','peer_role':'harness',
                    'max_frame_bytes':4194304,'capabilities':['context.feedback/1'],'required_capabilities':['harness/1','context.feedback/1']})
                self.assertEqual(hello['role'],'harness')
                result=request('start','policy.start',{'output_directory':str(root/'outputs'),'files_root':str(root),
                    'facts_database':str(root/'facts.sqlite'),'view_id':'fixed-view','fact_watermark':'1',
                    'required_fact_ids':['F1'],'content_version':'fixed-content','harness_ref':'fixed-strategy',
                    'model_operation':'model.start','model_semantics':{'maxTokens':128}})
                self.assertTrue(result['accepted'])
                body=records[result['projection_ref']['sha256']]
                self.assertGreater(len(body),4194304)
                saved=json.loads(body)
                self.assertIn(large,saved['context']['messages'][0]['content'])
                self.assertEqual(saved['selection']['fact_ids'],['F1'])
                self.assertEqual(callbacks,['record.put','projection.publish','model.start'])
                native = json.dumps({'message':{'stopReason':'toolUse'},'context':{'messages':[{'role':'user','content':large}]}}).encode()
                native_path=root/'native.json';native_path.write_bytes(native)
                native_ref={'sha256':hashlib.sha256(native).hexdigest(),'size_bytes':str(len(native)),'media_type':'application/json'}
                self.assertGreater(len(native),4194304)
                self.assertTrue(request('continue','policy.continue',{'turn_path':str(native_path),'turn_ref':native_ref}))
                result=request('finish','policy.finish',{'content_version':'fixed-content','previous_checkpoint_id':'native-checkpoint','resource_copies':[],'claimed_input_ids':['F1']})
                self.assertEqual(result['execution_fencing'],'pending')
                self.assertEqual(callbacks[-2:],['checkpoint.commit','round.handoff'])
            finally:
                parent.shutdown(socket.SHUT_RDWR);stream.close();parent.close()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
                diagnostics=process.stderr.read().decode();process.stderr.close()
                self.assertEqual(process.returncode,0,diagnostics)


if __name__=='__main__':unittest.main()
