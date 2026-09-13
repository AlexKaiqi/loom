"""Trusted test-side JSON ports. No candidate code or model output is imported."""
from pathlib import Path
import base64,hashlib,json,os,subprocess,time,tarfile
from oracle import InvalidEvidence,pi_jsonl,strict_json
class MissingDependency(Exception):pass
ENV={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8"}
ARTIFACT_ROOTS=[]
class JsonPort:
    def __init__(self,argv,audit):
        if not isinstance(argv,list) or not argv or not all(isinstance(x,str) for x in argv):
            raise MissingDependency("explicit peer argv missing")
        self.argv=argv;self.audit=audit;self.fixture_root=audit.parent/"peer-state"/audit.stem
        self.fixture_root.mkdir(parents=True,exist_ok=True)
    def call(self,method,params):
        request={"protocol":"LORE_COMPONENT_TEST/1","fixture_root":str(self.fixture_root),"method":method,"params":params}
        p=subprocess.run(self.argv,input=json.dumps(request),text=True,capture_output=True,env=ENV,timeout=30,close_fds=True)
        with self.audit.open("a") as f:f.write(json.dumps({"request":request,"exit":p.returncode,"stdout":p.stdout,"stderr":p.stderr})+"\n")
        if p.returncode:raise InvalidEvidence("peer failed "+method+": "+p.stderr[:200])
        reply=json.loads(p.stdout)
        if reply.get("status") in ("MISSING","UNIMPLEMENTED"):raise MissingDependency(method)
        if reply.get("error"):raise InvalidEvidence("peer error "+repr(reply["error"]))
        return reply["result"]
def read_reference(ref):
    path=Path(ref["path"])
    if not ARTIFACT_ROOTS:raise MissingDependency("trusted artifact roots not configured")
    resolved=path.resolve()
    if not any(resolved==root or root in resolved.parents for root in ARTIFACT_ROOTS):raise InvalidEvidence("artifact outside trusted fixture roots")
    if not path.is_absolute() or not path.is_file() or path.is_symlink() or path.stat().st_size>64*1024*1024:
        raise InvalidEvidence("peer did not provide actual immutable artifact")
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ref["sha256"] or len(data)!=ref["bytes"]:
        raise InvalidEvidence("peer original artifact mismatch")
    return data
def original_session_from_archive(ref):
    data=read_reference(ref)
    # The peer supplies actual protected archive bytes, not decoded Session facts.
    import io
    originals=[]
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:*") as archive:
        members=archive.getmembers()
        if len(members)>4096 or sum(m.size for m in members)>64*1024*1024:raise InvalidEvidence("unbounded original archive")
        for member in members:
            parts=Path(member.name).parts
            if member.name.startswith("/") or ".." in parts:
                raise InvalidEvidence("unsafe original archive member")
            if member.isfile() and member.name.endswith(".jsonl") and "sessions" in parts:
                stream=archive.extractfile(member);raw=stream.read()
                pi_jsonl(raw);originals.append(raw)
    if len(originals)!=1:raise InvalidEvidence("expected exactly one actual original Pi Session")
    return originals[0]
class ExecutionChannel:
    """Matches X's proposed duplex test adapter; never a static-stdin substitute."""
    def __init__(self,x,binding):
        self.x=x;self.binding=binding;self.buffer=b"";self.stderr=b"";self.eof=False;self.offsets=dict(stdin=0,stdout=0,stderr=0);self.read_serial=0
    def fields(self,method,call_id,offset):
        return {"method":method,"call_id":call_id,"byte_offset":offset,**{k:self.binding[k] for k in ("execution_id","object_generation","channel_id","request_digest")}}
    def write(self,frame):
        raw=(json.dumps(frame,ensure_ascii=False)+"\n").encode()
        fields=self.fields("channel_write","collector-write-"+str(self.offsets["stdin"])+"-"+hashlib.sha256(raw).hexdigest(),self.offsets["stdin"])
        result=self.x.call("channel_write",{**self.binding,"data_b64":base64.b64encode(raw).decode(),"call_fields":fields})
        self.offsets["stdin"]+=len(raw)
        return result
    def next_frame(self,deadline):
        while b"\n" not in self.buffer:
            if self.eof:raise InvalidEvidence("S exited before terminal response")
            if time.monotonic()>deadline:raise InvalidEvidence("S frame timeout")
            calls={stream:self.fields("channel_read","collector-read-"+stream+"-"+str(self.read_serial),self.offsets[stream]) for stream in ("stdout","stderr")}
            chunk=self.x.call("channel_read",{**self.binding,"limit_bytes":65536,"wait_ms":200,"calls":calls})
            self.read_serial+=1
            for stream in ("stdout","stderr"):self.offsets[stream]+=len(base64.b64decode(chunk[stream+"_b64"],validate=True))
            self.buffer+=base64.b64decode(chunk["stdout_b64"],validate=True)
            self.stderr+=base64.b64decode(chunk["stderr_b64"],validate=True)
            self.eof=bool(chunk["stdout_eof"])
            if len(self.buffer)>1048576 or len(self.stderr)>1048576:
                raise InvalidEvidence("bounded S control stream exceeded")
        line,self.buffer=self.buffer.split(b"\n",1)
        try:return strict_json(line)
        except (ValueError,UnicodeError) as error:raise InvalidEvidence("non-JSON control frame") from error
    def close(self):
        self.x.call("close_stdin",{**self.binding,"call_fields":self.fields("close_stdin","collector-explicit-eof",self.offsets["stdin"])})
def load_target(path):
    if not path.is_file():raise MissingDependency("S target configuration missing: "+str(path))
    target=json.loads(path.read_text())
    for key in ("sut_argv","x_command","f_command","dependency_gates","profile","fixture_authority","artifact_roots","resource_contract","resource_reservation"):
        if key not in target:raise MissingDependency("target lacks "+key)
    if not target["sut_argv"] or not target["dependency_gates"]:
        raise MissingDependency("actual S entry/dependency gates absent")
    if {g.get("component") for g in target["dependency_gates"]}!={"X","F"}:raise MissingDependency("real X/F E gates required")
    for gate in target["dependency_gates"]:
        p=Path(gate["path"])
        if not p.is_file():raise MissingDependency("required component gate absent")
        if hashlib.sha256(p.read_bytes()).hexdigest()!=gate["sha256"]:
            raise InvalidEvidence("dependency gate version changed")
        state=json.loads(p.read_text())
        if state.get("component")!=gate["component"] or state.get("stage")!="G4":raise MissingDependency("not a matching component acceptance gate")
        if state.get("status")!="PASS":
            raise MissingDependency("required actual dependency not accepted")
    resource=target["resource_contract"];resource_path=Path(resource["path"])
    if not resource_path.is_file() or hashlib.sha256(resource_path.read_bytes()).hexdigest()!=resource["sha256"]:raise MissingDependency("shared S/tool/helper resource contract missing or changed")
    prescribed={"max_objects":3,"memory_bytes":805306368,"session_memory_bytes":536870912,"tool_memory_bytes":134217728,"helper_memory_bytes":134217728}
    if any(target["resource_reservation"].get(k)!=v for k,v in prescribed.items()):raise InvalidEvidence("S fixture does not reserve the complete shared slot")
    global ARTIFACT_ROOTS
    ARTIFACT_ROOTS=[Path(p).resolve() for p in target["artifact_roots"]]
    if not ARTIFACT_ROOTS or any(str(p) in ("/","/home","/home/alex") for p in ARTIFACT_ROOTS):raise InvalidEvidence("artifact authority is overly broad")
    return target

def physical_remaining(binding):
    """Direct object inventory only; actual PID namespace is physical_witness.py."""
    objects=[]
    cid=binding["container_id"]
    if len(cid)!=64 or any(c not in "0123456789abcdef" for c in cid):raise InvalidEvidence("not a full actual container ID")
    p=subprocess.run(["docker","ps","--all","--no-trunc","--format","{{.ID}}"],env=ENV,text=True,capture_output=True,timeout=10)
    if p.returncode:raise InvalidEvidence("Engine inventory unavailable")
    if cid in p.stdout.splitlines():objects.append({"type":"remaining_container","id":cid})
    volume=binding.get("private_volume_id")
    if volume:
        p=subprocess.run(["docker","volume","ls","--format","{{.Name}}"],env=ENV,text=True,capture_output=True,timeout=10)
        if p.returncode:raise InvalidEvidence("volume inventory unavailable")
        if volume in p.stdout.splitlines():objects.append({"type":"remaining_volume","id":volume})
    return objects
