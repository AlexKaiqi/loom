"""Fixed observation supplement; actual E/R/NATS only, independent original-byte oracle."""
import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from fixture import Fixture
from support import encode,envelope,sha,subject,stream,save
from observation_authority import registration_ref,check_observation,runtime_bytes,controls
from receipt_authority import check_receipt,original_request,request_fields
IDS=["EO"+str(i).zfill(2) for i in range(1,11)]

async def run(out):
    result={"status":"FAIL","case_ids":IDS,"tests_run":0,"errors":[],"failed_checks":[],"preparation_controls":{"status":"PASS","checks":controls()},"skipped":[],"cases":[]}
    fixture=None
    try:
        if not all(x["passed"] for x in result["preparation_controls"]["checks"]):
            result["preparation_controls"]["status"]="FAIL"
            raise AssertionError("observation oracle controls failed")
        fixture=Fixture(out/"actual");await fixture.start();f=fixture
        original_checker=f.stores[0].reference_checker
        f.stores[0].reference_checker=lambda ref,purpose,expected=None:check_observation(f.root,ref,purpose,expected) if purpose=="observation" else original_checker(ref,purpose,expected)
        for operation,resource,namespace,kind in [("oreg1","observed1","n1","surface"),("oreg2","observed2","n1","surface"),("oregw","observedw","n1","workspace"),("oregn2","observedn2","n2","surface")]:
            directory=f.root/resource;directory.mkdir()
            f.stores[0].register("runtime",operation,resource,namespace,kind,str(directory),f.harness,{"runtime":["read","write"]})
        refs={key:registration_ref(f.root,key) for key in ["oreg1","oreg2","oregw","oregn2"]}
        ref=refs["oreg1"]
        raw=encode(envelope("runtime","observation-1","n1","surface.registered",{"observation_ref":ref},origin="runtime"))
        save(out/"expected-original.json",{"reference":ref,"raw_utf8":raw.decode(),"sha256":sha(raw),"subject":subject("n1","observation-1"),"sequence":1})
        async def state():
            counts={ns:(await f.js.stream_info(stream(ns))).state.messages for ns in ["n1","n2","n3"]}
            return {"accepted_events":f.sql("select count(*) from requests where kind='event'")[0][0],"published":len([x for x in f.proxy.audit if x.get("direction")=="publish"]),"messages":counts}
        async def rejection(context,value,label,code="reference_invalid",absent=False):
            before=await state();checker=f.stores[0].reference_checker
            if absent:f.stores[0].reference_checker=None
            error=None
            try:
                await asyncio.wait_for(f.service.emit_observation(context,label,"n1",value),5)
            except Exception as exc:error={"code":getattr(exc,"code",None),"type":type(exc).__name__,"message":str(exc)}
            finally:f.stores[0].reference_checker=checker
            after=await state();save(out/(label+".json"),{"ref":value,"context":context,"before":before,"after":after,"error":error})
            assert error is not None and error["code"]==code,(label,error,code)
            assert after==before,(label,"rejection changed R or NATS",before,after)
        for case in IDS:
            row={"id":case,"status":"PASS"};result["tests_run"]+=1
            try:
                if case=="EO01":
                    reply=await asyncio.wait_for(f.service.emit_observation("runtime","observation-1","n1",ref),5)
                    assert reply["status"]=="CONFIRMED",reply
                    msg=await f.js.get_msg(stream("n1"),seq=1);runtime_bytes(msg.data,raw)
                    assert msg.subject==subject("n1","observation-1") and msg.headers.get("Nats-Msg-Id")=="observation-1"
                    assert await f.service.emit_observation("runtime","observation-1","n1",ref)==reply
                    assert await f.service.query("runtime","observation-1")==reply
                    current=await state();assert current=={"accepted_events":1,"published":1,"messages":{"n1":1,"n2":0,"n3":0}},current
                    actual=f.stores[0].query("runtime","observation-1");request=original_request(f.root,"observation-1")
                    assert actual["phase"]=="confirmed" and actual["receipt_ref"]["facility_ref"]==reply["receipt_ref"]
                    assert check_receipt(f.root,f.server.url,actual["receipt_ref"],"receipt",request_fields(request))
                    (out/"original-message.bin").write_bytes(msg.data);save(out/"positive.json",{"reply":reply,"control":actual,"original_request":request,"headers":dict(msg.headers),"state":current})
                elif case=="EO02":
                    await rejection("alice",ref,"denied-principal","denied")
                    await rejection({"principal":"runtime"},ref,"forged-context","invalid")
                elif case=="EO03":await rejection("runtime",{**ref,"owner":"F"},"wrong-owner")
                elif case=="EO04":await rejection("runtime",refs["oregw"],"real-workspace")
                elif case=="EO05":await rejection("runtime",refs["oregn2"],"real-other-namespace")
                elif case=="EO06":
                    await rejection("runtime",{**ref,"id":"oreg2"},"real-other-operation")
                    second=refs["oreg2"]
                    prior_control=f.stores[0].query("runtime","observation-1")
                    await rejection("runtime",second,"observation-1","conflict")
                    assert f.stores[0].query("runtime","observation-1")==prior_control
                    first_message=await f.js.get_msg(stream("n1"),seq=1);runtime_bytes(first_message.data,raw)
                    expected=encode(envelope("runtime","observation-2","n1","surface.registered",{"observation_ref":second},origin="runtime"))
                    (out/"expected-second.bin").write_bytes(expected)
                    reply=await f.service.emit_observation("runtime","observation-2","n1",second)
                    assert reply["status"]=="CONFIRMED",reply
                    message=await f.js.get_msg(stream("n1"),seq=2);runtime_bytes(message.data,expected)
                    assert message.subject==subject("n1","observation-2") and message.headers.get("Nats-Msg-Id")=="observation-2"
                    (out/"second-original-message.bin").write_bytes(message.data)
                    assert await state()=={"accepted_events":2,"published":2,"messages":{"n1":2,"n2":0,"n3":0}}
                elif case=="EO07":await rejection("runtime",{**ref,"resource_id":"observed2"},"wrong-resource")
                elif case=="EO08":await rejection("runtime",{**ref,"revision":2},"wrong-revision")
                elif case=="EO09":await rejection("runtime",{**ref,"sha256":"0"*64},"wrong-original-hash")
                elif case=="EO10":
                    await rejection("runtime",{**ref,"id":"absent-original"},"missing-original")
                    await rejection("runtime",ref,"missing-authority",absent=True)
            except Exception as exc:
                row.update(status="FAIL",error={"type":type(exc).__name__,"message":str(exc)})
                result["failed_checks"].append(case)
            result["cases"].append(row)
        result["status"]="PASS" if not result["failed_checks"] and result["tests_run"]==10 else "FAIL"
    except Exception as exc:
        missing="MISSING" in str(exc)
        result["status"]="MISSING" if missing else "FAIL"
        result["errors"].append({"type":type(exc).__name__,"message":str(exc)})
        for case in IDS[result["tests_run"]:]:result["cases"].append({"id":case,"status":"MISSING" if missing else "ERROR"})
        result["tests_run"]=10
    finally:
        if fixture is not None:
            try:await fixture.close()
            except Exception as exc:result["status"]="FAIL";result["errors"].append({"cleanup":str(exc)})
        result["cleanup"]={"owned_nats_reaped":fixture is None or fixture.server.proc is None or fixture.server.proc.poll() is not None}
        if not result["cleanup"]["owned_nats_reaped"]:result["status"]="FAIL"
    save(out/"result.json",result);return result

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--batch",required=True);args=parser.parse_args()
    out=Path(__file__).parent/"evidence"/args.batch;out.mkdir(parents=True,exist_ok=False)
    result=asyncio.run(asyncio.wait_for(run(out),45))
    print(json.dumps({"status":result["status"],"tests_run":result["tests_run"],"failed_checks":result["failed_checks"]}))
    raise SystemExit(0 if result["status"]=="PASS" else 2 if result["status"]=="MISSING" else 1)
