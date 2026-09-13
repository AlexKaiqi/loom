"""Separate-process, separate NATS connection checks real positive receipt."""
import asyncio
import json
import sys
import nats
from support import encode,sha,stream,subject
async def main():
    item=json.load(sys.stdin);ref=item["ref"];request=item["request"]
    nc=await nats.connect(servers=[sys.argv[1]],allow_reconnect=False,connect_timeout=2)
    try:
        msg=await nc.jetstream().get_msg(stream(ref["namespace"]),seq=ref["sequence"])
        obj=json.loads(msg.data)
        assert msg.subject==subject(ref["namespace"],ref["request_id"])==ref["subject"]==request["payload"]["subject"]
        assert obj["request_id"]==ref["request_id"]==request["id"] and obj["source"]==ref["source"]==request["principal"] and obj["namespace"]==ref["namespace"]==request["namespace"]
        assert ref["sha256"]==sha(msg.data)==request["payload"]["event_sha256"] and len(msg.data)==request["payload"]["event_bytes"] and msg.data==encode(obj)
        assert (msg.headers or {}).get("Nats-Msg-Id")==ref["request_id"]
        print(json.dumps({"sequence":msg.seq,"sha256":sha(msg.data),"bytes":len(msg.data),"subject":msg.subject,"header":dict(msg.headers or {})}))
    finally:await nc.close()
if __name__=="__main__":asyncio.run(main())
