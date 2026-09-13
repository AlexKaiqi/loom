"""Fixed E01-E15 real-component inventory. Missing code is ERROR, never skip."""
import asyncio
import copy
import json
import math
import os
from pathlib import Path
import unittest
import nats
from nats.js.api import DiscardPolicy
from fixture import Fixture,AUTHORITY
from support import encode,envelope,subject,stream,save,sha
from oracle import raw_history,application_origin
from process_support import spawn_worker,wait_marker,stop_worker
from input_cases import InputCases

class EventContract(InputCases,unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        evidence=os.environ.get("LORE_E_EVIDENCE_DIR")
        if not evidence:raise RuntimeError("explicit LORE_E_EVIDENCE_DIR required; use run_contract.py")
        self.root=Path(evidence)/self._testMethodName
        if self._testMethodName.split("_")[1] in {"E04","E05","E07","E13"}:
            self.root.mkdir(parents=True,exist_ok=False);self.f=None;return
        self.f=Fixture(self.root)
        self.addAsyncCleanup(self.f.close)
        await self.f.start()
    async def extra(self,label,**kw):
        f=Fixture(self.root/label,**kw);self.addAsyncCleanup(f.close);await f.start();return f
    async def reject(self,code,fn,*args,**kwargs):
        try:await asyncio.wait_for(fn(*args,**kwargs),5)
        except Exception as error:self.assertEqual(getattr(error,"code",None),code,repr(error))
        else:self.fail("missing exact contract rejection "+code)
    async def submit(self,id="e1",namespace="n1",name="notice",payload=None,principal="alice",f=None,service=None):
        f=f or self.f
        return await asyncio.wait_for((service or f.service).submit(principal,id,namespace,name,{"text":"original-雪"} if payload is None else payload),5)
    async def assert_original(self,f,id="e1",namespace="n1",name="notice",payload=None,principal="alice",seq=1):
        row={"sequence":seq,"subject":subject(namespace,id),"data":encode(envelope(principal,id,namespace,name,{"text":"original-雪"} if payload is None else payload))}
        raw_history(await f.rows(namespace),[row]);return row
    def assert_control_receipt(self,f,result,outcome):
        from receipt_authority import check_receipt,original_request,request_fields
        request=original_request(f.root,result["request_id"])
        row=f.stores[0].query("runtime",result["request_id"])
        self.assertEqual(row["phase"],"confirmed")
        ref=row["receipt_ref"]
        self.assertEqual(ref["facility_ref"],result["receipt_ref"])
        self.assertEqual(ref["outcome"],outcome);self.assertIs(ref["definite"],True)
        self.assertEqual({key:ref[key] for key in request_fields(request)},request_fields(request))
        self.assertTrue(check_receipt(f.root,f.server.url,ref,"receipt",request_fields(request)))
        save(f.root/("control-receipt-"+sha(result["request_id"].encode())+".json"),{"request":request,"query":row,"outward":result})
        return ref
    async def test_E01_origin_authority(self):
        before=self.f.sql("select count(*) from requests")
        await self.reject("invalid",self.f.service.submit,{"principal":"runtime"},"bad0","n1","done",{})
        await self.reject("denied",self.f.service.submit,"eve","bad1","n1","done",{})
        await self.reject("denied",self.f.service.emit_observation,"alice","bad2","n1",{"registration_id":"invented"})
        for field in ("origin","principal","system"):
            await self.reject("invalid",self.f.service.submit,"alice","bad-"+field,"n1","done",{field:"runtime"})
        self.assertEqual(self.f.sql("select count(*) from requests"),before)
        result=await self.submit(name="done");self.assertEqual(result["status"],"CONFIRMED")
        row=await self.assert_original(self.f,name="done")
        application_origin(json.loads(row["data"]),"alice")
        await self.submit(id="e2",name="fail")
        raw_history(await self.f.rows(),[row,{"sequence":2,"subject":subject("n1","e2"),"data":encode(envelope("alice","e2","n1","fail",{"text":"original-雪"}))}])
        try:self.f.stores[0].resolve("runtime","n1","surface-original","read")
        except Exception as error:self.assertEqual(getattr(error,"code",None),"not_found")
        else:self.fail("application event unexpectedly registered a resource")
    async def test_E02_exact_byte_boundary(self):
        for rid,payload in [("bad id",{}),("",{}),("nan",{"n":math.nan}),("set",{"x":set()})]:
            await self.reject("invalid",self.f.service.submit,"alice",rid,"n1","notice",payload)
        self.assertEqual(self.f.sql("select count(*) from requests"),[(0,)])
        base=encode(envelope("alice","limit","n1","notice",{"text":""}))
        payload={"text":"x"*(65536-len(base))}
        self.assertEqual(len(encode(envelope("alice","limit","n1","notice",payload))),65536)
        await self.submit(id="limit",payload=payload)
        await self.assert_original(self.f,id="limit",payload=payload)
        oversized={"text":payload["text"]+"x"}
        await self.reject("invalid",self.f.service.submit,"alice","above","n1","notice",oversized)
        self.assertEqual(self.f.sql("select count(*) from requests"),[(1,)])
    async def test_E03_complete_identity_conflict(self):
        original=await self.submit()
        self.assert_control_receipt(self.f,original,"positive")
        self.assertEqual(await self.submit(),original)
        for principal,namespace,name,payload in [("bob","n1","notice",{"text":"original-雪"}),("alice","n2","notice",{"text":"original-雪"}),("alice","n1","done",{"text":"original-雪"}),("alice","n1","notice",{"text":"changed"})]:
            await self.reject("conflict",self.f.service.submit,principal,"e1",namespace,name,payload)
            await self.assert_original(self.f)
        self.assertEqual(len([a for a in self.f.proxy.audit if a.get("direction")=="publish"]),1)
    async def test_E04_confirmed_server_SIGKILL(self):
        for repeat in range(3):
            f=await self.extra("repeat-"+str(repeat));result=await self.submit(f=f)
            self.assertEqual(result["status"],"CONFIRMED");before=await f.rows()
            await f.observer.close();f.server.kill();await f.server.start()
            f.observer=await f.server.connect();f.js=f.observer.jetstream()
            raw_history(await f.rows(),before)
            self.assertEqual(result["receipt_ref"]["sequence"],1)
            await f.close()
    async def test_E05_actual_PubAck_loss(self):
        for repeat in range(3):
            f=await self.extra("repeat-"+str(repeat))
            f.proxy.drop_next_ack=True
            worker=await spawn_worker(f,"lost-ack",f.config("submit",context="alice",request_id="e1",namespace="n1",name="notice",payload={"text":"original-雪"}))
            try:await asyncio.wait_for(f.proxy.dropped.wait(),5)
            finally:await stop_worker(worker,kill=True)
            self.assertFalse(Path(worker[3]["reply"]).exists())
            await self.assert_original(f)
            before=len([a for a in f.proxy.audit if a.get("direction")=="publish"])
            fresh=await f.new_service()
            result=await asyncio.wait_for(fresh.query("alice","e1"),5)
            self.assertEqual(result["status"],"CONFIRMED");self.assertEqual(result["receipt_ref"]["sequence"],1)
            self.assert_control_receipt(f,result,"positive")
            self.assertEqual(len([a for a in f.proxy.audit if a.get("direction")=="publish"]),before)
            await self.assert_original(f);await f.close()
    async def test_E06_dispatched_unknown_no_resend(self):
        f=self.f;marker=f.root/"dispatched.marker"
        config=f.config("submit",context="alice",request_id="uncertain",namespace="n1",name="notice",payload={"text":"u"})
        config.update(cut="after_dispatch_before_publish",marker=str(marker))
        worker=await spawn_worker(f,"issued-no-proof",config)
        try:await wait_marker(worker[0],marker)
        finally:await stop_worker(worker,kill=True)
        before=len([a for a in f.proxy.audit if a.get("direction")=="publish"])
        for _ in range(2):
            result=await f.service.query("alice","uncertain")
            self.assertEqual(result["status"],"UNKNOWN");self.assertEqual(result["request_id"],"uncertain")
        self.assertEqual(len([a for a in f.proxy.audit if a.get("direction")=="publish"]),before)
        self.assertEqual(f.sql("select phase from requests where id='uncertain'"),[("issued",)])
        await f.observer.close();f.server.kill()
        unavailable=await asyncio.wait_for(f.service.query("alice","uncertain"),5)
        self.assertEqual(unavailable["status"],"UNKNOWN")
        self.assertEqual(f.sql("select phase from requests where id='uncertain'"),[("issued",)])
        await f.server.start();f.observer=await f.server.connect();f.js=f.observer.jetstream()
        fresh=await f.new_service()
        self.assertEqual((await fresh.query("alice","uncertain"))["status"],"UNKNOWN")
        self.assertEqual(len([a for a in f.proxy.audit if a.get("direction")=="publish"]),before)
        other=await self.submit(id="other",namespace="n2",service=fresh)
        self.assertEqual(other["status"],"CONFIRMED")
        await self.assert_original(f,id="other",namespace="n2")
    async def fill(self,f):
        saved=[];negative=None
        for i in range(8):
            result=await self.submit(id="cap-"+str(i),payload={"text":"x"*256},f=f)
            if result["status"]=="REJECTED":negative=(i,result);break
            self.assertEqual(result["status"],"CONFIRMED");saved.append(i)
        self.assertTrue(saved);self.assertIsNotNone(negative,"fixed capacity must be reached within 8 attempts")
        return saved,negative
    async def test_E07_real_negative_receipt(self):
        f=await self.extra("capacity",max_bytes=1024)
        saved,(index,result)=await self.fill(f)
        self.assertEqual(result["receipt_ref"]["outcome"],"rejected")
        wrapper=self.assert_control_receipt(f,result,"negative")
        self.assertTrue(result["receipt_ref"]["error"]["description"])
        original=await f.rows()
        self.assertEqual(len(original),len(saved))
        before=len([a for a in f.proxy.audit if a.get("direction")=="publish"])
        self.assertEqual(await self.submit(id="cap-"+str(index),payload={"text":"x"*256},f=f),result)
        self.assertEqual(len([a for a in f.proxy.audit if a.get("direction")=="publish"]),before)
        raw_history(await f.rows(),original)
        self.assertEqual(f.sql("select phase from requests where id=?",("cap-"+str(index),)),[("confirmed",)])
        self.assertEqual(await f.service.query("alice","cap-"+str(index)),result)
        worker=await spawn_worker(f,"negative-fresh-query",f.config("query",context="alice",request_id="cap-"+str(index)))
        await stop_worker(worker,kill=False)
        self.assertEqual(json.loads(Path(worker[3]["reply"]).read_text())["result"],result)
        from receipt_authority import check_receipt
        self.assertTrue(check_receipt(f.root,f.server.url,wrapper,"receipt"))
        self.assertEqual(len([a for a in f.proxy.audit if a.get("direction")=="publish"]),before)
    async def test_E08_four_actual_connections(self):
        services=[self.f.service]+[await self.f.new_service() for _ in range(3)]
        connections=await self.f.server.monitoring()
        self.assertGreaterEqual(connections["num_connections"],5,"four E connections plus separate observer required")
        save(self.root/"four-connections.json",connections)
        async def writer(index):
            for i in range(8):
                result=await self.submit(id=f"w{index}-{i}",payload={"writer":index,"index":i},service=services[index])
                self.assertEqual(result["status"],"CONFIRMED")
        await asyncio.gather(*(writer(i) for i in range(4)))
        rows=await self.f.rows();self.assertEqual([r["sequence"] for r in rows],list(range(1,33)))
        actual={}
        for row in rows:
            value=json.loads(row["data"]);actual[value["request_id"]]=row["data"]
            self.assertEqual(row["subject"],subject("n1",value["request_id"]))
        self.assertEqual(actual,{f"w{w}-{i}":encode(envelope("alice",f"w{w}-{i}","n1","notice",{"writer":w,"index":i})) for w in range(4) for i in range(8)})
        self.assertEqual(await self.f.rows("n2"),[])
        await self.reject("denied",self.f.service.scan,"eve","n1",1,{})
    async def test_E13_retention_profile(self):
        f=await self.extra("capacity",max_bytes=1024)
        saved,_=await self.fill(f);rows=await f.rows()
        self.assertEqual(len(rows),len(saved))
        for row,i in zip(rows,saved):self.assertEqual(row["data"],encode(envelope("alice","cap-"+str(i),"n1","notice",{"text":"x"*256})))
        cfg=(await f.js.stream_info(stream("n1"))).config
        self.assertEqual(cfg.discard,DiscardPolicy.NEW);self.assertEqual(cfg.max_age,0)
        for field,value in [("discard",DiscardPolicy.OLD),("max_age",300)]:
            cfg=(await f.js.stream_info(stream("n1"))).config;original=getattr(cfg,field);setattr(cfg,field,value)
            await f.js.update_stream(config=cfg)
            await self.reject("configuration_error",f.new_service)
            setattr(cfg,field,original);await f.js.update_stream(config=cfg)
    async def test_E14_replay_without_notification(self):
        await self.submit(id="before")
        first=await self.f.service.scan("alice","n1",1,{})
        self.assertEqual([r["request_id"] for r in first["events"]],["before"])
        await self.submit(id="gap")
        # No consumer or notification is delivered to this scanner; the original start is authoritative.
        again=await self.f.service.scan("alice","n1",1,{})
        self.assertEqual([r["request_id"] for r in again["events"]],["before","gap"])
        fresh=await self.f.new_service()
        replay=await fresh.scan("alice","n1",1,{})
        self.assertEqual(replay,again)
    async def test_E15_no_connection_per_wait(self):
        await self.submit()
        before=await self.f.server.monitoring()
        consumers_before=(await self.f.js.stream_info(stream("n1"))).state.consumer_count
        for _ in range(12):await self.f.service.scan("alice","n1",1,{})
        after=await self.f.server.monitoring()
        self.assertEqual(after["num_connections"],before["num_connections"])
        self.assertEqual((await self.f.js.stream_info(stream("n1"))).state.consumer_count,consumers_before)
        save(self.root/"connection-observations.json",{"before":before,"after_scans":after})
        await self.f.service.close()
        for _ in range(30):
            closed=await self.f.server.monitoring()
            if closed["num_connections"]<after["num_connections"]:break
            await asyncio.sleep(.02)
        self.assertEqual(closed["num_connections"],1,"only the independent observer connection may remain")
        save(self.root/"connection-after-close.json",closed)
if __name__=="__main__":unittest.main()
