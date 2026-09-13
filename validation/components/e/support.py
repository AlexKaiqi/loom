"""Real local NATS fixture and raw, independent observers. Never implements EventService."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import nats

ROOT=Path(__file__).resolve().parents[3]
BINARY=ROOT/"research/.cache/nats-server/nats-server"
BINARY_SHA="c2ce368d3080994e3ec94e688d8c749c17000c75aa5edc7bb08dda33345218e9"
PYTHON=ROOT/"research/.venvs/runtime-research/bin/python"
def encode(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
def save(path,value):
    Path(path).write_bytes(json.dumps(value,ensure_ascii=False,indent=2,default=str).encode()+b"\n")
def sha(raw):return hashlib.sha256(raw).hexdigest()
def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));return sock.getsockname()[1]
def stream(namespace):return "LORE_"+namespace
def subject(namespace,request_id):return "lore."+namespace+".event."+sha(request_id.encode())
def envelope(principal,request_id,namespace,name,payload,origin="application"):
    return {"schema_version":1,"origin":origin,"source":principal,"namespace":namespace,"request_id":request_id,"name":name,"payload":payload}

class Server:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.port=free_port();self.monitor_port=free_port()
        self.url=f"nats://127.0.0.1:{self.port}";self.proc=None;self.logs=[];self.lifecycle=[]
        self.config=self.root/"server.conf"
        self.config.write_text(f'listen: "127.0.0.1:{self.port}"\nhttp: "127.0.0.1:{self.monitor_port}"\njetstream {{ store_dir: "{self.root / "store"}", sync_interval: "always" }}\n')
    async def start(self):
        if sha(BINARY.read_bytes())!=BINARY_SHA:raise RuntimeError("fixed NATS binary mismatch")
        log=(self.root/f"server-{len(self.logs)+1}.log").open("wb");self.logs.append(log)
        self.proc=subprocess.Popen([str(BINARY),"-c",str(self.config)],stdout=log,stderr=subprocess.STDOUT,close_fds=True)
        self.lifecycle.append({"action":"start","pid":self.proc.pid})
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if self.proc.poll() is not None:raise RuntimeError("NATS startup exited")
            try:
                reader,writer=await asyncio.open_connection("127.0.0.1",self.port)
                await asyncio.wait_for(reader.readline(),1);writer.close();await writer.wait_closed();return
            except OSError:await asyncio.sleep(.03)
        raise TimeoutError("NATS startup 10s")
    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill();self.proc.wait(timeout=3)
            self.lifecycle.append({"action":"SIGKILL","pid":self.proc.pid,"returncode":self.proc.returncode})
            if self.proc.returncode!=-9:raise AssertionError("actual SIGKILL required")
    async def connect(self):
        async def error_cb(error):self.lifecycle.append({"client_error":type(error).__name__})
        return await nats.connect(servers=[self.url],allow_reconnect=False,connect_timeout=2,error_cb=error_cb)
    async def monitoring(self,endpoint="connz"):
        def read():
            with urllib.request.urlopen(f"http://127.0.0.1:{self.monitor_port}/{endpoint}",timeout=2) as response:return json.load(response)
        return await asyncio.to_thread(read)
    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate();self.proc.wait(timeout=3)
            self.lifecycle.append({"action":"terminate","pid":self.proc.pid,"returncode":self.proc.returncode})
        for log in self.logs:log.close()
        save(self.root/"lifecycle.json",self.lifecycle)

class WireProxy:
    """Bounded NATS protocol forwarder; drops only one actual server PubAck MSG.
    PUB/HPUB audit is taken before forwarding, not from EventService reporting.
    Not an event adapter and does not create a synthetic server response.
    """
    def __init__(self,server,root):
        self.server=server;self.root=Path(root);self.port=free_port();self.url=f"nats://127.0.0.1:{self.port}"
        self.listener=None;self.tasks=set();self.writers=set();self.audit=[];self.drop_next_ack=False;self.dropped=asyncio.Event()
        self.max_frame=1024*1024;self.max_frames=20000;self.pending_acks={}
    def record(self,item):
        self.audit.append(item)
        with (self.root/"wire-observations.jsonl").open("ab") as log:
            log.write(encode(item)+b"\n");log.flush();os.fsync(log.fileno())
    async def start(self):
        self.listener=await asyncio.start_server(self.handle,"127.0.0.1",self.port,limit=self.max_frame+1024)
    async def relay(self,reader,writer,direction):
        while True:
            line=await reader.readline()
            if not line:return
            parts=line.rstrip(b"\r\n").split()
            if not parts:raise RuntimeError("empty protocol line")
            command=parts[0]
            body=b""
            if command in (b"PUB",b"HPUB",b"MSG",b"HMSG"):
                size=int(parts[-1])
                if not 0<=size<=self.max_frame:raise RuntimeError("proxy frame limit")
                body=await reader.readexactly(size+2)
                if body[-2:]!=b"\r\n":raise RuntimeError("invalid NATS payload framing")
            if len(self.audit)>=self.max_frames:raise RuntimeError("proxy frame budget")
            if direction=="client" and command in (b"PUB",b"HPUB") and parts[1].startswith(b"lore."):
                raw=body[:-2]
                if command==b"HPUB":raw=raw[int(parts[-2]):]
                binding={"subject":parts[1].decode(),"sha256":sha(raw),"bytes":len(raw)}
                try:
                    value=json.loads(raw);binding.update(request_id=value["request_id"],namespace=value["namespace"],source=value["source"])
                except (ValueError,KeyError,UnicodeDecodeError):pass
                reply=parts[2].decode() if (command==b"PUB" and len(parts)==4) or (command==b"HPUB" and len(parts)==5) else None
                if reply:self.pending_acks[reply]=binding
                self.record({"direction":"publish","line":line.decode().rstrip(),"body_base64":base64.b64encode(body[:-2]).decode(),"binding":binding,"reply_subject":reply})
            if direction=="server" and command==b"MSG" and body:
                try:value=json.loads(body[:-2])
                except (ValueError,UnicodeDecodeError):value=None
                bound=self.pending_acks.get(parts[1].decode())
                if bound is not None and isinstance(value,dict) and (("stream" in value and type(value.get("seq")) is int) or ("error" in value and isinstance(value["error"],dict))):
                    drop=self.drop_next_ack
                    self.record({"direction":"puback","dropped":drop,"line":line.decode().rstrip(),"body_base64":base64.b64encode(body[:-2]).decode(),"binding":bound})
                    if drop:
                        self.drop_next_ack=False;self.dropped.set();continue
            writer.write(line+body);await writer.drain()
    async def handle(self,reader,writer):
        task=asyncio.current_task();self.tasks.add(task);self.writers.add(writer);upstream=None
        try:
            remote,upstream=await asyncio.open_connection("127.0.0.1",self.server.port,limit=self.max_frame+1024)
            self.writers.add(upstream)
            forwards=[asyncio.create_task(self.relay(reader,upstream,"client")),asyncio.create_task(self.relay(remote,writer,"server"))]
            done,pending=await asyncio.wait(forwards,return_when=asyncio.FIRST_COMPLETED)
            for child in pending:child.cancel()
            await asyncio.gather(*forwards,return_exceptions=True)
            for child in done:
                error=child.exception()
                if error:self.record({"direction":"proxy_error","type":type(error).__name__,"message":str(error)})
        except (OSError,asyncio.CancelledError):pass
        finally:
            for item in (writer,upstream):
                if item:
                    item.close();self.writers.discard(item)
            self.tasks.discard(task)
    async def close(self):
        if self.listener:self.listener.close();await self.listener.wait_closed()
        for writer in list(self.writers):writer.close()
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
        save(self.root/"wire-audit.json",self.audit)

async def history(js,namespace):
    info=await js.stream_info(stream(namespace));result=[]
    for sequence in range(1,info.state.last_seq+1):
        try:message=await js.get_msg(stream(namespace),seq=sequence)
        except nats.js.errors.NotFoundError:
            result.append({"sequence":sequence,"missing":True});continue
        result.append({"sequence":message.seq,"subject":message.subject,"data":message.data})
    return result
def raw_for_json(rows):
    return [{**{k:v for k,v in row.items() if k!="data"},"data_base64":base64.b64encode(row["data"]).decode()} if "data" in row else row for row in rows]
