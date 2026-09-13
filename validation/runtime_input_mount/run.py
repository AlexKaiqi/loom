"""Three original runtime-input groups. NoEngine checks do not prove physical mounts."""
import argparse, base64, copy, hashlib, importlib, io, json, sys, tarfile, traceback
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from validation.components.x.fixtures import create
from validation.components.s.f_peer import Peer
from lore_runtime.session_plan_files import InputFiles
from lore_execution.journal import canonical, digest
from lore_execution.errors import ExecutionError

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")
def need(value, message):
    if not value: raise AssertionError(message)

class Fixture:
    def __init__(self, root):
        self.fx = create(root, {"initial":{"script":"binary_effect"}}, {"domain":"runtime","cpu":.25})
        self.root, self.state = root, self.fx["state"]
        port = root / "peer-state/f-port"; port.mkdir(parents=True)
        self.ns = self.fx["authority"]["namespace"]
        self.peer = Peer(port, {"namespace":self.ns,"principal":"independent-fixture"})
        self.original = root / "workspace-old"; self.original.mkdir()
        (self.original / "report.json").write_bytes(b'{"sum":10}\n')
        self.view = self.peer.capture(self.original, "workspace")
        self.file_ref, _ = self.peer.original_file(self.view, "report.json")
        self.old = self.peer.read_F(self.file_ref)
        (self.original / "report.json").write_bytes(b'{"sum":999}\n')
        self.authority_root = root / "authority"; self.authority_root.mkdir()
        self.projections = InputFiles(self.peer.store, {"plan_root":str(root/"generated"),"namespace":self.ns}, self.register)
        self.mount = self.projections.mount(self.view, "input", root)
        profile_path = ROOT / "design/g3/x-node-profile/profile.json"
        profile = json.loads(profile_path.read_bytes()); plan = profile["slot_reservation"]
        self.slot = dict(owner="trusted-X-configuration",slot_id="runtime-input-slot",revision=1,plan_sha256=digest(canonical(plan)),role="tool")
        slot = dict(slot_id=self.slot["slot_id"],revision=1,namespace=self.ns,plan_sha256=self.slot["plan_sha256"],plan=plan,allowed_principals=["trusted-S"],state_root=str(self.state))
        self.config = dict(schema="lore-x-trusted-node-test-config/v1",transport_principal="trusted-S",state_root=str(self.state),profiles=[dict(id=profile["id"],path=str(profile_path),sha256=sha(profile_path))],slots=[slot],grants=[],references={},read_only_roots=[],allowed_harness_entries=[],dynamic_reference_authorities=[dict(root=str(self.authority_root),namespace=self.ns,allowed_kinds=["grant","readonly-view"],rule="immutable-full-ref-registration/v1")])
        self.config_path = root / "config.json"; save(self.config_path,self.config)
        self.request = copy.deepcopy(self.fx["request"]); self.request["caller"]="trusted-S"
        self.request["readonly_mounts"]=[self.mount]
        self.authority = self.authorize(self.request)
        save(root/"originals.json",dict(request=self.request,authority=self.authority,mount=self.mount,old_file_ref=self.file_ref,old_bytes_sha256=digest(self.old),config=self.config))
    def register(self,kind,ref,scope):
        path=self.authority_root/(digest(canonical(dict(kind=kind,ref=ref)))+".json")
        save(path,dict(kind=kind,ref=ref,registered_scope=scope))
    def authorize(self,request):
        auth=copy.deepcopy(self.fx["authority"]);auth["caller"]="trusted-S";auth["slot_ref"]=copy.deepcopy(self.slot)
        auth["domain"]=request["domain"]
        grant=dict(principal="trusted-S",operations=["execute","query","checkpoint","stop"],original_request=request,request_digest=digest(canonical(request)),scope={"namespace":self.ns},slot_ref=self.slot,role="tool")
        path=self.root/("grant-"+grant["request_digest"]+".json");save(path,grant)
        ref=dict(owner="trusted-X-configuration",id=grant["request_digest"],record_path=str(path),sha256=sha(path))
        self.register("grant",ref,{"namespace":self.ns});auth["grant_ref"]=ref;return auth

class BeforeCreate(Exception): pass
class NoEngine:
    calls=[]
    def __init__(self,*args,**kwargs): pass
    def call(self,*args,**kwargs):
        self.calls.append([args,kwargs]);raise AssertionError("Engine forbidden in NoEngine checks")

def capture_prepare(module, fx, request=None, authority=None, config=True):
    request=copy.deepcopy(request or fx.request); authority=copy.deepcopy(authority or fx.authority)
    reached={};NoEngine.calls=[]
    def stop_create(self,req,auth,checked,raw,generation):
        reached.update(checked=copy.deepcopy(checked),raw=raw);raise BeforeCreate()
    with patch("lore_execution.store.Engine",NoEngine), patch.object(module.ExecutionStore,"_create",stop_create):
        store=module.ExecutionStore(str(fx.state),**(dict(trusted_config=str(fx.config_path),trusted_config_sha256=sha(fx.config_path)) if config else {}))
        try:
            try:store.execute(request,authority)
            except BeforeCreate:pass
        finally:store.journal.close()
    need(not NoEngine.calls,"Engine call before validation")
    need(reached,"did not reach the original creation boundary")
    return reached

def reject(call):
    try:call()
    except ExecutionError as exc:
        need(exc.code in {"UNAUTHORIZED","INVALID_REQUEST","STALE_BINDING","INPUT_VERSION_UNAVAILABLE","ID_CONFLICT"},"unexpected rejection code")
        need(not NoEngine.calls,"rejection issued Engine call")
        return dict(code=exc.code,message=str(exc))
    raise AssertionError("invalid input was accepted")

def sources():
    paths=[*sorted((ROOT/"lore_execution").glob("*.py")),ROOT/"lore_execution/profile.json",ROOT/"lore_execution/seccomp.json",Path(__file__),ROOT/"validation/runtime_input_mount/protocol.json",ROOT/"design/g3/x-runtime-input.md",ROOT/"validation/components/x/fixtures.py",ROOT/"validation/components/s/f_peer.py",ROOT/"lore_runtime/session_plan_files.py"]
    paths += sorted((ROOT/"lore_files").glob("*.py"))
    return {str(p):sha(p) for p in paths}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--batch",required=True);ap.add_argument("--module",default="lore_execution");a=ap.parse_args()
    need(a.batch.replace("-","").isalnum(),"unsafe batch")
    out=ROOT/"validation/runtime_input_mount/evidence"/a.batch;out.mkdir(parents=True,exist_ok=False)
    before=sources();save(out/"source-before.json",before);checks=[];errors=[];baseline={};status="FAIL"
    try:
        module=importlib.import_module(a.module)
        fx=Fixture(out/"fixture")
        from lore_execution.requests import validate
        from lore_execution.node_profile import NodeProfile
        if not hasattr(NodeProfile,"runtime_input") or not hasattr(module,"ExecutionStore"):
            legacy=copy.deepcopy(fx.request);legacy.pop("readonly_mounts")
            baseline["legacy_without_mount_valid"]=bool(validate(legacy,fx.authority,fx.state))
            baseline["with_mount_rejected"]=reject(lambda:validate(fx.request,fx.authority,fx.state))
            baseline["scope"]="NoEngine source baseline; physical old /input absence not yet run"
            status="MISSING"
        else:
            got=capture_prepare(module,fx)
            checks.append(dict(case="RI01",check="actual_F_old_full_ref_and_precreate_mount",passed=got["checked"]["readonly_mounts"]==[fx.mount] and (Path(fx.mount["source"]["path"])/"report.json").read_bytes()==fx.old and fx.peer.read_F(fx.file_ref)==fx.old and (fx.original/"report.json").read_bytes()!=fx.old))
            save(out/"prepared.json",dict(checked={k:v for k,v in got["checked"].items() if k not in ("script","stdin")},archive_sha256=digest(got["raw"])))
            controls=[]
            def bad(name,q=None,auth=None,config=True):
                controls.append(dict(name=name,**reject(lambda:capture_prepare(module,fx,q,auth,config))))
            bad("no_profile",config=False)
            for key in ("grant_ref","slot_ref"):
                auth=copy.deepcopy(fx.authority);auth.pop(key);bad("missing_"+key,auth=auth)
            auth=copy.deepcopy(fx.authority);auth["namespace"]="other";bad("wrong_namespace",auth=auth)
            for name,change in [("task_domain",lambda q:q.update(domain="task")),("wrong_target",lambda q:q["readonly_mounts"][0].update(target="/outside")),("writable",lambda q:q["readonly_mounts"][0].update(read_only=False)),("wrong_inode",lambda q:q["readonly_mounts"][0]["source"].update(ino=0)),("wrong_version",lambda q:q["readonly_mounts"][0]["content_ref"]["version_ref"].update(archive_sha256="0"*64)),("wrong_hash",lambda q:q["readonly_mounts"][0]["manifest_ref"].update(sha256="0"*64)),("two_mounts",lambda q:q["readonly_mounts"].append(copy.deepcopy(q["readonly_mounts"][0])))]:
                q=copy.deepcopy(fx.request);change(q);bad(name,q,fx.authorize(q))
            original=Path(fx.mount["source"]["path"])/"report.json";saved=original.read_bytes();st=original.stat()
            try:
                original.write_bytes(b'{"sum":11}\n');bad("actual_source_bytes_changed")
            finally:
                original.write_bytes(saved)
                import os
                os.utime(original,ns=(st.st_atime_ns,st.st_mtime_ns))
            controls.append(dict(name="new_mount_restore_unsupported",**reject(lambda:validate(fx.request,fx.authority,fx.state,restore=True))))
            save(out/"negative-controls.json",controls)
            checks.append(dict(case="RI02",check="all_specific_invalid_sources_rejected_before_Engine",passed=len(controls)==13,count=len(controls)))
            with tarfile.open(fileobj=io.BytesIO(got["raw"]),mode="r:") as archive:
                names={m.name.removeprefix("./") for m in archive};files={m.name.removeprefix("./"):archive.extractfile(m).read() for m in archive if m.isfile()}
            expected={p.name:p.read_bytes() for p in fx.fx["target"].iterdir() if p.is_file()}
            legacy=copy.deepcopy(fx.request);legacy.pop("readonly_mounts");old=capture_prepare(module,fx,legacy,fx.authorize(legacy))
            checks.append(dict(case="RI03",check="whole_work_archive_not_projection_and_original_digest",passed=files==expected and "report.json" not in names and "input" not in names and "readonly_mounts" not in old["checked"] and old["raw"]==got["raw"] and old["checked"]["request_digest"]!=got["checked"]["request_digest"]))
            save(out/"work-original.json",dict(members=sorted(names),files={n:digest(v) for n,v in files.items()},old_digest=old["checked"]["request_digest"],new_digest=got["checked"]["request_digest"]))
            status="NOENGINE_PASS" if len(checks)==3 and all(x["passed"] for x in checks) else "FAIL"
    except ModuleNotFoundError as exc:
        status="MISSING";errors.append(repr(exc))
    except Exception as exc:
        errors.append(dict(error=repr(exc),traceback=traceback.format_exc()))
    after=sources();stable=before==after
    if not stable:status="FAIL"
    result=dict(status=status,cases=["RI01","RI02","RI03"],checks=checks,errors=errors,baseline=baseline,source_unchanged=stable,physical_status="UNVERIFIED",Engine_calls=NoEngine.calls)
    save(out/"source-after.json",after);save(out/"result.json",result);print(json.dumps(result))
    return 0 if status=="NOENGINE_PASS" else 4 if status=="MISSING" else 1
if __name__=="__main__":raise SystemExit(main())
