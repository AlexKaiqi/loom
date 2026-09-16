"""Fixed Linux host assets backed by actual F; no facility or policy execution."""
import copy
import json
from pathlib import Path
from lore_execution.errors import require
from lore_execution.journal import canonical, digest
from lore_execution.node_profile import NodeProfile, guarded
from lore_execution.ordinary_sources import document, file_object, readonly
from lore_files.metadata import walk
from lore_files.util import identity, ordinary_path
from .session_plan_files import immutable, json_file

CODE_FILES = tuple("lore_session/node/"+name+".mts" for name in
                   ("entry","adapter","session","callbacks","stdio","common")) + (
    "harnesses/minimal/index.mts","harnesses/minimal/projection.mts","harnesses/runtime/index.mts")
KINDS = ("snapshot","readonly-view","owner-receipt","grant","storage-charge")
# 2026-09-14 (m01-output-budget amendment, batch-ah counterexample): the helper
# reservation derives from the per-execution slot envelope (3*CONTROL_BYTES /
# 128+CONTROL_INODES); after the envelope's 8x rise the plan totals must hold
# the concurrent reservations and retained spool debt. 128 MiB -> 256 MiB,
# 8192 -> 16384 inodes. Old values retained in the amendment record.
# 2026-09-15 (amendment-linux-browser): the shared tool role grows to the
# browser workload scale (512 MiB / 0.5 cpu); the total covers S+tool+helper.
# The default python path is unchanged at the request layer (tool_plans derives
# request budgets from the environment profile and clamps to these role caps).
SLOT = dict(max_objects=3,memory_bytes=1478490112,session_memory_bytes=536870912,
            tool_memory_bytes=805306368,helper_memory_bytes=134217728,
            cpus=dict(S=.5,tool=1.0,helper=.25),all_active_writable_bytes=536870912,
            all_active_writable_inodes=16384)


class StartupAssets:
    @guarded
    def __init__(self,root,config):
        c=copy.deepcopy(config)
        allowed={"principal","namespace","sources","code_sources","profile_ref","request_template_ref",
                 "deps_mount","model","capability_limits","original_refs"}
        require(set(c)<=allowed and allowed-{"original_refs"}<=set(c),"INVALID_REQUEST","unknown/missing fixed host input")
        require(all(type(c[k]) is str and c[k] for k in ("principal","namespace")),"INVALID_REQUEST","fixed principal/namespace required")
        require(set(c["sources"])=={"surface","workspace"} and set(c["code_sources"])==set(CODE_FILES),
                "INVALID_REQUEST","complete original domains/code set required")
        self.root=ordinary_path(root);self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.config=c
        directories={k:self.root/n for k,n in (("artifact_root","artifacts"),("plan_root","plans"),
                    ("authority_root","authority"),("state_root","X-state"),("event_input_root","E-inputs"))}
        for path in directories.values():path.mkdir(mode=0o700,exist_ok=True)
        sources=[]
        for domain in ("surface","workspace"):
            value=c["sources"][domain]
            require(set(value)=={"path","resource_id"} and type(value["resource_id"]) is str and value["resource_id"],
                    "INVALID_REQUEST","fixed original source identity required")
            path=ordinary_path(value["path"])
            require(path.is_dir() and not path.is_relative_to(self.root) and not self.root.is_relative_to(path),
                    "UNAUTHORIZED","caller resource overlaps host control root")
            sources.append(dict(resource_id=value["resource_id"],domain=domain,path=str(path),root=identity(path),revision=1))
        require(sources[0]["resource_id"]!=sources[1]["resource_id"] and
                not Path(sources[0]["path"]).is_relative_to(Path(sources[1]["path"])) and
                not Path(sources[1]["path"]).is_relative_to(Path(sources[0]["path"])),
                "UNAUTHORIZED","two domains must be distinct ordinary resources")
        require(c["model"].keys()<={"id","name","api","provider","reasoning","input","cost","contextWindow","maxTokens"},
                "UNAUTHORIZED","keyless model specification only")
        limits=c["capability_limits"]
        # Archive thresholds (m01-output-budget amendment 2026-09-14): the host
        # records the bounded-context contract alongside max_steps; the values
        # are validated here and enforced by the reference Harness policy.
        def _archive_ok(value):
            return (type(value) is dict and set(value)=={"context_tokens","reserve_tokens","tail_reserve_tokens","soft_tokens"}
                    and all(type(value[k]) is int and value[k]>0 for k in value)
                    and value["reserve_tokens"]<value["context_tokens"] and value["soft_tokens"]<value["context_tokens"])
        require(type(limits) is dict and set(limits)<={"max_steps","archive"} and
                (not limits or type(limits["max_steps"]) is int and 0<limits["max_steps"]<=64) and
                ("archive" not in limits or _archive_ok(limits["archive"])),
                "INVALID_REQUEST","fixed existing Harness limit only")
        profile=document(c["profile_ref"]);request=document(c["request_template_ref"])
        # 2026-09-15 (amendment-linux-browser): admitted session environments are
        # the registered set — the fixed Pi session profile or a registered
        # increment (linux-browser-v1) whose slot plan and template binding hold.
        ADMISSIONS={"fixed-node-pi-session-v1","linux-browser-v1"}
        require(profile["id"] in ADMISSIONS and profile["slot_reservation"]==SLOT
                and request["schema_version"]==2 and request["environment"]==profile["id"],
                "UNAUTHORIZED","fixed admitted Node profile/slot differs")
        extra=c.get("extra_profiles") or []
        require(type(extra) is list,"INVALID_REQUEST","extra profiles must be a list")
        extra_refs=[]
        for item in extra:
            require(type(item) is dict and set(item)=={"id","path","sha256"}
                    and item["id"] in ADMISSIONS and item["id"]!=profile["id"],
                    "INVALID_REQUEST","extra profile registration invalid")
            body=document(item)
            require(body["id"]==item["id"] and body.get("slot_reservation")==SLOT,
                    "INVALID_REQUEST","extra profile slot plan differs")
            extra_refs.append(immutable(directories["artifact_root"]/("node-profile-"+item["id"]+".json"),
                file_object(item["path"])[1]))
        profile_ref=immutable(directories["artifact_root"]/"node-profile.json",file_object(c["profile_ref"]["path"])[1])
        request_ref=immutable(directories["artifact_root"]/"node-request-template.json",file_object(c["request_template_ref"]["path"])[1])
        require(all(profile_ref[k]==c["profile_ref"][k] and request_ref[k]==c["request_template_ref"][k] for k in ("bytes","sha256")),
                "INVALID_REQUEST","fixed profile source changed while copying")
        deps=copy.deepcopy(c["deps_mount"])
        require(deps["role"]=="dependencies" and deps["target"]=="/opt" and deps["read_only"] is True,
                "UNAUTHORIZED","fixed dependency mount required")
        readonly(deps)
        code_root=directories["artifact_root"]/"code-source";code_root.mkdir(exist_ok=True)
        for name in CODE_FILES:
            ref=c["code_sources"][name];actual,data=file_object(ref["path"])
            require(all(ref[k]==actual[k] for k in ("path","bytes","sha256")),"INVALID_REQUEST","actual original code differs")
            immutable(code_root/name,data)
        require({p.relative_to(code_root).as_posix() for p in code_root.rglob("*") if p.is_file()}==set(CODE_FILES),
                "INVALID_REQUEST","unexpected ordinary code member")
        slot_ref=dict(owner="trusted-X-configuration",slot_id="runtime-shared-slot",revision=1,
                      plan_sha256=digest(canonical(SLOT)),role="session")
        slot=dict(slot_id=slot_ref["slot_id"],revision=1,namespace=c["namespace"],plan_sha256=slot_ref["plan_sha256"],
                  plan=copy.deepcopy(SLOT),allowed_principals=["trusted-S"],state_root=str(directories["state_root"]))
        trusted=dict(schema="lore-x-trusted-node-test-config/v1",transport_principal="trusted-S",
            state_root=str(directories["state_root"]),
            profiles=[dict(id=profile["id"],**profile_ref)]
                +[dict(id=item["id"],**ref) for item,ref in zip(extra,extra_refs)],
            slots=[slot],
            grants=[],references=dict(snapshots=[],F_views=[],owner_receipts=[]),read_only_roots=[],
            allowed_harness_entries=[dict(path="/harness/lore_session/node/entry.mts",
                sha256=c["code_sources"]["lore_session/node/entry.mts"]["sha256"],argv_modes=["--config"])],
            dynamic_reference_authorities=[dict(root=str(directories["authority_root"]),identity="trusted-Runtime-F-S-owner",
                namespace=c["namespace"],allowed_kinds=list(KINDS),rule="immutable-full-ref-registration/v1")])
        self.config_ref=json_file(self.root/"trusted-X-config.json",trusted)
        self.host=dict(principal=c["principal"],namespace=c["namespace"],**{k:str(v) for k,v in directories.items()},
            initial_sources=sources,authorization=dict(owner="trusted-runtime-host",namespace=c["namespace"],root=str(self.root)),
            trusted_config_ref=self.config_ref,profile_ref=profile_ref,request_template_ref=request_ref,
            deps_mount=deps,slot_ref=slot_ref,model=c["model"])
        json_file(self.root/"host.json",self.host)
        json_file(self.root/"startup-inputs.json",c)
        NodeProfile(self.config_ref["path"],self.config_ref["sha256"],self.host["state_root"])
        self.register("readonly-view",deps,dict(namespace=c["namespace"],role="dependencies"))

    @classmethod
    @guarded
    def open_existing(cls,root,config,*,control):
        from .startup_reentry import open_existing
        return open_existing(cls,root,config,control)

    @guarded
    def register(self,kind,ref,scope):
        require(kind in KINDS and scope["namespace"]==self.host["namespace"],"UNAUTHORIZED","original registration namespace/kind differs")
        name=digest(canonical(dict(kind=kind,ref=ref)))+".json"
        return json_file(Path(self.host["authority_root"])/name,dict(kind=kind,ref=ref,registered_scope=scope))

    def _capture(self,files,path,resource_id,domain):
        path=ordinary_path(path)
        binding=dict(resource_id=resource_id,domain=domain,path=str(path),root=identity(path),revision=1,
                     authorization=self.host["authorization"])
        bundle=files.capture("startup-"+digest(canonical(binding)),binding,dict(owner="trusted-runtime-initial",binding=binding))
        _,tree,_=files.versions.load(bundle["version_ref"])
        require(walk(path,files.limits)[0]==tree,"BASE_CHANGED","original captured startup tree changed")
        return bundle

    def _descriptor(self,files,label,body):
        path=Path(self.host["artifact_root"])/(label+"-source");path.mkdir(exist_ok=True)
        json_file(path/"descriptor.json",body)
        bundle=self._capture(files,path,"startup-"+label+"-"+digest(str(self.root).encode()),"surface")
        ref=dict(owner="F",kind="file",path="descriptor.json",version_ref=bundle["version_ref"],
                 sha256=digest(canonical(body)+b"\n"))
        require(files.read_reference(ref,self.host["authorization"])==canonical(body)+b"\n",
                "INVALID_REQUEST","actual F descriptor bytes differ")
        return ref

    @guarded
    def build(self,files):
        if getattr(self,"_reentry",False):
            from .startup_reentry import build_existing
            return build_existing(self,files)
        versions={}
        for source in self.host["initial_sources"]:
            require(identity(ordinary_path(source["path"]))==source["root"],"STALE_BINDING","original caller resource replaced")
            versions[source["domain"]]=self._capture(files,source["path"],source["resource_id"],source["domain"])
        root=Path(self.host["artifact_root"])
        code=self._capture(files,root/"code-source","startup-code-"+digest(str(self.root).encode()),"surface")
        material=files.materialize("startup-code-read-"+digest(str(self.root).encode()),code["version_ref"],str(root/"code-read"),self.host["authorization"])
        harness=self._descriptor(files,"harness",dict(code=dict(bundle=code,materialized=material),
                    entry="lore_session/node/entry.mts",harness_entry="harnesses/runtime/index.mts"))
        originals=copy.deepcopy(self.config.get("original_refs",{}))
        for name,row in originals.items():
            require(type(name) is str and name and "/" not in name and name not in (".","..")
                    and set(row)=={"source_ref","read_path"} and row["read_path"]=="/input/originals/"+name,
                    "UNAUTHORIZED","original source mapping differs")
            files.read_reference(row["source_ref"],self.host["authorization"])
        cap=self._descriptor(files,"capability",dict(targets=["runtime","workspace"],limits=self.config["capability_limits"],original_refs=originals))
        specs=[dict(request_id="startup-register-"+digest(canonical([self.host["namespace"],source["resource_id"]])),resource_id=source["resource_id"],namespace=self.host["namespace"],
                    kind=source["domain"],path=source["path"],harness_ref=harness,grants={self.host["principal"]:["read","write"]})
               for source in self.host["initial_sources"]]
        return copy.deepcopy(dict(host=self.host,initial_refs=dict(harness_ref=harness,capability_ref=cap,
                     **{d+"_version_ref":bundle["version_ref"] for d,bundle in versions.items()}),
                     registrations_spec=specs,config_ref=self.config_ref))
