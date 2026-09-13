"""Finite actual F/R startup asset checks; no Engine/model/NATS client."""
import argparse,copy,hashlib,importlib,json,os,shutil,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
CODES=["lore_session/node/"+v+".mts" for v in ("entry","adapter","session","callbacks","stdio","common")]+["harnesses/minimal/index.mts","harnesses/minimal/projection.mts","harnesses/runtime/index.mts"]
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def save(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw(v)+b"\n")
def load(p):return json.loads(Path(p).read_bytes())
def fact(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
def ident(p):s=Path(p).lstat();return dict(dev=s.st_dev,ino=s.st_ino)
def need(v,m):
 if not v:raise AssertionError(m)
def rejects(fn):
 try:fn()
 except Exception as e:
  need(getattr(e,"code",None) in ("UNAUTHORIZED","INVALID_REQUEST","STALE_BINDING","BASE_CHANGED","CONFLICT","VERSION_CORRUPT","CHANGE_OBSERVED"),"unexpected rejection "+repr(e));return dict(code=e.code,message=str(e))
 raise AssertionError("invalid startup accepted")

class Fixture:
 def __init__(self,root,cls):
  from lore_control import ControlStore
  from lore_files import FileStore
  from lore_runtime.host_files import HostFiles
  self.root=Path(root);self.root.mkdir(parents=True)
  for domain in ("surface","workspace"):(self.root/domain).mkdir()
  (self.root/"surface/template.md").write_text("Original {{notes.md}}\n")
  (self.root/"surface/notes.md").write_text("Only original ordinary input.\n")
  (self.root/"workspace/numbers.json").write_text("[2,3,5]\n")
  dm=load(ROOT/"original-host/dependencies-manifest.json")
  model=dict(id="faux-1",name="Faux",api="faux",provider="faux",reasoning=False,input=["text","image"],cost=dict(input=0,output=0,cacheRead=0,cacheWrite=0),contextWindow=128000,maxTokens=16384)
  self.config=dict(principal="operator",namespace="startup-test",sources={d:dict(path=str(self.root/d),resource_id="original-"+d) for d in ("surface","workspace")},code_sources={n:fact(ROOT/n) for n in CODES},profile_ref=fact(ROOT/"original-host/profile.json"),request_template_ref=fact(ROOT/"original-host/request-template.json"),deps_mount=dict(role="dependencies",source=dm["root"],target="/opt",read_only=True,manifest_ref=fact(ROOT/"original-host/dependencies-manifest.json"),content_ref=dm["source_ref"]),model=model,capability_limits=dict(max_steps=16))
  self.assets=cls(self.root/"host",self.config)
  self.control=ControlStore(self.root/"R.sqlite",{"operator":dict(namespaces=["startup-test"],roles=["admin","runtime","submit"])})
  self.owner=HostFiles(self.control,self.assets.host)
  self.files=FileStore(self.root/"F",self.owner.authorization,self.owner.reference,limits=dict(max_entries=1024,max_logical_bytes=4194304,max_archive_bytes=8388608,window_seconds=10))
  self.owner.files=self.files;self.control.reference_checker=self.owner.control_reference
  self.result=self.assets.build(self.files)
  self.registrations={s["kind"]:self.control.register("operator",**s) for s in self.result["registrations_spec"]}
 def close(self):
  (self.root/"original-R.sql").write_text("\n".join(self.control.db.iterdump()));self.control.close()

def run_case(id,path,cls):
 f=Fixture(path,cls)
 try:
  r=f.result
  if id=="SA01":
   H=r["initial_refs"]["harness_ref"];cap=r["initial_refs"]["capability_ref"]
   h=f.owner._harness(H)
   _,tree,contents=f.files.versions.load(h["code"]["bundle"]["version_ref"])
   need({n for n,v in tree["entries"].items() if v["kind"]=="file"}==set(CODES),"code set differs")
   need(all(contents[n]==(ROOT/n).read_bytes() for n in CODES),"original code bytes differ")
   need(json.loads(f.files.read_reference(cap,f.assets.host["authorization"]))["targets"]==["runtime","workspace"],"capability targets differ")
   from lore_execution.node_profile import NodeProfile
   validator=NodeProfile(r["config_ref"]["path"],r["config_ref"]["sha256"],r["host"]["state_root"])
   for d,reg in f.registrations.items():
    need(reg["path"]==str(f.root/d) and {k:reg[k] for k in ("dev","ino")}==ident(f.root/d),"caller source replaced by materialization")
    view=f.owner.resolve(r["initial_refs"][d+"_version_ref"],"F-view",dict(registration=reg))
    need(view["materialized"]["path"]==str(f.root/d),"source view root differs")
   return dict(assets=r,code_files={n:sha(contents[n]) for n in CODES},actual_config=validator.config)
  if id=="SA02":
   need(cls(f.root/"host",f.config).build(f.files)==r,"repeat changes original references")
   bad=copy.deepcopy(f.config);bad["code_sources"].pop(CODES[-1]);results=[rejects(lambda:cls(f.root/"host-bad",bad))]
   bad=copy.deepcopy(f.config);bad["code_sources"][CODES[0]]["sha256"]="0"*64;results.append(rejects(lambda:cls(f.root/"host-corrupt",bad)))
   (f.root/"surface").rename(f.root/"surface-old");shutil.copytree(f.root/"surface-old",f.root/"surface")
   try:results.append(rejects(lambda:cls(f.root/"host",f.config)))
   finally:shutil.rmtree(f.root/"surface");(f.root/"surface-old").rename(f.root/"surface")
   p=f.root/"surface/notes.md";original=p.read_bytes();st=p.stat()
   try:p.write_bytes(b"outside modification\n");results.append(rejects(lambda:f.assets.build(f.files)))
   finally:p.write_bytes(original);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
   return results
  from lore_session.snapshots import SnapshotStore
  from lore_runtime.session_plans import SessionPlans
  from lore_events.input_files import packet,publish,validate
  host=f.assets.host;snapshots=SnapshotStore(f.root/"S",host["namespace"],f.assets.register)
  scope=dict(namespace=host["namespace"],surface_id="original-surface",session_id="initial-session",session_generation=1)
  def resolve(ref,purpose,expected):
   if purpose=="session":return dict(scope=scope,confirmation_request_id=None)
   raise AssertionError("unneeded source purpose "+purpose)
  f.owner.session_resolver=resolve
  old=f.control.reference_checker
  def refs(ref,purpose,expected):
   if purpose=="input":validate(ref,expected["binding"],host["event_input_root"]);return True
   return old(ref,purpose,expected)
  f.control.reference_checker=refs
  initial=r["initial_refs"];selector=dict(namespace=host["namespace"],source="operator",start_sequence=1,filters={},page_size=16,surface_ref=initial["surface_version_ref"],previous_session_ref=None,execution_targets=[dict(resource_id="original-"+d,version_ref=initial[d+"_version_ref"]) for d in ("surface","workspace")])
  payload=dict(resource_id="original-surface",resource_revision=1,harness_ref=initial["harness_ref"],input_ref=None,input_binding=selector,session_ref=dict(owner="S",**scope,confirmation_request_id=None),source_result_ref=None,capability_ref=initial["capability_ref"])
  f.control.accept("operator",dict(id="startup-invocation",namespace=host["namespace"],kind="invocation",payload=payload))
  span=dict(start_sequence=1,end_sequence=0,high_water=0,next_sequence=1)
  input_ref=publish(Path(host["event_input_root"]),"startup-invocation",packet("startup-invocation",selector,span,[],[]));f.control.bind_input("operator","startup-invocation",selector,input_ref)
  plans=SessionPlans(f.control,f.files,snapshots,host,f.owner.resolve,f.assets.register)
  plan=plans.prepare("operator","startup-invocation",execution_id="s-exec-"+sha(raw(["startup-invocation","accept"])))
  need(plan["node_config"]["runtime_context"]["input"]["range"]==span,"E original range differs")
  need(plan["request"]["command_argv"][-3:]==["/harness/lore_session/node/entry.mts","--config","/input/node-config.json"],"ordinary Node argv differs")
  return dict(plan=plan,input_ref=input_ref,scope="actual R E-file F S X-validation only; no Engine/Node/NATS")
 finally:f.close()

def main():
 p=argparse.ArgumentParser();p.add_argument("--batch",required=True);p.add_argument("--worker",action="store_true");a=p.parse_args()
 if a.worker:
  out=Path(a.batch)
  try:cls=importlib.import_module("lore_runtime.startup_assets").StartupAssets
  except ModuleNotFoundError:save(out/"result.json",dict(status="MISSING",actual_runs=0));return 2
  results=[]
  for id in ["SA01","SA02","SA03"]:
   try:results.append(dict(id=id,status="PASS",result=run_case(id,out/"actual"/id,cls)))
   except BaseException as e:results.append(dict(id=id,status="FAIL",error=repr(e),traceback=traceback.format_exc()))
   save(out/"assessment.json",results)
  status="PASS_STARTUP_NOENGINE_ONLY" if all(r["status"]=="PASS" for r in results) else "FAIL"
  save(out/"result.json",dict(status=status,actual_runs=3));return 0 if status!="FAIL" else 1
 out=ROOT/"validation/startup-assets-evidence"/a.batch;out.mkdir(parents=True,exist_ok=False);work=out/"workspace";work.mkdir()
 paths=[Path(__file__).relative_to(ROOT),Path("design/g3/system/startup-assets.md"),*[Path(n) for n in CODES]]
 for package in ["lore_runtime","lore_control","lore_files","lore_events","lore_execution","lore_session"]:paths += [p.relative_to(ROOT) for p in (ROOT/package).glob("*") if p.is_file() and p.suffix in (".py",".json")]
 host=[Path("design/g3/x-node-profile")/n for n in ("profile.json","request-template.json")]+[Path("validation/components/x_node_profile/evidence/node-independent-full-001/actual/shared/dependencies-manifest.json")];paths+=host
 before={str(p):sha((ROOT/p).read_bytes()) for p in paths}
 for p in paths:(work/p).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p,work/p)
 (work/"original-host").mkdir()
 for p in host:shutil.copy2(work/p,work/"original-host"/p.name)
 save(out/"source-before.json",before)
 command=[sys.executable,"-B",str(work/"validation/startup_assets_probe.py"),"--worker","--batch",str(out)];save(out/"command.json",dict(argv=command,cwd=str(work)))
 with (out/"stdout").open("wb") as stdout,(out/"stderr").open("wb") as stderr:proc=subprocess.run(command,cwd=work,env=dict(os.environ,PYTHONPATH=str(work),PYTHONDONTWRITEBYTECODE="1"),stdout=stdout,stderr=stderr,timeout=120)
 result=load(out/"result.json") if (out/"result.json").exists() else dict(status="FAIL",actual_runs=0)
 result.update(exit_code=proc.returncode,source_unchanged=all(sha((ROOT/p).read_bytes())==h for p,h in before.items()),copied_source=all(sha((work/p).read_bytes())==h for p,h in before.items()));save(out/"result.json",result);print(json.dumps(result));return proc.returncode if result["source_unchanged"] and result["copied_source"] else 1
if __name__=="__main__":raise SystemExit(main())
