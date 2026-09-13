"""Preregistered facility-only probe: no EventService or fake ControlStore."""
import asyncio
import json
from pathlib import Path
import sys
import traceback
import importlib.metadata
import nats
from nats.js.api import StreamConfig,StorageType,DiscardPolicy
from support import Server,WireProxy,stream,subject,envelope,encode,save,sha,raw_for_json,history,BINARY,PYTHON
from oracle import raw_history,input_files
async def main(batch):
    out=Path(__file__).parent/"evidence"/batch;out.mkdir(parents=True,exist_ok=False)
    server=Server(out/"nats");proxy=WireProxy(server,out);observer=None;client=None
    result={"scope":"G3 native fixture/oracle readiness only; E and R unimplemented","protocol_sha256":sha((Path(__file__).parent/"preparation-protocol.json").read_bytes()),"script_sha256":sha(Path(__file__).read_bytes()),"support_sha256":sha((Path(__file__).parent/"support.py").read_bytes()),"amendment_sha256":sha((Path(__file__).parent/"preparation-amendment-002.json").read_bytes()),"binary_sha256":sha(BINARY.read_bytes()),"checks":[],"errors":[]}
    def check(name,condition):
        result["checks"].append({"id":name,"passed":bool(condition)})
        if not condition:raise AssertionError(name)
    try:
        check("fixed-client",importlib.metadata.version("nats-py")=="2.15.0")
        await server.start();await proxy.start();observer=await server.connect();js=observer.jetstream()
        for namespace,max_bytes in [("n1",8388608),("n2",1024)]:
            await js.add_stream(config=StreamConfig(name=stream(namespace),subjects=["lore."+namespace+".event.*"],storage=StorageType.FILE,discard=DiscardPolicy.NEW,max_bytes=max_bytes,max_age=0,num_replicas=1))
        client=await nats.connect(servers=[proxy.url],allow_reconnect=False,connect_timeout=2)
        data=encode(envelope("alice","e1","n1","notice",{"text":"original-雪"}))
        proxy.drop_next_ack=True;timed_out=False
        try:await client.jetstream().publish(subject("n1","e1"),data,headers={"Nats-Msg-Id":"e1"},timeout=.3)
        except nats.errors.TimeoutError:timed_out=True
        check("actual-puback-dropped-and-client-timeout",timed_out and proxy.dropped.is_set())
        rows=await history(js,"n1")
        expected=[{"sequence":1,"subject":subject("n1","e1"),"data":data}]
        raw_history(rows,expected);check("independent-original-raw-bytes",True)
        save(out/"before-raw.json",raw_for_json(rows))
        check("one-actual-publish",len([x for x in proxy.audit if x.get("direction")=="publish"])==1)
        await client.close();client=None;await observer.close();observer=None
        server.kill();await server.start();observer=await server.connect();js=observer.jetstream()
        after=await history(js,"n1");raw_history(after,expected);save(out/"after-raw.json",raw_for_json(after))
        check("SIGKILL-restart-original-store",True)
        client=await nats.connect(servers=[proxy.url],allow_reconnect=False,connect_timeout=2)
        publisher=client.jetstream()
        saved=[];negative=None
        for i in range(8):
            try:
                raw=encode(envelope("alice","cap"+str(i),"n2","notice",{"text":"x"*256}))
                ack=await publisher.publish(subject("n2","cap"+str(i)),raw,headers={"Nats-Msg-Id":"cap"+str(i)})
                saved.append({"sequence":ack.seq,"data":raw})
            except nats.js.errors.APIError as error:
                negative={"code":error.code,"err_code":error.err_code,"description":error.description};break
        check("capacity-explicit-error",bool(saved) and negative is not None)
        save(out/"capacity.json",{"saved_sequences":[item["sequence"] for item in saved],"negative":negative,"stream_info":(await js.stream_info(stream("n2"))).as_dict()})
        for item in saved:check("capacity-preserves-"+str(item["sequence"]),(await js.get_msg(stream("n2"),seq=item["sequence"])).data==item["data"])
        import base64
        negatives=[x for x in proxy.audit if x.get("direction")=="puback" and "error" in json.loads(base64.b64decode(x["body_base64"]))]
        check("negative-bound-to-original-publish",len(negatives)==1 and negatives[0]["binding"]["request_id"]=="cap"+str(i) and negatives[0]["binding"]["source"]=="alice")
        count=len([x for x in proxy.audit if x.get("direction")=="puback"])
        try:await publisher.get_msg(stream("n2"),seq=999)
        except nats.js.errors.NotFoundError:pass
        else:raise AssertionError("expected real unrelated missing message")
        check("unrelated-API-error-not-publish-receipt",len([x for x in proxy.audit if x.get("direction")=="puback"])==count)
        for bad in ([],[dict(expected[0],data=b"wrong")]):
            try:raw_history(bad,expected)
            except AssertionError:pass
            else:raise AssertionError("bad raw history was accepted")
        check("bad-history-controls-rejected",True)
        directory=out/"input-control";directory.mkdir();file=directory/"events.jsonl";file.write_bytes(b"A\n")
        input_files(directory,{"events.jsonl":b"A\n"});file.write_bytes(b"B\n")
        try:input_files(directory,{"events.jsonl":b"A\n"})
        except AssertionError:pass
        else:raise AssertionError("same-size corruption accepted")
        check("physical-equal-length-corruption-rejected",True)
    except Exception as error:result["errors"].append({"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
    finally:
        if client:await client.close()
        if observer:await observer.close()
        await proxy.close();server.close()
        check("actual-server-reaped",server.proc is None or server.proc.poll() is not None)
        result["status"]="PREPARATION_PASS" if not result["errors"] else "FAIL";save(out/"result.json",result)
        print(json.dumps({"batch":batch,"status":result["status"],"checks":result["checks"],"errors":result["errors"]}))
    return 0 if not result["errors"] else 1
if __name__=="__main__":raise SystemExit(asyncio.run(asyncio.wait_for(main(sys.argv[1]),40)))
