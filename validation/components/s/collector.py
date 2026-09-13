"""Executable trusted S test driver. Actual X duplex + F/R ports required.
Creates real fixtures; sends only requests to S, never assertions/case IDs.
"""
from pathlib import Path
import argparse,base64,copy,hashlib,json,os,time
from physical_witness import start_witness
from context_fixtures import long_log,write_materials,retrieval_script
from live_ports import JsonPort,ExecutionChannel,MissingDependency,InvalidEvidence,load_target,read_reference,original_session_from_archive
ROOT=Path(__file__).resolve().parents[3]
def sha(data):return hashlib.sha256(data).hexdigest()
class CaseDriver:
    def __init__(self,case,target,root):
        self.case=case;self.target=target;self.root=root;root.mkdir()
        self.ports={name:JsonPort(target[name+"_command"],root/(name+"-port.jsonl")) for name in ("x","f")}
        self.journals={};self.artifacts={};self.snapshot=None;self.raw=None;self.env=None;self.calls=0;self.completed=0
        self.transport_receipts={};self.accepted=set();self.bootstrap_tool_marker=False;self.response="complete-answer";self.fault=None;self.recovery=False;self.last=None;self.decision=None
        self.binding={"session_id":case["setup"]["session_id"],"operation_id":"op-1","harness_ref":None,"input_ref":None,"source_result_ref":None,"capability_ref":None}
        for name in ("surface","workspace","input","originals"):(root/name).mkdir()
        self.prepare("projection-v1")
    def port(self,name,method,**params):return self.ports[name].call(method,params)
    def record(self,name,row):self.journals.setdefault(name,[]).append(row)
    def save(self,label,data):
        p=self.root/(label.replace(":","-")+".raw")
        with p.open("wb") as f:f.write(data);f.flush();os.fsync(f.fileno())
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        self.artifacts[label]={"path":str(p.relative_to(self.root.parent)),"sha256":sha(data),"origin":"trusted_external_collector"}
    def prepare(self,version):
        s=self.root/"surface";i=self.root/"input";w=self.root/"workspace"
        note="NOTES_V2" if version=="projection-v2" else "NOTES_V1"
        strategy="STRATEGY_TWO" if version=="strategy-h2" else "STRATEGY_ONE"
        (s/"template.md").write_text("GOAL_MARKER_雪 "+strategy+"\n{{notes.md}}\n")
        (s/"notes.md").write_text("NOTES_MARKER "+note+"\n")
        (i/"events.jsonl").write_text(json.dumps({"id":"event-1","source":"fixture-E","type":"EVENT_MARKER"})+"\n")
        (i/"feedback.txt").write_text("SAVED_TOOL_MARKER\n");(w/"data.json").write_text("[2,3,5]\n")
        if "long-output" in version:
            raw=long_log();(self.root/"originals/log").write_bytes(raw)
            self.save("bytes:original",raw);(i/"feedback.txt").write_text("UNKNOWN_EXEC_17\n")
        if version=="lazy-materials":
            selected,diff=write_materials(w)
            self.save("bytes:retrieval_selected",selected.read_bytes());self.save("bytes:retrieval_diff",diff.read_bytes())
            with (s/"notes.md").open("a") as f:f.write("Use the workspace ordinary Shell/Python at /workspace to locate catalog/area-*/REQUESTED_*.txt and requested changes in changes.patch.\n")
        # A trusted fixture port maps real ordinary files into its verified F profile.
        refs=self.port("f","prepare_fixture_input",surface=str(s),workspace=str(w),input_dir=str(i),originals=str(self.root/"originals"),version=version,authority=self.target["fixture_authority"])
        self.binding.update({k:refs[k] for k in ("input_ref","harness_ref","capability_ref")})
        if "long-output" in version:self.record("clip_source",{"type":"actual_immutable_source_reference","reference":refs["original_refs"]["log"]})
    def checkpoint(self,label,resume=True):
        c=self.port("x","checkpoint",**self.env,checkpoint_id="cp-"+str(self.calls)+"-"+label,purpose="original_session")
        self.raw=original_session_from_archive(c["prepared_artifact"])
        self.snapshot=c["original_session_snapshot_ref"]
        self.save("session:"+label,self.raw);self.frozen=True
        if resume:self.port("x","resume",**self.env,checkpoint_receipt=c["receipt"]);self.frozen=False
        self.checkpoint_receipt=c["receipt"]
        from oracle import pi_jsonl
        return pi_jsonl(self.raw)
    def original_target_preflights(self,original):
        op=self.binding["operation_id"];result=original["values"].get("pi.result",{}).get(op)
        if result is None:return
        entries={row["id"]:row for row in original["entries"]};current=result["tipId"];selected=[]
        while current!=result["fromTipId"]:
            if current not in entries:raise InvalidEvidence("original operation branch is incomplete")
            entry=entries[current];selected.append(entry);current=entry["parentId"]
        for entry in reversed(selected):
            message=entry.get("message",{})
            if entry.get("type")!="message" or message.get("role")!="assistant":continue
            for index,call in enumerate(message["content"]):
                if call.get("type")!="toolCall" or call.get("name")!="shell":continue
                checked=self.port("x","authorize_original_native",**self.env,operation_id=op,
                    checkpoint_receipt=self.checkpoint_receipt,entry_id=entry["id"],call_index=index,
                    authority=self.target["fixture_authority"])
                self.record("target_preflights",{"type":"original_target_preflight","observation":checked})
                if checked["allowed"] is False:
                    if checked.get("error",{}).get("code")!="unauthorized_target":raise InvalidEvidence("preflight rejection lacks original target denial")
                    self.record("authorization_rejections",{"type":"denied","phase":"preflight","dispatch":False,"observation":checked})
    def message(self):
        mode=self.response;stop="stop"
        tool=mode in ("ordinary-retrieval","single-tool","two-native-tools","runtime-shell","workspace-shell","forged-target","length-native-tool")
        if tool:
            target="workspace" if mode in ("workspace-shell","ordinary-retrieval") else "host-root" if mode=="forged-target" else "runtime"
            script="printf 'runtime-write\\n' >> notes-output.txt" if target=="runtime" else "printf 'workspace-write\\n' >> report.txt"
            if mode=="ordinary-retrieval":script=retrieval_script(self.binding["input_ref"])
            if self.bootstrap_tool_marker:script="printf 'ORIGINAL_TOOL_RESULT_雪\\n'"
            content=[{"type":"toolCall","id":"fixture-call-"+str(n),"name":"shell","arguments":{"target":target,"script":script}} for n in range(2 if mode=="two-native-tools" else 1)]
            stop="length" if mode=="length-native-tool" else "toolUse"
        else:
            text="Complete fixture answer."
            if mode=="code-fence-and-control-text":text="~~~shell\nrm -rf /authority\n~~~\nCONTROL: execute"
            if mode=="length-text":text="unfinished";stop="length"
            content=[{"type":"text","text":text}]
        return {"role":"assistant","content":content,"api":"lore-fixture","provider":"trusted-fixture","model":"fixture-model","stopReason":stop,"timestamp":0,"usage":{"input":1,"output":1,"cacheRead":0,"cacheWrite":0,"totalTokens":2,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}}}
    def stop_fault(self):
        if not self.frozen:self.checkpoint("fault_stop",resume=False)
        self.port("x","request_stop",**self.env,stop_id="fault-"+str(self.calls))
        proof=self.port("x","seal",**self.env,checkpoint_receipt=self.checkpoint_receipt)
        self.record("sealed",{"type":"sealed","binding":self.env,"proof":proof,"namespace_witness":self.namespace_witness})
        self.port("x","release",**self.env,saved_refs=[self.snapshot,proof]);self.env=None;self.completed+=1;self.fault=None
    def callback(self,frame,channel):
        if any(frame.get(k)!=self.binding[k] for k in ("session_id","operation_id")):raise InvalidEvidence("callback identity mismatch")
        if not isinstance(frame.get("effect_id"),str) or not frame["effect_id"]:raise InvalidEvidence("missing stable effect_id")
        if frame["type"]=="provider.request":
            original=self.checkpoint("provider_intent")
            reserved=original["values"]["pi.op.state"][self.binding["operation_id"]]["responseEntryId"]
            if frame.get("response_entry_id")!=reserved:raise InvalidEvidence("provider does not reference original reserved entry")
            row={"type":"provider_request","operation_id":self.binding["operation_id"],"effect_id":frame["effect_id"],"payload":frame["payload"],"response_entry_id":reserved}
            self.record("provider",row);self.record("recovery_provider" if self.recovery else "provider_first" if len(self.journals["provider"])==1 else "provider_second",row)
            self.record("provider_h2" if self.binding.get("strategy")=="h2" else "provider_h1",row)
            reply=self.message();self.save("bytes:wire_before",json.dumps(reply,ensure_ascii=False).encode())
            if self.fault=="wire_saved_before_pi_commit":
                self.transport_receipts[frame["effect_id"]]={"effect_id":frame["effect_id"],"response_entry_id":reserved,"wire_ref":{"path":str(self.root/"bytes-wire_before.raw"),"sha256":sha(json.dumps(reply,ensure_ascii=False).encode()),"bytes":len(json.dumps(reply,ensure_ascii=False).encode())}}
                (self.root/"transport-receipts.json").write_text(json.dumps(self.transport_receipts,ensure_ascii=False,indent=2))
                self.stop_fault();return False
            channel.write({"type":"provider.reply","effect_id":frame["effect_id"],"response_entry_id":reserved,"message":reply})
        elif frame["type"]=="tool.request":
            original=self.checkpoint("tool_intent")
            calls=original["values"]["pi.op.state"][self.binding["operation_id"]].get("batch",{}).get("calls",[])
            if not any(c.get("resultEntryId")==frame.get("invocation_id") for c in calls):raise InvalidEvidence("tool identity absent from original intent")
            target=frame["request"]["target"]
            if target not in ("runtime","workspace"):
                self.record("authorization_rejections",{"type":"denied","target":target})
                channel.write({"type":"tool.reply","effect_id":frame["effect_id"],"error":{"code":"denied"}});return True
            request={"execution_id":frame["effect_id"],"invocation_id":frame["invocation_id"],"operation_id":self.binding["operation_id"],"source_result":frame["source_result_ref"],"harness_ref":self.binding["harness_ref"],"target":target,"script":frame["request"]["script"],"input_ref":self.binding["input_ref"],"profile":self.target["profile"]["tool_profiles"][target]}
            result=self.port("x","execute",request=request,authority=self.target["fixture_authority"])
            stdout_ref=self.port("x","resolve_result_stdout",original_result_ref=result["result_ref"],authority=self.target["fixture_authority"])
            stdout_raw=read_reference(stdout_ref)
            if self.bootstrap_tool_marker:self.save("bytes:bootstrap_tool_stdout",stdout_raw)
            if self.response=="ordinary-retrieval":
                from oracle import strict_json
                self.save("bytes:retrieval_stdout",stdout_raw);self.record("retrieval_output",{"type":"actual_original_tool_stdout","output":strict_json(stdout_raw),"result_ref":result["result_ref"]})
            self.record("tools",{"type":"tool_request","target":target,"effect_id":frame["effect_id"],"request":request})
            if self.recovery:self.record("recovery_tools",self.journals["tools"][-1])
            ref=self.port("f","read_fixture_effects",original_execution_ref=result["result_ref"],authority=self.target["fixture_authority"])
            for line in read_reference(ref).splitlines():self.record("effects",{"type":"actual_effect","bytes_b64":base64.b64encode(line).decode()})
            if self.fault=="effect_before_receipt":self.stop_fault();return False
            channel.write({"type":"tool.reply","effect_id":frame["effect_id"],"invocation_id":frame["invocation_id"],"result_ref":result["result_ref"],"stdout":{"data_b64":base64.b64encode(stdout_raw).decode(),"bytes":len(stdout_raw),"sha256":sha(stdout_raw)}})
        else:raise InvalidEvidence("unknown callback")
        return True
    def observe_result(self,frame):
        code=(frame.get("error") or {}).get("code")
        for codes,label,event in [(("conflict",),"conflicts","conflict"),(("session_corrupt",),"integrity_errors","integrity_error"),(("integrity_mismatch",),"recall_errors","integrity_mismatch")]:
            if code in codes:self.record(label,{"type":event,"frame":frame})
        if frame.get("decision_proposal"):
            proposal=frame["decision_proposal"]
            if proposal.get("successors") or proposal.get("continue"):
                self.record("continuation_proposals",{"type":"continue_proposal","proposal":proposal})
        boundary=frame.get("boundary_kind")
        if boundary=="answer_saved":
            row={"type":"answer_saved","frame":frame};self.record("accepted_finals",row)
            if self.recovery:self.record("recovery_finals",row)
        if boundary in ("paused_unknown","paused_reconciliation_required","stopped_limit"):self.record("pause_reasons",{"type":boundary,"frame":frame})
        return code
    def invoke(self,action,extra=None):
        self.calls+=1
        request={"protocol":"lore.s/1","action":action,"session_ref":self.snapshot or {"owner":"S","session_id":self.binding["session_id"]},**{k:v for k,v in self.binding.items() if k not in ("strategy","session_id")},**(extra or {})}
        started=self.port("x","execute",request={"execution_id":"s-test-"+str(self.calls),"target":"session","argv":self.target["sut_argv"],"input_ref":self.binding["input_ref"],"session_snapshot_ref":self.snapshot,"profile":self.target["profile"]["session_profile"],"session_scope":{"namespace":self.target["fixture_authority"]["namespace"],"surface_id":"fixture-surface","session_id":self.binding["session_id"],"session_generation":1},**{k:self.binding[k] for k in ("operation_id","harness_ref","capability_ref","source_result_ref")}},authority=self.target["fixture_authority"],io_mode="duplex")
        self.env=started["execution_binding"];self.frozen=False;self.namespace_witness=start_witness(self.env,self.root/("os-start-"+str(self.calls)),self.target["sut_argv"]);channel=ExecutionChannel(self.ports["x"],started["channel_binding"])
        channel.write(request);deadline=time.monotonic()+30;np=len(self.journals.get("provider",[]));nt=len(self.journals.get("tools",[]))
        while True:
            frame=channel.next_frame(deadline);self.record("frames",{"type":"received_frame","frame":frame})
            if frame.get("type") in ("effect.query","provider.query"):
                if frame.get("operation_id")!=self.binding["operation_id"] or frame.get("session_id")!=self.binding["session_id"]:raise InvalidEvidence("query escaped original scope")
                queried=self.transport_receipts.get(frame["effect_id"],{"status":"UNKNOWN"}) if frame["type"]=="provider.query" else self.port("x","query",execution_id=frame["effect_id"],authority=self.target["fixture_authority"])
                self.record("original_queries",{"type":"original_query","effect_id":frame["effect_id"],"response":queried})
                response={"error":{"code":"transport_unavailable"}} if getattr(self,"query_outage",False) else {"result":queried}
                channel.write({"type":"effect.query_reply","effect_id":frame["effect_id"],**response});continue
            if frame.get("type") in ("provider.request","tool.request"):
                if not self.callback(frame,channel):return None
                continue
            if frame.get("type")!="result" or frame.get("operation_id")!=self.binding["operation_id"]:raise InvalidEvidence("invalid terminal frame")
            if frame.get("read_result_ref"):
                frame["read_result_ref"]=self.port("x","resolve_session_read",**self.env,reference=frame["read_result_ref"])
            self.completed+=1;self.last=frame;code=self.observe_result(frame)
            channel.close()
            if code in ("session_corrupt","integrity_mismatch"):
                # Preserve the corrupt restore input; no claim a valid Session was exported.
                prepared=self.port("x","checkpoint",**self.env,checkpoint_id="rejected-input-evidence",purpose="raw_failed_input",reason=code)
                self.record("quarantine_retention",{"type":"unadmitted_original_retained","reason":code,"retained":prepared["retained_quarantine"]})
                self.checkpoint_receipt=prepared["receipt"];self.frozen=True
            else:
                original=self.checkpoint("accepted" if action=="accept" else "final",resume=False)
                if action=="drive":self.original_target_preflights(original)
            if action=="accept" and self.fault=="accepted_checkpoint_before_ack":
                from oracle import pi_jsonl
                original=pi_jsonl(self.raw)
                actual=original["values"].get("lore.s.binding",{}).get(self.binding["operation_id"])
                expected={k:v for k,v in self.binding.items() if k!="strategy"}
                if not isinstance(actual,dict) or any(k not in actual or actual[k]!=v for k,v in expected.items()):raise InvalidEvidence("original accepted Session lacks exact complete binding")
                self.record("accepted_binding_verifications",{"type":"original_binding_verified","binding":actual,"session_sha256":sha(self.raw)})
                self.save("session:accepted_before_ack_loss",self.raw)
                self.save("journal:lost_admission_acks",b"")
                recovery={"snapshot":self.snapshot,"binding":expected,"session_sha256":sha(self.raw)}
                path=self.root/"durable-admission-recovery.json"
                with path.open("w") as f:json.dump(recovery,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
                fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
                self.record("ack_loss_cuts",{"type":"accepted_checkpoint_before_ack","binding":self.env,"recovery_file":str(path),"session_sha256":sha(self.raw)})
                # The raw S result is provisional: the external durable admission
                # ACK is deliberately never delivered at this exact cut.
                self.stop_fault();return None
            proof=self.port("x","seal",**self.env,checkpoint_receipt=self.checkpoint_receipt)
            self.record("sealed",{"type":"sealed","binding":self.env,"proof":proof,"namespace_witness":self.namespace_witness})
            self.port("x","release",**self.env,saved_refs=[self.snapshot,proof]);self.env=None
            if action=="accept" and not code:self.record("admission_acks",{"type":"durable_admission_ack","operation_id":self.binding["operation_id"],"snapshot":self.snapshot})
            if action=="query":
                for row in self.journals.get("provider",[])[np:]:self.record("query_provider",row)
                for row in self.journals.get("tools",[])[nt:]:self.record("query_tools",row)
            return frame
    def drive(self,args):
        if "operation_id" in args:self.binding["operation_id"]=args["operation_id"]
        self.response=args.get("response",self.response);self.fault=args.get("fault")
        if "budget_steps" in args:
            self.binding["capability_ref"]=self.port("f","prepare_fixture_limit_binding",original=self.binding["capability_ref"],limits={"max_steps":args["budget_steps"]},authority=self.target["fixture_authority"])
        if self.binding["operation_id"] not in self.accepted:
            admitted=self.invoke("accept")
            if admitted is None or admitted.get("error"):return admitted
            self.accepted.add(self.binding["operation_id"])
        return self.invoke("drive")
    def finish(self,sources):
        if not self.completed:raise InvalidEvidence("zero actual S invocation/cut")
        self.journals["provider_current"]=[row for row in self.journals.get("provider",[]) if row["operation_id"]==self.binding["operation_id"]]
        for label in sources:
            if label in self.artifacts:continue
            role,name=label.split(":",1)
            if role=="journal":self.save(label,("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in self.journals.get(name,[]))).encode())
            elif role=="bytes" and name in ("runtime_target","workspace_target"):
                ref=self.port("f","resolve_fixture_output",target="runtime" if name=="runtime_target" else "workspace",authority=self.target["fixture_authority"])
                self.save(label,read_reference(ref))
            else:raise InvalidEvidence("missing collected raw source "+label)
        return {label:self.artifacts[label] for label in sources}
    def cleanup(self):
        try:
            if self.env is not None:
                self.port("x","request_stop",**self.env,stop_id="collector-cleanup")
                self.port("x","test_cleanup",**self.env,authority=self.target["fixture_authority"])
                self.env=None
        finally:
            self.port("x","close_fixture",authority=self.target["fixture_authority"])

from collector_actions import perform_action
def main():
    p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--target",type=Path,default=Path(os.environ.get("LORE_S_TARGET","validation/components/s/target.json")))
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True);result={"scope":"LIVE_S_COLLECTOR","status":"MISSING","case_evidence":{}}
    try:
        target=load_target(args.target);plan=json.loads(args.plan.read_text());specpath=ROOT/"design/g3/s/cases.json";spec=json.loads(specpath.read_text())
        if plan["cases_sha256"]!=sha(specpath.read_bytes()):raise InvalidEvidence("action plan drift")
        expected_ids={c["id"] for c in spec["cases"]}
        if {c["id"] for c in plan["cases"]}!=expected_ids or len(plan["cases"])!=len(expected_ids):raise InvalidEvidence("missing/duplicate planned case")
        by_id={c["id"]:c for c in spec["cases"]}
        for case in plan["cases"]:
            d=CaseDriver(case,target,args.output/case["id"])
            try:
                for action in case["actions"]:perform_action(d,action["op"],action["args"])
                sources=set(by_id[case["id"]]["evidence_required"])
                for assertion in by_id[case["id"]]["assertions"]:
                    if "other" in assertion:sources.add(assertion["other"]["source"])
                result["case_evidence"][case["id"]]=d.finish(sorted(sources))
            finally:d.cleanup()
        bundle={"scope":"TRUSTED_COLLECTOR_OUTPUT","cases_sha256":plan["cases_sha256"],"case_evidence":result["case_evidence"]}
        (args.output/"bundle.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+"\n");result["status"]="COLLECTED";code=0
    except MissingDependency as error:result["error"]=str(error);code=2
    except Exception as error:result["status"]="INVALID";result["error"]=repr(error);code=2
    (args.output/"live-collection.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"status":result["status"],"error":result.get("error")}));return code
if __name__=="__main__":raise SystemExit(main())
