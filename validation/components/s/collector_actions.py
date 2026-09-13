"""Test action implementation. No case-ID branches and no oracle expected values."""
import copy,json,hashlib
from physical_witness import stop_witness
from live_ports import InvalidEvidence,read_reference,physical_remaining
def perform_action(d,op,args):
    if op=="accept_ack_lost":
        d.fault="accepted_checkpoint_before_ack";d.invoke("accept")
    elif op=="fresh_resubmit_after_ack_loss":
        recovery=json.loads((d.root/"durable-admission-recovery.json").read_text())
        d.accepted=set();d.binding=recovery["binding"];d.snapshot=recovery["snapshot"];d.recovery=True
        from live_ports import original_session_from_archive
        raw=original_session_from_archive(d.snapshot["original_archive"])
        if hashlib.sha256(raw).hexdigest()!=recovery["session_sha256"]:raise InvalidEvidence("saved admission source changed before fresh retry")
        d.raw=raw;d.invoke("accept");d.accepted.add(d.binding["operation_id"])
    elif op=="accept":d.invoke("accept");d.accepted.add(d.binding["operation_id"])
    elif op=="drive":d.drive(args)
    elif op in ("query","query_original"):d.invoke("query")
    elif op=="checkpoint":
        if d.raw is None:raise InvalidEvidence("no actual original Session")
        d.save("session:"+args["label"],d.raw)
    elif op in ("fresh_query","fresh_reconcile"):
        d.recovery=True;d.query_outage=args.get("x_query")=="unknown";d.invoke("query")
        if op=="fresh_reconcile":d.invoke("drive")
        if "bytes:wire_before" in d.artifacts:d.save("bytes:wire_after",(d.root.parent/d.artifacts["bytes:wire_before"]["path"]).read_bytes())
    elif op in ("seal","restart"):d.recovery=op=="restart"
    elif op=="observe_resources":
        for index,record in enumerate(d.journals.get("sealed",[])):
            for actual in stop_witness(record["binding"],record["namespace_witness"],d.root/("os-stop-"+str(index))):d.record("live_namespace_processes",actual)
            for actual in physical_remaining(record["binding"]):d.record("remaining_execution_objects",actual)
    elif op=="resubmit":
        previous=copy.deepcopy(d.binding)
        for field in args["change"]:
            if field=="source_result_ref":
                d.binding[field]=d.last["operation_result_ref"]
            else:
                alternate=d.port("f","prepare_alternate_fixture_binding",field=field,original=previous[field],authority=d.target["fixture_authority"])
                d.binding[field]=alternate
        d.invoke("accept");d.binding=previous
    elif op=="prepare_files":
        d.prepare(args["fixture"])
        if args["fixture"]=="projection-with-original-feedback":
            d.bootstrap_tool_marker=True
            try:d.drive({"response":"single-tool"})
            finally:d.bootstrap_tool_marker=False
            d.binding["source_result_ref"]=d.last["operation_result_ref"]
            d.binding["operation_id"]="projection-step"
    elif op=="change_upstream":(d.root/"surface/notes.md").write_text("NOTES_MARKER NOTES_V2\n")
    elif op=="next_input":d.prepare("projection-v2")
    elif op=="next_from_saved_result":
        if d.last is None or not d.last.get("operation_result_ref"):raise InvalidEvidence("next fixture operation lacks actual saved result")
        d.binding["source_result_ref"]=d.last["operation_result_ref"];d.binding["operation_id"]=args["operation_id"]
    elif op=="project":d.drive({})
    elif op=="attempt_continue":d.drive({"operation_id":"op-limit-next"})
    elif op=="settle_series":
        d.record("series_observations",{"type":"terminal_frame_observed","result":d.last})
    elif op=="retrieve_full":
        if d.binding["operation_id"] not in d.accepted:
            admitted=d.invoke("accept")
            if admitted is None or admitted.get("error"):return
            d.accepted.add(d.binding["operation_id"])
        reply=d.invoke("export_read",{"read_ref":d.port("f","fixture_full_output_reference",authority=d.target["fixture_authority"])})
        if (reply.get("error") or {}).get("code")=="integrity_mismatch":return
        ref=reply["read_result_ref"];d.save("bytes:retrieved",read_reference(ref));d.record("complete_recalls",{"type":"complete_recall","reference":ref})
        retained=d.port("f","resolve_fixture_original",authority=d.target["fixture_authority"]);d.save("bytes:retained",read_reference(retained))
    elif op=="corrupt_recall":
        # Corrupt the selected immutable read fixture through a test-only storage fault port;
        # the protected original evidence copy remains outside the candidate writable domain.
        d.port("f","test_corrupt_fixture_read",same_size=args["same_size"],authority=d.target["fixture_authority"])
    elif op=="run_strategy":
        d.binding["strategy"]=args["harness"];d.prepare("strategy-"+args["harness"]);d.binding["operation_id"]="op-"+args["harness"];d.drive({})
    elif op=="save_valid_session":d.drive({"response":"complete-answer"})
    elif op=="corrupt_session":d.snapshot=d.port("x","test_fault_input",reference=d.snapshot,fault="append_complete_invalid_jsonl_line",authority=d.target["fixture_authority"])
    else:raise InvalidEvidence("unimplemented trusted collector action "+op)
