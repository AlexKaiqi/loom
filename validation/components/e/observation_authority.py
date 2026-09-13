"""Independent original R registration byte authority; no E state or replacement R."""
import json
import sqlite3
from pathlib import Path
from support import encode,sha,save

FIELDS={"owner","kind","id","namespace","resource_id","revision","sha256"}
def original(root,operation_id):
    with sqlite3.connect((Path(root)/"control.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
        rows=db.execute("SELECT binding_json,response_json FROM operations WHERE id=?",(operation_id,)).fetchall()
    if len(rows)!=1:raise ValueError("original registration operation missing")
    binding_raw,response_raw=(value.encode("utf-8") for value in rows[0])
    return binding_raw,response_raw,json.loads(binding_raw),json.loads(response_raw)

def registration_ref(root,operation_id):
    binding_raw,response_raw,binding,response=original(root,operation_id)
    out=Path(root)/"observation-originals";out.mkdir(exist_ok=True)
    (out/(operation_id+".binding.json")).write_bytes(binding_raw)
    (out/(operation_id+".response.json")).write_bytes(response_raw)
    return {"owner":"R","kind":"registration","id":operation_id,"namespace":response["namespace"],"resource_id":response["id"],"revision":response["revision"],"sha256":sha(response_raw)}

def check_observation(root,ref,purpose,expected):
    accepted=False;reason=None
    try:
        if purpose!="observation" or type(ref) is not dict or set(ref)!=FIELDS:raise ValueError("invalid observation reference shape")
        if ref["owner"]!="R" or ref["kind"]!="registration":raise ValueError("wrong original owner/kind")
        if type(expected) is not dict or set(expected)!={"namespace","source","event_name"} or expected["event_name"]!="surface.registered":raise ValueError("incorrect expected observation binding")
        binding_raw,response_raw,binding,response=original(root,ref["id"])
        if binding.get("op")!="register" or binding.get("kind")!="surface" or response.get("kind")!="surface":raise ValueError("original is not a completed surface registration")
        if binding.get("principal")!=expected["source"]:raise ValueError("wrong original authenticated registering principal")
        if not (binding["namespace"]==response["namespace"]==ref["namespace"]==expected["namespace"]):raise ValueError("wrong namespace")
        if not (binding["resource_id"]==response["id"]==ref["resource_id"]):raise ValueError("wrong resource")
        if type(ref["revision"]) is not int or ref["revision"]!=response["revision"] or ref["revision"]<1:raise ValueError("wrong original revision")
        if sha(response_raw)!=ref["sha256"]:raise ValueError("wrong original bytes digest")
        if encode(binding)!=binding_raw or encode(response)!=response_raw:raise ValueError("noncanonical original R record")
        if type(response.get("dev")) is not int or type(response.get("ino")) is not int or not Path(response["path"]).is_absolute():raise ValueError("incomplete original physical registration")
        if binding["harness_ref"]!=response["harness_ref"] or binding["grants"]!=response["grants"]:raise ValueError("wrong original registration associations")
        accepted=True
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as exc:reason=str(exc)
    with (Path(root)/"observation-authority.jsonl").open("a") as log:log.write(json.dumps({"ref":ref,"purpose":purpose,"expected":expected,"accepted":accepted,"reason":reason},ensure_ascii=False)+"\n")
    return accepted

def runtime_bytes(raw,expected):
    if raw!=expected:raise AssertionError("actual runtime event differs from precomputed original-source bytes")
    value=json.loads(raw)
    if value["origin"]!="runtime" or value["source"]!="runtime" or value["name"]!="surface.registered" or value["payload"]["observation_ref"]["owner"]!="R":raise AssertionError("runtime provenance missing")

def controls():
    value={"schema_version":1,"origin":"runtime","source":"runtime","namespace":"n1","request_id":"control","name":"surface.registered","payload":{"observation_ref":{"owner":"R","kind":"registration","id":"fixture"}}}
    expected=encode(value);runtime_bytes(expected,expected);results=[{"id":"correct-explicit-fixture","passed":True}]
    for name,bad in [("missing",b""),("wrong-origin",encode({**value,"origin":"application"})),("wrong-owner",encode({**value,"payload":{"observation_ref":{"owner":"F"}}})),("wrong-source",encode({**value,"source":"alice"}))]:
        try:runtime_bytes(bad,expected)
        except (AssertionError,ValueError,KeyError):results.append({"id":name,"passed":True})
        else:results.append({"id":name,"passed":False})
    return results
