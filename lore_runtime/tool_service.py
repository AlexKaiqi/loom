"""Single ordinary tool facility: original R responsibility, X execution, F publication."""
import copy
import json
from pathlib import Path
from lore_control.values import ControlError, encode
from lore_execution.errors import require
from lore_execution.journal import canonical, digest
from .session_plan_files import json_file
from .tool_facts import ToolFacts


class ToolService(ToolFacts):
    def __init__(self,control,files,execution,publication,plans,stopped_validator,emission_submit=None):
        require(callable(stopped_validator),"UNAUTHORIZED","trusted original stop validator required")
        self.control,self.files,self.execution,self.publication,self.plans=control,files,execution,publication,plans
        self.principal=plans.host["principal"]
        self.stopped_validator,self.emission_submit=stopped_validator,emission_submit

    @staticmethod
    def stdout_reference(original):
        return dict(path=original["path"],sha256=original["sha256"],bytes=original["size"])

    @staticmethod
    def _unknown(eid,fresh=False,error=None):
        return dict(status="UNKNOWN",fresh=fresh,effect_id=eid,error=None if error is None else dict(type=type(error).__name__,code=getattr(error,"code",None),message=str(error)))

    def query(self,effect_id,binding):
        row=self._row(effect_id,binding)
        if row is None:return dict(status="NOT_FOUND",fresh=False,effect_id=effect_id)
        if row["phase"]!="confirmed":return self._unknown(effect_id)
        receipt=row["receipt_ref"]
        expected={k:receipt[k] for k in ("request_id","namespace","source","delivery_owner","request_digest")}
        require(self.control_reference(receipt,"receipt",expected),"UNAUTHORIZED","original tool receipt invalid")
        f=receipt["facility_ref"];record=self._record(row);code=record["result"]["exit_code"]
        require(type(code) is int and 0<=code<=255,"INCOMPLETE_OBSERVATION","original tool exit status unknown")
        return copy.deepcopy(dict(status="RECEIVED",fresh=False,effect_id=effect_id,
            exit_code=code,stderr_ref=self.stdout_reference(record["artifacts"]["stderr"]),
            **{k:f[k] for k in ("result_ref","stdout_ref","publication_ref","event_receipts")}))

    def execute(self,binding,frame,original_session_snapshot_ref):
        binding,frame,envelope=copy.deepcopy((binding,frame,original_session_snapshot_ref))
        eid=frame["effect_id"]
        old=self._row(eid,binding)
        if old is not None:
            require(old["payload"]["frame"]==frame and old["payload"]["original_session_snapshot_ref"]==envelope,
                    "UNAUTHORIZED","original tool identity/content changed")
            return self.query(eid,binding)
        plan=self.plans.prepare(binding,frame,envelope)
        request=dict(id=eid,namespace=plan["resource"]["namespace"],kind="execution",
                     payload=dict(parent_id=binding["operation_id"],binding=binding,frame=frame,
                                  original_session_snapshot_ref=envelope,plan=plan))
        self.control.accept(self.principal,request)
        # R must retain this exact resource before any executable grant or Engine object exists.
        try:
            self.control.acquire(plan["resource"]["id"],eid,plan["base_ref"])
            self.plans.grant(plan)
            dispatched=self.control.mark_dispatched(self.principal,eid,"X")
            if not dispatched["fresh"]:return self.query(eid,binding)
            self.execution.execute(plan["request"],plan["authority"])
            # 2026-09-15 (amendment-linux-browser): the await window follows the
            # plan deadline (browser tools launch chromium); the default python
            # path keeps the historical 20s (its plan deadline is 20s).
            exited=self.execution.await_exit(eid,plan["authority"],
                timeout=min(120, plan["request"]["budgets"]["deadline_seconds"]))
            require(exited["result"]["output_state"]=="COMPLETE","INCOMPLETE_OBSERVATION","ordinary tool output unresolved")
            cp=self.execution.checkpoint(eid,plan["authority"],"s-tool-final","ordinary_tool_result")["artifacts"]["checkpoint"]
            stopped=self.execution.seal(eid,plan["authority"],cp)
            json_file(Path(plan["directory"])/"original-X-stopped.json",stopped)
            return self._finish(self._row(eid,binding),fresh=True)
        except Exception as exc:
            return self._unknown(eid,True,exc)

    def reconcile(self,effect_id,binding):
        row=self._row(effect_id,binding)
        if row is None:return dict(status="NOT_FOUND",fresh=False,effect_id=effect_id)
        if row["phase"]=="confirmed":return self.query(effect_id,binding)
        # Only already sealed original effects can advance publication. Never redispatch.
        try:
            record=self._record(row)
            require(record["result"]["execution_state"]=="STOPPED" and "stopped" in record["artifacts"]
                    and record["result"]["output_state"]=="COMPLETE","INCOMPLETE_OBSERVATION","original tool not durably sealed")
            self._result_ref(row)
            return self._finish(row,fresh=False)
        except Exception as exc:return self._unknown(effect_id,False,exc)

    def _events(self,row,pub):
        plan=row["payload"]["plan"]
        if plan["request"]["domain"]!="runtime":return []
        # The reserved application file remains in the complete original F archive.
        _,base,base_contents=self.files.versions.load(plan["base_ref"])
        _,new,new_contents=self.files.versions.load(pub["F_query"]["version_ref"])
        name=".lore/emit-requests.jsonl"
        for tree in (base,new):
            require(name not in tree["entries"] or tree["entries"][name]["kind"]=="file",
                    "INVALID_REQUEST","emit source is not an ordinary file")
        old,data=base_contents.get(name,b""),new_contents.get(name,b"")
        require(data.startswith(old) and (not old or old.endswith(b"\n")),"INVALID_REQUEST","emit source rewrote original prefix")
        if data==old:return []
        require(callable(self.emission_submit),"INCOMPLETE_OBSERVATION","runtime emit delta lacks trusted submitter")
        result=self.emission_submit(row["id"],copy.deepcopy(row["payload"]["binding"]),copy.deepcopy(pub))
        require(type(result) is list and all(type(v) is dict and v.get("status") in ("CONFIRMED","REJECTED") for v in result),
                "INCOMPLETE_OBSERVATION","event delivery remains unknown")
        return result

    def _finish(self,row,fresh):
        eid=row["id"];plan=row["payload"]["plan"];record=self._record(row)
        cp=record["artifacts"]["checkpoint"];result_ref=self._result_ref(row)
        import_id="tool-import-"+eid;material_id="tool-materialize-"+eid;install_id="tool-install-"+eid
        saved=self.files.journal.get(import_id)
        if saved is None:
            bundle=self.files.import_archive(import_id,self._binding(plan),cp["path"],self._source(row),plan["base_ref"],"host-v1")
        else:
            require(saved["state"]=="complete" and saved["inputs"]["source_ref"]==self._source(row)
                    and saved["inputs"]["binding"]==self._binding(plan) and saved["inputs"]["base_ref"]==plan["base_ref"],
                    "UNAUTHORIZED","original F import changed")
            bundle=saved["result"];self.files.versions.validate_bundle(bundle)
        # Once an install exists its original stage may already be the retired directory.
        if self.files.journal.get(material_id) is None:
            self.files.materialize(material_id,bundle["version_ref"],str(Path(plan["directory"])/"staged"),self.plans.host["authorization"])
        pub=self.publication.publish(self.principal,row["namespace"],install_id,plan["resource"],plan["base_ref"],material_id,self._stop(row),self.plans.host["authorization"])
        # F/R publication is confirmed; X retains the original archive on release.
        # Event validation can reject the ordinary outbox without retaining a sandbox.
        released=self.execution.release(eid,plan["authority"])
        json_file(Path(plan["directory"])/"original-X-released.json",released)
        events=self._events(row,pub)
        facility=dict(owner="X",kind="ordinary_tool",execution_id=eid,binding=row["payload"]["binding"],frame=row["payload"]["frame"],
                      result_ref=result_ref,stdout_ref=self.stdout_reference(record["artifacts"]["stdout"]),
                      original_stdout_ref=record["artifacts"]["stdout"],publication_ref=pub,
                      original_release_response=released,event_receipts=events)
        original={k:row[k] for k in ("principal","id","namespace","kind","payload")}
        receipt=dict(request_id=eid,namespace=row["namespace"],source=self.principal,delivery_owner="X",
                     request_digest=digest(encode(original).encode()),outcome="positive",facility_ref=facility)
        self.control.confirm_delivery(self.principal,eid,receipt)
        return dict(self.query(eid,row["payload"]["binding"]),fresh=fresh)
