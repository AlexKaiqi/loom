"""One preregistered shared-slot schema1 release probe; no Node/Pi/F execution."""
from pathlib import Path
import argparse,copy,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"validation"),str(ROOT/"validation/components/x"),str(ROOT/"validation/components/v"),str(ROOT/"validation/components/r")]
from x_tool_inode_probe import exact_cleanup
from source_snapshot import capture,unchanged
from source_closure import AUDIT,python_children
from process_group import cleanup as process_cleanup

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def save(p,v):Path(p).write_bytes(canonical(v)+b"\n")
def file_bytes(ref):
 raw=Path(ref["path"]).read_bytes();assert hashlib.sha256(raw).hexdigest()==ref["sha256"] and len(raw)==ref["size"];return raw

def allocated(path,pid):
 root=Path(path);seen={}
 for p in [root,*root.rglob("*")]:
  s=p.lstat();seen[s.st_dev,s.st_ino]={"path":str(p),"blocks":s.st_blocks*512}
 for p in (Path("/proc")/str(pid)/"fd").glob("*"):
  try:
   name=os.readlink(p)
   if name.startswith(str(root)+"/") and name.endswith(" (deleted)"):
    s=p.stat();seen[s.st_dev,s.st_ino]={"path":name,"fd":str(p),"blocks":s.st_blocks*512}
  except FileNotFoundError:pass
 s=root.stat();return dict(path=str(root),root=dict(dev=s.st_dev,ino=s.st_ino),allocated_bytes=sum(v["blocks"]for v in seen.values()),inodes=len(seen),objects=list(seen.values()))

def registry(root,kind,ref,scope):
 value=dict(kind=kind,ref=ref,registered_scope=scope);name=hashlib.sha256(canonical(dict(kind=kind,ref=ref))).hexdigest()+".json"
 save(root/name,value)

def worker(out):
 from fixtures import create
 from run import Adapter
 from collector import Collector
 from lore_execution import ExecutionStore
 out.mkdir();checks=[];physical_bindings=[];adapter=None;observer=None;fx=None
 def check(name,yes,**facts):checks.append(dict(check=name,passed=bool(yes),**facts));save(out/"checks.json",checks)
 try:
  fx=create(out/"fixture",{"initial":{"script":"binary_effect"}},{"domain":"task","cpu":.25})
  authority_root=fx["root"]/"trusted-authority";authority_root.mkdir()
  profile_path=ROOT/"design/g3/x-node-profile/profile.json";profile=json.loads(profile_path.read_bytes())
  scope={"namespace":fx["authority"]["namespace"]};plan=profile["slot_reservation"];plan_sha=hashlib.sha256(canonical(plan)).hexdigest()
  slot_ref=dict(owner="trusted-X-configuration",slot_id="one-original-shared-slot",revision=1,plan_sha256=plan_sha,role="tool")
  slot=dict(slot_id=slot_ref["slot_id"],revision=1,namespace=scope["namespace"],plan_sha256=plan_sha,plan=plan,allowed_principals=["trusted-S"],state_root=str(fx["state"]))
  config=dict(schema="lore-x-trusted-node-test-config/v1",transport_principal="trusted-S",state_root=str(fx["state"]),profiles=[dict(id=profile["id"],path=str(profile_path),sha256=sha(profile_path))],slots=[slot],grants=[],references=dict(snapshots=[],F_views=[],owner_receipts=[]),read_only_roots=[],allowed_harness_entries=[],dynamic_reference_authorities=[dict(root=str(authority_root),identity="original-grant-fixture",namespace=scope["namespace"],allowed_kinds=["grant"],rule="immutable-full-ref-registration/v1")])
  config_path=fx["root"]/"trusted-config.json";save(config_path,config)
  def authorize(request):
   auth=copy.deepcopy(fx["authority"]);auth["slot_ref"]=slot_ref
   record=dict(principal="trusted-S",operations=["execute","query","checkpoint","stop"],original_request=request,request_digest=hashlib.sha256(canonical(request)).hexdigest(),scope=scope,slot_ref=slot_ref,role="tool")
   p=authority_root/("grant-"+record["request_digest"]+".json");save(p,record)
   ref=dict(owner="trusted-X-configuration",id=record["request_digest"],record_path=str(p),sha256=sha(p));registry(authority_root,"grant",ref,scope);auth["grant_ref"]=ref;return auth
  requests=[copy.deepcopy(fx["request"])for _ in range(2)];requests[1]["execution_id"]+="-next"
  fx["execution_ids"].add(requests[1]["execution_id"]);authorities=[authorize(q)for q in requests]
  save(out/"requests.json",requests);save(out/"authorities.json",authorities)
  observer=Collector(out,fx);adapter=Adapter([sys.executable,"-B","-m","lore_execution.adapter","--trusted-config",str(config_path),"--trusted-config-sha256",sha(config_path)],fx,out)
  def call(i,method,binding,**extra):
   return adapter.call(method,dict(request=requests[i],authority=authorities[i],binding=binding,state_dir=str(fx["state"]),**extra))
  def finish(i):
   observer.fx=dict(fx,request=requests[i],authority=authorities[i])
   initial=call(i,"execute",{});check("tool%d_execute"%i,"error"not in initial,response=initial)
   if "error"in initial:return None
   binding=initial["binding"];physical_bindings.append(binding)
   call(i,"await_exit",binding);cp=call(i,"checkpoint",binding,checkpoint_id="original",purpose="ordinary-tool")
   assert "error"not in cp;binding=cp["binding"];physical_bindings[-1]=binding
   prepared=observer.capture(cp,binding,"tool%d-prepared"%i)
   assert prepared["archive"]["files"]["effect"]["count"]==1
   original={k:copy.deepcopy(cp["artifacts"][k])for k in ("stdout","stderr","checkpoint")};raw={k:file_bytes(v)for k,v in original.items()}
   sealed=call(i,"seal",binding,receipt=original["checkpoint"]);assert "error"not in sealed
   stopped=observer.capture(sealed,binding,"tool%d-stopped"%i)
   assert not stopped["physical"]["container_running"]and stopped["physical"]["namespace_pids"]==[]
   released=call(i,"release",binding);check("tool%d_release_without_S_receipt"%i,"error"not in released,response=released)
   check("tool%d_actual_objects_absent"%i,observer.inspect(binding["container_id"])is None and binding["volume_id"]not in observer.ids("volume"))
   query=call(i,"query",binding);assert "error"not in query
   check("tool%d_original_refs_bytes_retained"%i,all(query["artifacts"].get(k)==ref and file_bytes(ref)==raw[k]for k,ref in original.items()))
   slot= json.loads(file_bytes(query["artifacts"]["slot"]))
   row=slot["reservations"][binding["slot_reservation_id"]];directory=fx["state"]/hashlib.sha256(binding["execution_id"].encode()).hexdigest()
   actual=allocated(directory,adapter.p.pid);debt=row.get("retained_spool")
   good=row["state"]=="RELEASED"and all(row[k]==binding[k]for k in ("execution_id","object_generation","request_digest"))and bool(debt)and debt["path"]==str(directory)and debt["root"]==actual["root"]and debt["allocated_bytes"]>=actual["allocated_bytes"]>0 and debt["inodes"]>=actual["inodes"]>0
   check("tool%d_retained_spool_charged"%i,good,reservation=row,actual=actual)
   repeated=call(i,"release",binding);check("tool%d_same_release_no_new_debt"%i,"error"not in released and "error"not in repeated and repeated["artifacts"]["slot"]==released["artifacts"]["slot"])
   return dict(binding=binding,original=original,raw=raw,reservation=row,directory=str(directory))
  old=finish(0);assert old is not None
  second=finish(1)
  if second is not None:
   q=call(0,"query",old["binding"]);slot=json.loads(file_bytes(q["artifacts"]["slot"]))
   row=slot["reservations"][old["binding"]["slot_reservation_id"]]
   check("old_debt_and_original_archive_survive_next_tool",row==old["reservation"]and all(q["artifacts"][k]==v and file_bytes(v)==old["raw"][k]for k,v in old["original"].items()))
   live=[v for v in slot["reservations"].values()if v["state"]not in("RELEASED","RECLAIMED")];retired=[v for v in slot["reservations"].values()if v["state"]in("RELEASED","RECLAIMED")]
   measured=allocated(fx["state"],adapter.p.pid);control=allocated(fx["state"]/".slots",adapter.p.pid)
   bytes_total=sum(v["writable_bytes"]for v in live)+sum(v["retained_spool"]["allocated_bytes"]for v in retired)+max(0,control["allocated_bytes"]-1048576)
   inode_total=sum(v["writable_inodes"]for v in live)+sum(v["retained_spool"]["inodes"]for v in retired)+max(0,control["inodes"]-128)
   check("aggregate_live_plus_retired_actual_debt_bounded",bytes_total<=134217728 and inode_total<=8192 and measured["allocated_bytes"]<=134217728 and measured["inodes"]<=8192,charged_bytes=bytes_total,charged_inodes=inode_total,actual=measured)
  adapter.stop()
  # Deliberately only the existing schema2 release guard, not Node execution or ownership-source verification.
  original=json.loads((out.parent/"node-original-record.json").read_bytes());negative=copy.deepcopy(original)
  assert negative["request"]["schema_version"]==2 and negative["released"]is True
  next(iter(negative["checkpoints"].values()))["retention"]["state"]="RETAINED"
  save(out/"node-controlled-branch-record.json",negative)
  store=ExecutionStore(str(fx["state"]),trusted_config=str(config_path),trusted_config_sha256=sha(config_path))
  try:
   try:store.slots.release(negative);error=None
   except Exception as exc:error=dict(code=getattr(exc,"code",None),message=str(exc))
   check("schema2_still_requires_checkpoint_transfer",error==dict(code="INCOMPLETE_OBSERVATION",message="local checkpoint ownership remains live"),actual_error=error,scope="direct guard only")
  finally:store.journal.close()
 except Exception as exc:check("probe_completed_original_sequence",False,error=repr(exc))
 finally:
  if adapter:adapter.stop()
  if observer:
   for binding in physical_bindings:
    try:check("owned_cleanup",True,objects=exact_cleanup(observer,fx,binding))
    except Exception as exc:check("owned_cleanup",False,error=repr(exc))
   check("original_engine_baseline_preserved",observer.ids("container")==observer.baseline_containers and observer.ids("volume")==observer.baseline_volumes)
  save(out/"assessment.json",dict(status="PASS"if checks and all(v["passed"]for v in checks)else"FAIL",checks=checks))
 return 0 if checks and all(v["passed"]for v in checks)else 1


def main():
 ap=argparse.ArgumentParser();ap.add_argument("--batch",required=True);ap.add_argument("--worker",action="store_true");a=ap.parse_args()
 if a.worker:return worker(ROOT.parent/"actual")
 assert a.batch.replace("-","").isalnum()
 out=ROOT/"validation/tool-slot-release-evidence"/a.batch;out.mkdir(parents=True,exist_ok=False);ws=out/"workspace"
 source=capture("lore_execution.adapter",[ROOT],ws);assert source
 protocol=ROOT/"design/g4/x-tool-slot-release-001/protocol.json";spec=json.loads(protocol.read_bytes())
 original=ROOT/spec["node_branch_negative"]["original_record"];assert sha(original)==spec["node_branch_negative"]["sha256"]
 (out/"node-original-record.json").write_bytes(original.read_bytes())
 paths=[Path(__file__).resolve(),ROOT/"validation/x_tool_inode_probe.py",protocol,ROOT/"design/g3/x-node-profile/profile.json",ROOT/"research/docker-linux/seccomp.json",ROOT/"validation/components/v/source_snapshot.py",ROOT/"validation/components/r/process_group.py",*(ROOT/"validation/components/x").glob("*.py"),*(ROOT/"design/g3/x").glob("*.json")]
 paths += [p for p in (ROOT/"lore_execution").rglob("*")if p.is_file()and p.suffix!=".py"and "__pycache__"not in p.parts]
 inputs=[]
 for p in paths:
  q=ws/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());inputs.append(dict(original=str(p),copy=str(q),sha256=sha(q)))
 audit=ws/"sitecustomize.py";audit.write_text(AUDIT);generated={str(audit):sha(audit),str(out/"node-original-record.json"):sha(out/"node-original-record.json")}
 save(out/"before.json",dict(candidate=source,inputs=inputs,generated=generated))
 with (out/"stdout").open("wb")as stdout,(out/"stderr").open("wb")as stderr:
  proc=subprocess.Popen([sys.executable,"-B",str(ws/"validation/x_tool_slot_release_probe.py"),"--batch",a.batch,"--worker"],cwd=ws,env=dict(PATH="/usr/bin:/bin",LANG="C.UTF-8",PYTHONPATH=str(ws),PYTHONDONTWRITEBYTECODE="1",LORE_X_REQUIRE_SOURCE_AUDIT="1"),stdout=stdout,stderr=stderr,start_new_session=True)
  try:code=proc.wait(timeout=180)
  except subprocess.TimeoutExpired:code=124
  finally:clean=process_cleanup(proc.pid)
 events=[json.loads(l)for p in(out/"imports").glob("*.jsonl")for l in p.read_text().splitlines()];known={**source["executed_snapshot"],**generated,**{v["copy"]:v["sha256"]for v in inputs}};executions=[v for v in events if v["kind"]=="exec"]
 bound=bool(executions)and all(known.get(v["filename"])==v["sha256"]for v in executions);stable=unchanged(source)and all(sha(v[k])==v["sha256"]for v in inputs for k in("original","copy"))and all(sha(p)==h for p,h in generated.items());children=python_children(events,ws)
 adapters=[json.loads(l)for p in(out/"actual").rglob("adapter-processes.jsonl")for l in p.read_text().splitlines()];pids={v["pid"]for v in executions if v["filename"]in source["executed_snapshot"]};actual_adapters=bool(adapters)and all(v["pid"]in pids for v in adapters);ac=[dict(pid=v["pid"],**process_cleanup(v["pid"]))for v in adapters]
 result=dict(status="PASS"if code==0 and bound and stable and children["pass"]and actual_adapters and not clean["before"]and all(not v["before"]for v in ac)else"FAIL",exit_code=code,source_unchanged=stable,observed_source_bound=bound,children=children,every_adapter_executed_copy=actual_adapters,cleanup=clean,adapter_cleanup=ac,actual=str(out/"actual/assessment.json"));save(out/"result.json",result);print(json.dumps(result));return 0 if result["status"]=="PASS"else 1

if __name__=="__main__":raise SystemExit(main())
