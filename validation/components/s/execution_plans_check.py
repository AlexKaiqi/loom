"""Bounded real-F, no-Engine wiring check for the S trusted fixture assembler."""
from pathlib import Path
import argparse
import base64
import copy
import json
import sys
import traceback
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from validation.components.s.f_peer import Peer
from validation.components.s.execution_plans import ExecutionPlans
from validation.components.s.context_fixtures import long_log,write_materials
from validation.components.x_node_profile.artifacts import file_fact,save,canonical,sha_bytes,archive_bytes
from lore_execution.node_profile import NodeProfile
from lore_execution.requests import validate


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--batch",required=True);args=parser.parse_args()
    root=ROOT/"validation/components/s/evidence"/args.batch;root.mkdir(exist_ok=False)
    rows=[];result={"scope":"TRUSTED_FIXTURE_REAL_F_NO_ENGINE","rows":rows,"status":"FAIL"}
    def check(name,ok,**facts):
        rows.append(dict(check=name,pass_=bool(ok),**facts))
        if not ok:raise AssertionError(name)
    try:
        for name in ("execution_plans.py","execution_plans_check.py","f_peer.py"):
            (root/name).write_bytes((ROOT/"validation/components/s"/name).read_bytes())
        case=root/"case";case.mkdir();port=case/"peer-state/f-port";port.mkdir(parents=True)
        for role in ("surface","workspace","input","originals"):(case/role).mkdir()
        (case/"surface/template.md").write_text("Goal {{notes.md}}\n")
        (case/"surface/notes.md").write_text("ORIGINAL_NOTES\n")
        (case/"workspace/data.json").write_text("[2,3,5]\n")
        (case/"input/events.jsonl").write_text('{"event":"original"}\n')
        (case/"input/feedback.txt").write_text("ORIGINAL_FEEDBACK\n")
        (case/"originals/log").write_bytes(long_log())
        peer=Peer(port,{"namespace":"plans-check","principal":"trusted-collector"})
        params=dict(surface=str(case/"surface"),workspace=str(case/"workspace"),input_dir=str(case/"input"),
                    originals=str(case/"originals"),version="plans-initial",authority=peer.authority)
        refs=peer.call("prepare_fixture_input",params)
        dp=ROOT/"validation/components/x_node_profile/evidence/node-independent-full-001/actual/shared/dependencies-manifest.json"
        dm=json.loads(dp.read_bytes())
        deps=dict(role="dependencies",source=dm["root"],target="/opt",read_only=True,manifest_ref=file_fact(dp,2097152)[0],content_ref=dm["source_ref"])
        plans=ExecutionPlans(case/"plans",peer,"plans-check",deps_mount=deps)
        request=dict(session_scope=dict(namespace="plans-check",surface_id="surface-one",session_id="session-one",session_generation=1),
                     operation_id="op-1",source_result_ref=None,session_snapshot_ref=None,
                     **{k:refs[k] for k in ("harness_ref","input_ref","capability_ref")})
        # A separate JsonPort-style Peer changes the current cap and H after Plans is constructed.
        other=Peer(port,peer.authority)
        request["capability_ref"]=other.call("prepare_fixture_limit_binding",dict(original=refs["capability_ref"],limits={"max_steps":2},authority=peer.authority))
        request["harness_ref"]=other.call("prepare_alternate_fixture_binding",dict(field="harness_ref",original=refs["harness_ref"],authority=peer.authority))
        plan=plans.session(request,execution_id="session-plan-one")
        cfg=plan["node_config"];original_input=peer.lookup("inputs",request["input_ref"])["document"]
        check("current_request_compact_H_cap_and_original_input",cfg["harness_ref"]==request["harness_ref"] and cfg["capability_ref"]==request["capability_ref"] and cfg["input"]["ref"]==request["input_ref"] and cfg["input"]["limits"]=={"max_steps":2})
        full,actual=peer.original_file(plan["input_view"],"node-config.json")
        raw=peer.read_F(full)
        check("generated_config_actual_F_history",json.loads(raw)==cfg and sha_bytes(raw)==actual["sha256"],full_ref=full,actual=actual)
        mount=next(m for m in plan["request"]["readonly_mounts"] if m["role"]=="input")
        path=Path(mount["source"]["path"])
        source=Path(original_input["input"]["materialized"]["path"])
        original_files={p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob("*") if p.is_file()}
        current_files={p.relative_to(path).as_posix():p.read_bytes() for p in path.rglob("*") if p.is_file()}
        check("combined_tree_complete_plus_only_config",set(current_files)==set(original_files)|{"node-config.json"} and all(current_files[k]==v for k,v in original_files.items()))
        check("keyless_fixed_paths",not set(cfg["model"])&{"apiKey","key","token","auth","baseUrl"} and plan["request"]["command_argv"][-3:]==["/harness/lore_session/node/entry.mts","--config","/input/node-config.json"] and cfg["input"]["original_refs"]["log"]["path"]=="/input/originals/log")
        profile=NodeProfile(plan["trusted_config"],plan["trusted_config_sha256"],plans.state_root)
        prepared=profile.prepare(plan["request"],plan["authority"])
        empty=archive_bytes(prepared["raw_archive"])
        check("actual_X_nonEngine_prepare_full_grant_and_empty",set(empty[0])=={"."} and empty[2]==0 and len(prepared["readonly_mounts"])==4 and prepared["slot_ref"]["role"]=="session",binding_extra=prepared["binding_extra"])
        script="printf 'EXACT_ORIGINAL_雪\n' >> report.txt"
        tool=plans.tool(request,"workspace",script,execution_id="tool-one",source_result_ref={"original":"actual-callback-binding"})
        checked=validate(tool["request"],tool["authority"],plans.state_root)
        role=profile.role_slot(tool["request"],tool["authority"])
        check("small_tool_original_script_full_F_state_and_slot",checked["script"]==script.encode() and role["role"]=="tool" and role["slot_ref"]["slot_id"]==prepared["slot_ref"]["slot_id"] and tool["request"]["budgets"]["cpu"]==.25 and tool["request"]["budgets"]["inodes"]==128)
        runtime=plans.tool(request,"runtime",script,execution_id="tool-runtime",source_result_ref=None)
        check("runtime_complete_surface_tree",runtime["F"]==original_input["source_F"]["surface"] and {p["path"] for p in runtime["request"]["input_manifest"]["files"]}=={"template.md","notes.md"})
        full_snapshot=plan["snapshot_bundle"]["snapshot_ref"]
        envelope=dict(owner="S",session_id="session-one",**plan["snapshot_bundle"],original_archive=dict(path=full_snapshot["archive_path"],bytes=full_snapshot["archive_bytes"],sha256=full_snapshot["archive_sha256"]))
        restored=plans.session(dict(request,session_snapshot_ref=envelope),execution_id="session-plan-two")
        profile.prepare(restored["request"],restored["authority"])
        check("existing_S_owner_envelope_exact_original",restored["snapshot_bundle"]==plan["snapshot_bundle"] and restored["request"]["snapshot_ref"]==full_snapshot)
        write_materials(case/"workspace")
        refs2=Peer(port,peer.authority).call("prepare_fixture_input",dict(params,version="plans-large"))
        large_request=dict(request,**{k:refs2[k] for k in ("harness_ref","input_ref","capability_ref")})
        large=plans.tool(large_request,"workspace",script,execution_id="tool-large",source_result_ref=None)
        actual_members=json.loads(Path(large["F"]["bundle"]["manifest_path"]).read_bytes())["tree"]["entries"]
        requested={row["path"]:row for row in large["request"]["input_manifest"]["files"]}
        check("large_complete_original_F_manifest_explicit1024",large["request"]["budgets"]["inodes"]==1024 and set(requested)=={n for n,v in actual_members.items() if v["kind"]=="file"} and len(requested)==514 and all(requested[n]["sha256"]==v["sha256"] for n,v in actual_members.items() if v["kind"]=="file"),files=len(requested),members=len(actual_members))
        for name,bad in [("wrong_namespace",dict(request,session_scope=dict(request["session_scope"],namespace="other"))),
                         ("changed_compact_ref",dict(request,input_ref=dict(request["input_ref"],sha256="0"*64)))]:
            try:plans.session(bad)
            except (ValueError,KeyError) as e:check(name,True,error=str(e))
            else:check(name,False)
        result["status"]="PASS_TRUSTED_FIXTURE_ASSEMBLY_NO_ENGINE"
    except Exception:
        result["error"]=traceback.format_exc()
    finally:
        result["source"]={n:file_fact(ROOT/"validation/components/s"/n)[0] for n in ("execution_plans.py","execution_plans_check.py","f_peer.py")}
        (root/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="rows"},ensure_ascii=False));return 0 if result["status"].startswith("PASS_") else 1

if __name__=="__main__":raise SystemExit(main())
