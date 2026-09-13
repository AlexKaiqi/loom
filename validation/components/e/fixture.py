"""Fixture orchestration only; imports actual E and actual R or raises MISSING."""
import asyncio
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from support import ROOT,PYTHON,Server,WireProxy,encode,save,sha,stream,subject,history,raw_for_json

AUTHORITY={"runtime":{"namespaces":["n1","n2","n3"],"roles":["admin","submit","runtime"]},"alice":{"namespaces":["n1","n2"],"roles":["submit"]},"bob":{"namespaces":["n1"],"roles":["submit"]},"eve":{"namespaces":[],"roles":[]}}
SURFACE={"owner":"F","kind":"surface_fixture","id":"surface-n1","sha256":sha(b"surface-original")}
SESSION={"owner":"S","kind":"session_fixture","id":"session-original","sha256":sha(b"session-original")}
def profile(root,max_bytes=8388608,page_size=128):
    return {"schema_version":1,"namespaces":["n1","n2","n3"],"stream_max_bytes":max_bytes,"message_limit_bytes":65536,
            "page_size":page_size,"authority":AUTHORITY,"runtime_principal":"runtime","input_root":str(Path(root)/"inputs"),
            "stream_prefix":"LORE_","subject_prefix":"lore","storage":"file","discard":"new","max_age":0,"replicas":1}
def sut_modules():
    try:
        em=importlib.import_module(os.environ.get("LORE_EVENT_MODULE","lore.events"))
        rm=importlib.import_module(os.environ.get("LORE_CONTROL_MODULE","lore.control"))
    except ModuleNotFoundError as exc:raise RuntimeError("MISSING real E/R component: "+str(exc)) from exc
    if not hasattr(em,"EventService") or not hasattr(rm,"ControlStore"):raise RuntimeError("MISSING EventService/ControlStore actual entry")
    gate_path=os.environ.get("LORE_R_GATE")
    if not gate_path:raise RuntimeError("MISSING verified G4 R dependency gate")
    from dependency_snapshot import verify_loaded
    verify_loaded(gate_path,rm.__file__,os.environ.get("LORE_R_SOURCE_EQUIVALENCE"))
    return em,rm
def reference_checker(root,url,proxy=None):
    def check(ref,purpose,expected=None):
        if not isinstance(ref,dict):return False
        if ref.get("kind")=="harness" and purpose=="harness":
            try:return ref["path"]==str(Path(root)/"harness-fixture.txt") and sha(Path(ref["path"]).read_bytes())==ref["sha256"]
            except (KeyError,OSError):return False
        if ref.get("kind")=="input" and ref.get("owner")=="E" and purpose=="input":
            try:
                directory=Path(ref["path"])
                if not directory.is_absolute() or directory.is_symlink() or not directory.resolve().is_relative_to(Path(root).resolve()):return False
                st=directory.stat()
                if ref.get("root",{}).get("dev")!=st.st_dev or ref.get("root",{}).get("ino")!=st.st_ino:return False
                manifest=(directory/"manifest.json").read_bytes()
                if sha(manifest)!=ref["manifest_sha256"]:return False
                meta=json.loads(manifest)
                if meta.get("complete") is not True:return False
                if set(meta.get("files",{}))!={"events.jsonl","invocation.json","execution-targets.json"}:return False
                if set(p.name for p in directory.iterdir())!={"events.jsonl","invocation.json","execution-targets.json","manifest.json"}:return False
                if any((directory/name).is_symlink() for name in meta["files"]):return False
                invocation=json.loads((directory/"invocation.json").read_bytes())
                targets=json.loads((directory/"execution-targets.json").read_bytes())
                binding={"namespace":invocation["namespace"],"source":invocation["source"],"start_sequence":invocation["range"]["start_sequence"],"filters":invocation["filters"],"page_size":invocation["page_size"],"surface_ref":invocation["surface_ref"],"previous_session_ref":invocation["previous_session_ref"],"execution_targets":targets["targets"]}
                if expected is not None and expected!={"invocation_id":invocation["invocation_id"],"binding":binding}:return False
                if ref["id"]!=invocation["invocation_id"] or ref["id"]!=meta["invocation_id"]:return False
                return all(sha((directory/name).read_bytes())==item["sha256"] and (directory/name).stat().st_size==item["bytes"] for name,item in meta["files"].items())
            except (KeyError,OSError,ValueError):return False
        from receipt_authority import check_receipt
        return check_receipt(root,url,ref,purpose,expected)
    return check

class Fixture:
    def __init__(self,root,max_bytes=8388608,page_size=128):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.em,self.rm=sut_modules()
        self.db=self.root/"control.sqlite";self.server=Server(self.root/"nats")
        self.proxy=WireProxy(self.server,self.root);self.observer=None;self.services=[];self.stores=[]
        self.profile=profile(self.root,max_bytes,page_size);self.closed=False
        self.surface=self.root/"surface";self.surface.mkdir();(self.surface/"original.txt").write_bytes(b"surface-original")
        self.session=self.root/"original-session.jsonl";self.session.write_bytes(b"session-original")
        harness=self.root/"harness-fixture.txt";harness.write_bytes(b"non-executed E fixture harness reference")
        self.harness={"owner":"F","kind":"harness","id":"h1","path":str(harness),"sha256":sha(harness.read_bytes())}
        self.registrations={}
        self.input_context={"surface_ref":{**SURFACE,"path":str(self.surface)},"previous_session_ref":{**SESSION,"path":str(self.session)},
            "execution_targets":[{"id":"surface-n1","namespace":"n1","path":str(self.surface),"access":["read","write"]}]}
    async def start(self):
        await self.server.start();await self.proxy.start()
        self.observer=await self.server.connect();self.js=self.observer.jetstream()
        self.service=await self.new_service()
        return self
    async def new_service(self,checkpoint=None,profile_override=None):
        store=self.rm.ControlStore(self.db,authority=AUTHORITY,reference_checker=reference_checker(self.root,self.server.url,self.proxy))
        self.stores.append(store)
        service=self.em.EventService(self.proxy.url,store,profile_override or self.profile,checkpoint=checkpoint)
        self.services.append(service);await asyncio.wait_for(service.start(),5)
        return service
    def context_for(self,namespace):
        import copy
        context=copy.deepcopy(self.input_context)
        if namespace!="n1":
            path=self.root/("surface-"+namespace)
            context["surface_ref"].update(id="surface-"+namespace,path=str(path))
            context["execution_targets"][0].update(id="surface-"+namespace,namespace=namespace,path=str(path))
        return context
    def binding(self,principal="alice",namespace="n1",start=1,filters=None):
        return {"namespace":namespace,"source":principal,"start_sequence":start,"filters":filters or {},"page_size":self.profile["page_size"],**self.context_for(namespace)}
    def reserve(self,invocation_id,principal="alice",namespace="n1",start=1,filters=None):
        if namespace not in self.registrations:
            context=self.context_for(namespace);path=Path(context["surface_ref"]["path"]);path.mkdir(exist_ok=True)
            self.registrations[namespace]=self.stores[0].register("runtime","register-"+namespace,"surface-"+namespace,namespace,"surface",str(path),self.harness,{"alice":["read","write"],"bob":["read","write"],"runtime":["read","write"]})
        registration=self.registrations[namespace]
        request={"id":invocation_id,"namespace":namespace,"kind":"invocation","payload":{"resource_id":"surface-"+namespace,"resource_revision":registration["revision"],"harness_ref":self.harness,"input_ref":None,"input_binding":self.binding(principal,namespace,start,filters)}}
        self.stores[0].accept(principal,request)
    def sql(self,query,args=()):
        with sqlite3.connect("file:"+str(self.db)+"?mode=ro",uri=True) as db:return db.execute(query,args).fetchall()
    async def prepare(self,invocation_id="i1",namespace="n1",start=1,filters=None,principal="alice",service=None):
        return await asyncio.wait_for((service or self.service).prepare_input(principal,invocation_id,namespace,start,filters or {},str(self.root/"inputs"),input_context=self.context_for(namespace)),5)
    async def rows(self,namespace="n1"):
        rows=await history(self.js,namespace)
        index=len(list(self.root.glob("raw-"+namespace+"-*")))
        metadata=[]
        for row in rows:
            if "data" not in row:continue
            msg=await self.js.get_msg(stream(namespace),seq=row["sequence"])
            metadata.append({"sequence":msg.seq,"headers":dict(msg.headers or {})})
        save(self.root/f"raw-{namespace}-{index}.json",raw_for_json(rows))
        save(self.root/f"headers-{namespace}-{index}.json",metadata)
        return rows
    def config(self,action,**args):
        return {"server_url":self.proxy.url,"observer_url":self.server.url,"db":str(self.db),"root":str(self.root),"profile":self.profile,"action":action,"args":args,"input_context":self.input_context}
    async def close(self):
        if self.closed:return
        self.closed=True;errors=[]
        for service in reversed(self.services):
            try:await asyncio.wait_for(service.close(),3)
            except Exception as exc:errors.append(repr(exc))
        if self.observer:
            try:await self.observer.close()
            except Exception as exc:errors.append(repr(exc))
        for store in reversed(self.stores):
            try:store.close()
            except Exception as exc:errors.append(repr(exc))
        if self.db.exists():
            try:
                with sqlite3.connect("file:"+str(self.db)+"?mode=ro",uri=True) as db:(self.root/"raw.sql").write_text("\n".join(db.iterdump()))
            except sqlite3.Error as exc:errors.append(repr(exc))
        await self.proxy.close();self.server.close()
        save(self.root/"cleanup.json",{"errors":errors,"nats_reaped":self.server.proc is None or self.server.proc.poll() is not None})
        if errors:raise AssertionError("fixture cleanup failures: "+repr(errors))
