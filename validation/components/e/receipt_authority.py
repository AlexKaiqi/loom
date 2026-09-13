"""Independent receipt authority; observes original SQL/facility, never implements E/R."""
import base64
import json
from pathlib import Path
import sqlite3
import subprocess
from support import ROOT,PYTHON,encode,sha,subject

def original_request(root,request_id):
    database=Path(root)/"control.sqlite"
    with sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True,timeout=1) as db:
        rows=db.execute("select id,principal,namespace,kind,payload_json from requests where id=?",(request_id,)).fetchall()
    if len(rows)!=1:raise ValueError("missing unique original request")
    rid,principal,namespace,kind,payload=rows[0]
    return {"principal":principal,"id":rid,"namespace":namespace,"kind":kind,"payload":json.loads(payload)}

def request_fields(request):
    return {"request_id":request["id"],"namespace":request["namespace"],"source":request["principal"],"delivery_owner":"E","request_digest":sha(encode(request))}

def wrapper_for_fixture(request,facility,outcome):
    """Explicit test data builder only. Formal component must return its own wrapper."""
    ref={"owner":"E","kind":"delivery_receipt","id":request["id"]+".receipt",**request_fields(request),"outcome":outcome,"definite":True,"facility_ref":facility}
    return {**ref,"sha256":sha(encode(ref))}

def contained_file(root,value):
    file=Path(value)
    if not file.is_absolute() or file.is_symlink() or not file.resolve().is_relative_to(Path(root).resolve()) or not file.is_file():raise ValueError("invalid facility file")
    return file

def negative_witness(root,facility,request):
    raw=contained_file(root,facility["receipt_path"]).read_bytes()
    value=json.loads(raw)
    error=value.get("error")
    if not isinstance(error,dict) or set(error)!={"code","err_code","description"}:return False
    if not isinstance(error["description"],str) or not error["description"] or type(error["code"]) is not int or type(error["err_code"]) is not int:return False
    if facility.get("error")!=error or sha(raw)!=facility["sha256"]:return False
    payload=request["payload"]
    bound={"request_id":request["id"],"namespace":request["namespace"],"source":request["principal"],"subject":payload["subject"],"sha256":payload["event_sha256"],"bytes":payload["event_bytes"]}
    log=contained_file(root,str(Path(root)/"wire-observations.jsonl"))
    for line in log.read_bytes().splitlines():
        item=json.loads(line)
        if item.get("direction")=="puback" and item.get("binding")==bound and base64.b64decode(item.get("body_base64",""),validate=True)==raw:return True
    return False

def check_receipt(root,url,ref,purpose,expected=None):
    """Returns false on invalid evidence, including observer failure/missing rows."""
    try:
        if purpose!="receipt" or not isinstance(ref,dict):return False
        required={"owner","kind","id","request_id","namespace","source","delivery_owner","request_digest","outcome","definite","facility_ref","sha256"}
        if set(ref)!=required or ref["owner"]!="E" or ref["kind"]!="delivery_receipt" or ref["id"]!=ref["request_id"]+".receipt":return False
        if ref["definite"] is not True or ref["outcome"] not in {"positive","negative"}:return False
        if ref["sha256"]!=sha(encode({k:v for k,v in ref.items() if k!="sha256"})):return False
        if not all(ref.get(k)==v for k,v in (expected or {}).items()):return False
        request=original_request(root,ref["request_id"])
        if request["kind"]!="event" or not all(ref[k]==v for k,v in request_fields(request).items()):return False
        payload=request["payload"]
        if payload["subject"]!=subject(request["namespace"],request["id"]) or type(payload["event_bytes"]) is not int or payload["event_bytes"]<1:return False
        facility=ref["facility_ref"]
        if not isinstance(facility,dict) or facility.get("owner")!="E":return False
        binding={"request_id":request["id"],"namespace":request["namespace"],"source":request["principal"],"subject":payload["subject"]}
        if not all(facility.get(k)==v for k,v in binding.items()):return False
        if ref["outcome"]=="negative":
            return facility.get("kind")=="delivery_receipt" and facility.get("outcome")=="rejected" and negative_witness(root,facility,request)
        if facility.get("kind")!="event" or facility.get("sha256")!=payload["event_sha256"] or type(facility.get("sequence")) is not int or facility["sequence"]<1:return False
        result=subprocess.run([str(PYTHON),str(ROOT/"validation/components/e/reference_probe.py"),url],input=json.dumps({"ref":facility,"request":request}),capture_output=True,text=True,timeout=5)
        with (Path(root)/"reference-checks.jsonl").open("a") as log:log.write(json.dumps({"ref":ref,"request":request,"returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr})+"\n")
        return result.returncode==0
    except (KeyError,ValueError,TypeError,OSError,sqlite3.Error,subprocess.SubprocessError):return False

if __name__=="__main__":
    import sys
    item=json.load(sys.stdin)
    accepted=check_receipt(sys.argv[1],sys.argv[2],item["ref"],item.get("purpose","receipt"),item.get("expected"))
    print(json.dumps({"accepted":accepted,"observer":"fresh-authority-process"}))
    raise SystemExit(0 if accepted else 1)
