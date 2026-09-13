"""ER01 preregistered authority probe. SQLite rows are fixtures, never fake R/E."""
import asyncio
import base64
import copy
import json
from pathlib import Path
import sqlite3
import sys
import traceback
import nats
from nats.js.api import StreamConfig,StorageType,DiscardPolicy
from support import Server,WireProxy,stream,subject,envelope,encode,save,sha,PYTHON,BINARY
from receipt_authority import wrapper_for_fixture,request_fields

async def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).parent
    result={"scope":"receipt authority readiness only; explicit original-request SQLite fixture, actual NATS; NOT ControlStore/EventService acceptance","inputs":{str(p):sha(p.read_bytes()) for p in [source/"receipt-preparation-protocol.json",source/"receipt_preparation.py",source/"receipt_authority.py",source/"reference_probe.py",source/"support.py",BINARY]},"checks":[],"errors":[]}
    snapshot=out/"source";snapshot.mkdir()
    for name in ("receipt-preparation-protocol.json","receipt_preparation.py","receipt_authority.py","reference_probe.py","support.py"):(snapshot/name).write_bytes((source/name).read_bytes())
    server=Server(out/"nats");proxy=WireProxy(server,out);observer=None;client=None
    with sqlite3.connect(out/"control.sqlite") as db:db.execute("create table requests(id text primary key,principal text,namespace text,kind text,payload_json text)")
    def original(rid,namespace,raw):
        req={"principal":"alice","id":rid,"namespace":namespace,"kind":"event","payload":{"subject":subject(namespace,rid),"event_sha256":sha(raw),"event_bytes":len(raw)}}
        with sqlite3.connect(out/"control.sqlite") as db:db.execute("insert into requests values(?,?,?,?,?)",(rid,"alice",namespace,"event",encode(req["payload"]).decode()))
        return req
    def check(name,condition):
        result["checks"].append({"id":name,"passed":bool(condition)})
        if not condition:raise AssertionError(name)
    async def wait_connections(count,label):
        deadline=asyncio.get_running_loop().time()+2;observations=[]
        while True:
            observation=await server.monitoring("connz");observations.append(observation)
            if observation["num_connections"]>2:raise AssertionError("actual connection budget exceeded")
            if observation["num_connections"]==count:break
            if asyncio.get_running_loop().time()>=deadline:raise AssertionError("connection baseline not reached")
            await asyncio.sleep(.02)
        save(out/(label+"-connections.json"),observations)
        return observation
    baseline=1
    async def verify(name,ref,want=True,expected=None,purpose="receipt"):
        await wait_connections(baseline,name)
        process=await asyncio.create_subprocess_exec(str(PYTHON),str(source/"receipt_authority.py"),str(out),server.url,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await asyncio.wait_for(process.communicate(encode({"ref":ref,"purpose":purpose,"expected":expected})),7)
        save(out/(name+".json"),{"ref":ref,"expected":expected,"purpose":purpose,"returncode":process.returncode,"stdout":stdout.decode(),"stderr":stderr.decode()})
        check(name,process.returncode==(0 if want else 1) and json.loads(stdout).get("accepted") is want and not stderr)
    def rehash(ref):
        ref["sha256"]=sha(encode({k:v for k,v in ref.items() if k!="sha256"}));return ref
    try:
        await server.start();await proxy.start();observer=await server.connect();js=observer.jetstream()
        for namespace,limit in [("n1",8388608),("n2",1024)]:
            await js.add_stream(config=StreamConfig(name=stream(namespace),subjects=["lore."+namespace+".event.*"],storage=StorageType.FILE,discard=DiscardPolicy.NEW,max_bytes=limit,max_age=0,num_replicas=1))
        client=await nats.connect(servers=[proxy.url],allow_reconnect=False,connect_timeout=2)
        publisher=client.jetstream()
        raw=encode(envelope("alice","positive","n1","notice",{"text":"original-雪"}));req=original("positive","n1",raw)
        ack=await publisher.publish(subject("n1","positive"),raw,headers={"Nats-Msg-Id":"positive"})
        facility={"owner":"E","kind":"event","request_id":"positive","namespace":"n1","source":"alice","sequence":ack.seq,"subject":subject("n1","positive"),"sha256":sha(raw)}
        positive=wrapper_for_fixture(req,facility,"positive")
        await client.close();client=None
        positive_budget=await wait_connections(1,"positive-initial");save(out/"positive-probe-budget.json",positive_budget)
        check("positive-probe-baseline-one-connection",positive_budget["num_connections"]==1)
        await verify("positive-original-facility",positive,expected=request_fields(req))
        for key,value in [("request_digest","0"*64),("source","bob"),("namespace","n2"),("delivery_owner","X"),("outcome","unknown"),("definite",False)]:
            bad=copy.deepcopy(positive);bad[key]=value;await verify("bad-wrapper-"+key,rehash(bad),False)
        for key,value in [("sha256","0"*64),("sequence",999),("request_id","other")]:
            bad=copy.deepcopy(positive);bad["facility_ref"][key]=value;await verify("bad-facility-"+key,rehash(bad),False)
        await verify("missing-wrapper",{},False)
        await verify("facility-alone-not-R-receipt",facility,False)
        await verify("wrong-purpose",positive,False,purpose="result")
        await verify("wrong-expected-binding",positive,False,expected={"request_digest":"1"*64})
        # Freshly valid-looking wrapper but a mismatched stored complete binding must fail.
        altered=copy.deepcopy(req);altered["payload"]["event_bytes"]+=1
        with sqlite3.connect(out/"control.sqlite") as db:db.execute("update requests set payload_json=? where id=?",(encode(altered["payload"]).decode(),req["id"]))
        await verify("wrong-original-payload-bytes",wrapper_for_fixture(altered,facility,"positive"),False)
        with sqlite3.connect(out/"control.sqlite") as db:db.execute("update requests set payload_json=? where id=?",(encode(req["payload"]).decode(),req["id"]))
        await verify("positive-restored-original",positive)
        await wait_connections(1,"before-capacity")
        client=await nats.connect(servers=[proxy.url],allow_reconnect=False,connect_timeout=2);publisher=client.jetstream();baseline=2
        capacity_budget=await wait_connections(2,"capacity-initial");save(out/"capacity-budget.json",capacity_budget)
        check("capacity-two-live-connections",capacity_budget["num_connections"]==2)
        saved=[];negative=None
        for i in range(8):
            rid="capacity"+str(i);raw=encode(envelope("alice",rid,"n2","notice",{"text":"x"*256}));nreq=original(rid,"n2",raw)
            try:
                ack=await publisher.publish(subject("n2",rid),raw,headers={"Nats-Msg-Id":rid});saved.append((ack.seq,raw))
            except nats.js.errors.APIError:
                entries=[entry for entry in proxy.audit if entry.get("direction")=="puback" and entry.get("binding",{}).get("request_id")==rid]
                check("actual-negative-single-associated-puback",len(entries)==1)
                error_raw=base64.b64decode(entries[0]["body_base64"]);error=json.loads(error_raw)["error"]
                receipt=out/"negative-receipt.json";receipt.write_bytes(error_raw)
                nfacility={"owner":"E","kind":"delivery_receipt","outcome":"rejected","request_id":rid,"namespace":"n2","source":"alice","subject":subject("n2",rid),"error":error,"receipt_path":str(receipt),"sha256":sha(error_raw)}
                negative=wrapper_for_fixture(nreq,nfacility,"negative");break
        check("actual-capacity-reached-with-existing-events",bool(saved) and negative is not None)
        await verify("negative-fresh-process-original-PUB",negative,expected=request_fields(nreq))
        retained=[(await js.get_msg(stream("n2"),seq=sequence)).data==data for sequence,data in saved]
        check("capacity-retains-all-original",bool(retained) and all(retained))
        bad=copy.deepcopy(negative);bad["facility_ref"]["receipt_path"]=str(out/"missing.json");await verify("negative-missing-original-file",rehash(bad),False)
        bad=copy.deepcopy(negative);bad["facility_ref"]["error"]["description"]="invented";await verify("negative-changed-error",rehash(bad),False)
        changed=copy.deepcopy(nreq);changed["payload"]["event_sha256"]="f"*64
        with sqlite3.connect(out/"control.sqlite") as db:db.execute("update requests set payload_json=? where id=?",(encode(changed["payload"]).decode(),nreq["id"]))
        await verify("negative-wrong-original-PUB-bytes",wrapper_for_fixture(changed,nfacility,"negative"),False)
        with sqlite3.connect(out/"control.sqlite") as db:db.execute("update requests set payload_json=? where id=?",(encode(nreq["payload"]).decode(),nreq["id"]))
        log=out/"wire-observations.jsonl";log_original=log.read_bytes();log.write_bytes(b"")
        await verify("negative-no-observer-evidence",negative,False)
        log.write_bytes(log_original)
        await verify("negative-original-observation-restored",negative)
        count=len(proxy.audit)
        try:await publisher.get_msg(stream("n2"),seq=999)
        except nats.js.errors.NotFoundError:pass
        else:raise AssertionError("actual unrelated query must be missing")
        check("unrelated-query-error-not-publish-receipt",len(proxy.audit)==count)
        save(out/"actual-wrapper-examples.json",{"positive":positive,"negative":negative})
    except asyncio.CancelledError:
        result["errors"].append({"type":"CancelledError","message":"whole preparation deadline/cancellation"});raise
    except Exception as error:result["errors"].append({"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
    finally:
        if client:await client.close()
        if observer:await observer.close()
        await proxy.close();server.close()
        check("actual-server-reaped",server.proc is None or server.proc.poll() is not None)
        with sqlite3.connect(out/"control.sqlite") as db:(out/"explicit-request-fixture.sql").write_text("\n".join(db.iterdump()))
        result["status"]="PREPARATION_PASS" if not result["errors"] else "FAIL";save(out/"result.json",result)
    return result
async def main(batch):
    result=await asyncio.wait_for(run(Path(__file__).parent/"evidence"/batch),40)
    print(json.dumps({"batch":batch,"status":result["status"],"checks":len(result["checks"]),"errors":result["errors"]}))
    return 0 if result["status"]=="PREPARATION_PASS" else 1
if __name__=="__main__":raise SystemExit(asyncio.run(main(sys.argv[1])))
