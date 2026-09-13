"""Independent file, byte, historical-range, and actual fsync observations for E09-E12."""
import asyncio
import copy
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch
from oracle import input_files
from support import encode,envelope,sha,subject,stream,save
from process_support import spawn_worker,stop_worker

def expected_input(invocation_id,namespace,source,start,end,highwater,filters,rows,input_context,page_size=128):
    events=b"".join(row["data"]+b"\n" for row in rows)
    refs=[{"owner":"E","kind":"event","request_id":json.loads(row["data"])["request_id"],"namespace":namespace,
           "source":json.loads(row["data"])["source"],"sequence":row["sequence"],"subject":row["subject"],"sha256":sha(row["data"])} for row in rows]
    next_sequence=end+1 if end>=start else start
    span={"start_sequence":start,"end_sequence":end,"high_water":highwater,"next_sequence":next_sequence}
    invocation={"schema_version":1,"invocation_id":invocation_id,"namespace":namespace,"source":source,"range":span,
                "filters":filters,"page_size":page_size,"surface_ref":input_context["surface_ref"],"previous_session_ref":input_context["previous_session_ref"]}
    targets={"schema_version":1,"targets":input_context["execution_targets"]}
    files={"events.jsonl":events,"invocation.json":encode(invocation)+b"\n","execution-targets.json":encode(targets)+b"\n"}
    manifest={"schema_version":1,"complete":True,"invocation_id":invocation_id,"namespace":namespace,"source":source,
              "range":span,"filters":filters,"event_refs":refs,
              "files":{name:{"bytes":len(raw),"sha256":sha(raw)} for name,raw in files.items()}}
    files["manifest.json"]=encode(manifest)+b"\n"
    return files

class FsyncObserver:
    """Records actual stdlib fsync fd objects/bytes, then calls the real os.fsync.
    It does not accept a candidate's 'durable' flag. Direct native fsync requires a
    separate observer; absence of these witnesses FAILS this Python profile.
    """
    def __init__(self):self.calls=[];self.original=os.fsync
    def fsync(self,fd):
        st=os.fstat(fd);path=Path(os.readlink(f"/proc/self/fd/{fd}"))
        item={"path":str(path),"dev":st.st_dev,"ino":st.st_ino,"is_dir":path.is_dir()}
        if path.is_file():item.update(bytes=path.stat().st_size,sha256=sha(path.read_bytes()))
        self.original(fd);self.calls.append(item)
    def __enter__(self):self.patch=patch("os.fsync",self.fsync);self.patch.start();return self
    def __exit__(self,*args):self.patch.stop()

class InputCases:
    async def seed(self):
        result=[]
        for i,name in enumerate(("keep","drop","keep")):
            await self.submit(id="event-"+str(i),name=name,payload={"i":i})
            result.append({"sequence":i+1,"subject":subject("n1","event-"+str(i)),"data":encode(envelope("alice","event-"+str(i),"n1",name,{"i":i}))})
        return result
    def assert_input(self,ref,expected):
        self.assertEqual(ref["owner"],"E");self.assertEqual(ref["kind"],"input")
        path=Path(ref["path"]);self.assertTrue(path.is_absolute())
        self.assertTrue(path.resolve().is_relative_to((self.f.root/"inputs").resolve()))
        self.assertFalse(path.is_symlink());self.assertEqual(set(p.name for p in path.iterdir()),set(expected))
        self.assertEqual(ref["root"],{"dev":path.stat().st_dev,"ino":path.stat().st_ino})
        self.assertEqual(ref["manifest_sha256"],sha(expected["manifest.json"]))
        input_files(path,expected)
        save(self.root/("input-observation-"+ref["id"]+".json"),{"path":str(path),"ref":ref,"files":{name:{"bytes":len(raw),"sha256":sha((path/name).read_bytes())} for name,raw in expected.items()}})
    async def test_E09_highwater_complete_actual_input(self):
        rows=await self.seed();self.f.reserve("i1")
        peer=[]
        for index,name in enumerate(("keep","drop","keep")):
            rid="peer-"+str(index);await self.submit(id=rid,namespace="n2",name=name,payload={"i":index})
            peer.append({"sequence":index+1,"subject":subject("n2",rid),"data":encode(envelope("alice",rid,"n2",name,{"i":index}))})
        from oracle import raw_history
        raw_history(await self.f.rows("n2"),peer)
        seen=[]
        async def checkpoint(label,record):
            if label=="after_input_highwater_before_scan":
                self.assertEqual(record["high_water"],3);seen.append(record)
                await self.submit(id="late",name="keep",payload={"late":True})
        service=await self.f.new_service(checkpoint=checkpoint)
        with FsyncObserver() as observer:ref=await self.f.prepare(service=service)
        self.assertEqual(len(seen),1)
        expected=expected_input("i1","n1","alice",1,3,3,{},rows,self.f.input_context)
        self.assert_input(ref,expected)
        for name,raw in expected.items():
            path=Path(ref["path"])/name;st=path.stat()
            self.assertTrue(any(x["dev"]==st.st_dev and x["ino"]==st.st_ino and x.get("sha256")==sha(raw) for x in observer.calls),"actual complete-file fsync missing "+name)
        for directory in (Path(ref["path"]),Path(ref["path"]).parent):
            st=directory.stat()
            self.assertTrue(any(x["is_dir"] and x["dev"]==st.st_dev and x["ino"]==st.st_ino for x in observer.calls),"actual published-directory fsync missing")
        save(self.root/"fsync-observations.json",observer.calls)
        self.assertEqual(len(await self.f.rows()),4)
        self.assertTrue(Path(self.f.input_context["surface_ref"]["path"]).is_dir())
        self.assertEqual(Path(self.f.input_context["previous_session_ref"]["path"]).read_bytes(),b"session-original")
    async def test_E10_filter_page_missing_and_empty(self):
        rows=await self.seed()
        # page_size bounds source sequence coverage, not only count after filtering.
        self.f.profile["page_size"]=2
        service=await self.f.new_service()
        self.f.reserve("page",filters={"names":["keep"]})
        ref=await self.f.prepare("page",filters={"names":["keep"]},service=service)
        self.assert_input(ref,expected_input("page","n1","alice",1,2,3,{"names":["keep"]},[rows[0]],self.f.input_context,page_size=2))
        self.f.reserve("last",start=3,filters={"names":["keep"]})
        last=await self.f.prepare("last",start=3,filters={"names":["keep"]},service=service)
        self.assert_input(last,expected_input("last","n1","alice",3,3,3,{"names":["keep"]},[rows[2]],self.f.input_context,page_size=2))
        self.f.reserve("empty",namespace="n2")
        empty=await self.f.prepare("empty",namespace="n2",service=service)
        self.assert_input(empty,expected_input("empty","n2","alice",1,0,0,{},[],self.f.context_for("n2"),page_size=2))
        await self.reject("denied",service.scan,"eve","n1",1,{})
        await self.reject("invalid",service.scan,"alice","n1",5,{})
        await self.f.js.delete_msg(stream("n1"),2)
        self.f.reserve("missing",filters={"names":["keep"]})
        await self.reject("history_missing",self.f.prepare,"missing",filters={"names":["keep"]},service=service)
        self.assertIsNone(self.f.stores[0].query_input("alice","missing"))
        await self.reject("history_missing",service.scan,"alice","n1",1,{"names":["keep"]})
    async def test_E11_binding_restart_read_not_ACK(self):
        rows=await self.seed();self.f.reserve("i1")
        ref=await self.f.prepare()
        expected=expected_input("i1","n1","alice",1,3,3,{},rows,self.f.input_context)
        before=self.f.sql("select id,phase,payload_json from requests where id='i1'")
        for _ in range(2):self.assert_input(ref,expected)
        copied=self.root/"task-copy";shutil.copytree(ref["path"],copied);shutil.rmtree(copied)
        self.assertEqual(self.f.sql("select id,phase,payload_json from requests where id='i1'"),before)
        self.assertIn("i1",[x["id"] for x in self.f.stores[0].pending()])
        for principal,start,filters in [("bob",1,{}),("alice",2,{}),("alice",1,{"names":["keep"]})]:
            await self.reject("conflict",self.f.prepare,"i1",start=start,filters=filters,principal=principal)
        changed_context=copy.deepcopy(self.f.input_context);changed_context["previous_session_ref"]["id"]="other-session"
        await self.reject("conflict",self.f.service.prepare_input,"alice","i1","n1",1,{},str(self.f.root/"inputs"),input_context=changed_context)
        await self.submit(id="later",payload={"new":True})
        self.assertEqual(await self.f.prepare(),ref)
        worker=await spawn_worker(self.f,"fresh-input",self.f.config("lookup",context="alice",invocation_id="i1"))
        config=await stop_worker(worker,kill=False)
        fresh=json.loads(Path(config["reply"]).read_text())["result"]
        self.assertEqual(fresh,ref);self.assert_input(fresh,expected)
    async def test_E12_missing_incomplete_and_corrupt_files(self):
        rows=await self.seed();self.f.reserve("i1")
        ref=await self.f.prepare();expected=expected_input("i1","n1","alice",1,3,3,{},rows,self.f.input_context)
        path=Path(ref["path"]);baseline=await self.f.rows()
        for mode in ("missing","truncated","equal_length","wrong_event_ref","incomplete"):
            # Restore fixture bytes before each isolated negative; no candidate success is fabricated.
            for name,raw in expected.items():(path/name).write_bytes(raw)
            if mode=="missing":(path/"events.jsonl").unlink()
            elif mode=="truncated":(path/"events.jsonl").write_bytes(expected["events.jsonl"][:-1])
            elif mode=="equal_length":
                raw=expected["events.jsonl"];(path/"events.jsonl").write_bytes(raw.replace(b"keep",b"evil",1))
                self.assertEqual((path/"events.jsonl").stat().st_size,len(raw))
            else:
                manifest=json.loads(expected["manifest.json"])
                if mode=="wrong_event_ref":manifest["event_refs"][0]["sequence"]=2
                else:manifest["complete"]=False
                (path/"manifest.json").write_bytes(encode(manifest)+b"\n")
            await self.reject("input_invalid",self.f.service.lookup_input,"alice","i1")
            from oracle import raw_history
            raw_history(await self.f.rows(),baseline)
        for name,raw in expected.items():(path/name).write_bytes(raw)
        self.assertEqual(await self.f.service.lookup_input("alice","i1"),ref)
