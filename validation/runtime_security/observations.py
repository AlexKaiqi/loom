"""M02-specific assertions over existing independent original-store readers."""
import base64,hashlib,json,os,sqlite3
from pathlib import Path
from urllib.parse import quote
from validation.system.runtime_observer_sources import sql,read,refraw,EngineRead,tar_files,complete_tool_feedback
from validation.runtime_security.fixtures import save,raw,sha

def files(root):
 paths=[p for p in Path(root).rglob("*") if p.is_file()]
 if len(paths)>4096:raise AssertionError("finite M02 owner file bound")
 return {str(p.relative_to(root)):sha(p) for p in paths}

def original_state(config):
 path=Path(config['runtime']['control_db'])
 connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);connection.execute('PRAGMA query_only=ON')
 try:
  extra={}
  for name in ('meta','operations','namespace_turns','restore_installs','sqlite_sequence'):
   rows=connection.execute('SELECT * FROM '+name+' ORDER BY 1 LIMIT 10001').fetchall()
   if len(rows)>10000:raise AssertionError('finite R auxiliary record bound')
   extra[name]=rows
 finally:connection.close()
 return dict(R=sql(path),R_auxiliary=extra,X=files(config['runtime']['execution_dir']))

def engine_hook(config,out,seen):
 engine=EngineRead(config["runtime"]["engine_endpoint"])
 def observe(label,binding):
  if label!="after_start_before_receipt":return
  cid,eid=binding.get("container_id"),binding.get("exec_id")
  row=dict(label=label,binding=binding)
  if cid:row["container"]=engine.get("/containers/"+quote(cid,safe="")+"/json")
  if eid:row["exec"]=engine.get("/exec/"+quote(eid,safe="")+"/json")
  seen.append(row);save(out/"actual-Engine-at-dispatch.json",seen)
 return observe

async def events(config):
 import nats
 nc=await nats.connect(config["runtime"]["nats_url"],allow_reconnect=False,connect_timeout=2)
 try:
  js=nc.jetstream();name="LORE_"+config["startup"]["namespace"]
  info=await js.stream_info(name)
  if info.state.messages>16:raise AssertionError("M02 finite event bound")
  rows=[]
  if info.state.messages==0:return rows
  for seq in range(info.state.first_seq,info.state.last_seq+1):
   msg=await js.get_msg(name,seq=seq)
   rows.append(dict(seq=msg.seq,subject=msg.subject,bytes_base64=base64.b64encode(msg.data).decode(),body=json.loads(msg.data)))
  return rows
 finally:await nc.close()

def tool_originals(config,out,seen):
 root=Path(config["runtime"]["execution_dir"]);engine=EngineRead(config["runtime"]["engine_endpoint"])
 rows=[];residual=[]
 for path in root.glob("*/record.json"):
  r=json.loads(read(path));b=r["binding"]
  for kind,url in (("container","/containers/"+b.get("container_id","")+"/json"),("volume","/volumes/"+b.get("volume_id",""))):
   if (kind=="container" and b.get("container_id")) or (kind=="volume" and b.get("volume_id")):
    actual=engine.get(url)
    if actual["status"]!=404:residual.append(dict(kind=kind,binding=b,actual=actual))
  if r["request"]["schema_version"]!=1:continue
  output={name:refraw(r["artifacts"][name],root,98304) for name in ("stdout","stderr")}
  index=len(rows)+1
  for name,data in output.items():(out/("tool-"+str(index)+"-"+name+".body")).write_bytes(data)
  proofs=[s for s in seen if s["binding"]["execution_id"]==b["execution_id"]]
  valid=any(s.get("container",{}).get("status")==200 and s["container"]["body"]["Id"]==b["container_id"]
    and s.get("exec",{}).get("status")==200 and s["exec"]["body"]["ContainerID"]==b["container_id"] for s in proofs)
  rows.append(dict(source=dict(path=str(path),sha256=sha(path)),record=r,stdout=output["stdout"].decode("utf8"),stderr=output["stderr"].decode("utf8"),actual_execution_proof=valid))
 owner=hashlib.sha256(str(root).encode()).hexdigest()
 objects=engine.get('/containers/json?all=true&filters='+quote(json.dumps({'label':['lore.x.slot_owner='+owner]})))
 save(out/'actual-owned-objects-before-cleanup.json',objects)
 if objects['body']:residual.append(dict(kind='slot-objects',actual=objects))
 save(out/"actual-X-tools.json",rows);save(out/"residual-before-cleanup.json",residual)
 return rows,residual

def pi_has_tool_bytes(session_dir,marker,tool):
 # Only actual committed Pi entry records, not substrings/pending proposals.
 found=[];binding=tool['record']['binding']
 for path in Path(session_dir).glob("confirm-*/result.json"):
  bundle=json.loads(read(path));ref=bundle.get("snapshot_ref",{})
  if not ref.get("archive_path"):continue
  data=read(Path(ref['archive_path']),8388608)
  if hashlib.sha256(data).hexdigest()!=ref.get("archive_sha256"):raise AssertionError("actual S archive SHA differs")
  for name,body in tar_files(data)[0].items():
   if not name.endswith('.jsonl'):continue
   for line in body.decode('utf8').splitlines():
    value=json.loads(line)
    for row in value if isinstance(value,list) else [value]:
     message=row.get('message',{})
     if row.get('kind')!='entry' or message.get('role')!='toolResult':continue
     original=message.get('details',{}).get('result_ref',{})
     if not (original.get('owner')=='X' and all(original.get(k)==binding[k] for k in ('execution_id','object_generation','request_digest'))):continue
     if message.get('toolCallId')!='native-m02-call' or marker not in raw(message.get('content')).decode():continue
     if not complete_tool_feedback(message,tool['stdout'].encode(),tool['stderr'].encode(),tool['record']['result']['exit_code'],original):continue
     receipt=original.get('original_receipt')
     if not receipt:continue
     receipt_raw=refraw(receipt,Path(session_dir).parent/'host',8388608)
     record=json.loads(receipt_raw)
     if record.get('binding')!=binding:continue
     found.append(dict(snapshot=str(path),archive_sha256=ref['archive_sha256'],member=name,entry_id=row['id'],message=message,actual_X_receipt=receipt))
 return found
