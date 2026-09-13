"""Read original tool R/X/F facts and apply scoped host callbacks; no new ledger."""
import copy
import json
from pathlib import Path
from lore_control.values import decode, encode, ControlError
from lore_execution.errors import require
from lore_execution.journal import canonical, digest
from lore_execution.ordinary_sources import file_object
from lore_files.util import identity


class ToolFacts:
    def _row(self, eid, binding=None):
        with self.control._lock:
            raw=self.control.db.execute("SELECT * FROM requests WHERE id=?",(eid,)).fetchone()
            if raw is None:return None
            row=self.control._request_value(raw)
            self.control._authorize(self.principal,row["namespace"])
        require(row["principal"]==self.principal and row["namespace"]==self.plans.host["namespace"]
                and row["kind"]=="execution" and row["payload"]["plan"]["request"]["execution_id"]==eid,
                "UNAUTHORIZED","original tool facility scope differs")
        if binding is not None:require(row["payload"]["binding"]==binding,"UNAUTHORIZED","tool query binding differs")
        return row

    def _record(self, row):
        plan=row["payload"]["plan"]
        path=self.execution.journal.root/digest(row["id"].encode())/"record.json"
        record=json.loads(file_object(path)[1]) if path.exists() else None
        require(record is not None and record["request"]==plan["request"] and record["authority"]==plan["authority"],
                "UNAUTHORIZED","original X execution does not match accepted R plan")
        self.execution.node_profile.authorize(record["request"],plan["authority"],"query")
        require(record["binding"]["request_digest"]==digest(canonical(plan["request"])),"UNAUTHORIZED","original X digest differs")
        return record

    def _result_ref(self, row):
        record=self._record(row);plan=row["payload"]["plan"]
        fact,data=file_object(Path(plan["directory"])/"original-X-stopped.json")
        response=json.loads(data);b=record["binding"]
        require(response["binding"]==b and response["result"]["execution_state"]=="STOPPED"
                and response["result"]["output_state"]=="COMPLETE"
                and type(response["result"].get("exit_code")) is int
                and type(record["result"].get("exit_code")) is int
                and response["result"]["exit_code"]==record["result"].get("exit_code")
                and all(response["artifacts"].get(k)==record["artifacts"].get(k) for k in ("checkpoint","stopped","stdout","stderr")),
                "UNAUTHORIZED","original stopped response differs from X owner")
        return dict(owner="X",execution_id=row["id"],object_generation=b["object_generation"],
                    request_digest=b["request_digest"],original_receipt={k:fact[k] for k in ("path","bytes","sha256")})

    def validate_stopped(self, ref, purpose, scope):
        row=self._row(scope["execution_id"])
        if row is None:return False
        plan=row["payload"]["plan"];record=self._record(row);b=record["binding"]
        wanted=dict(owner="X",execution_id=row["id"],generation=b["object_generation"],
                    original_stopped_ref=record["artifacts"]["stopped"],original_execution_ref=self._result_ref(row))
        if ref!=wanted or purpose!="stopped" or scope["resource"]!=plan["resource"] or scope["base_ref"]!=plan["base_ref"] or scope["generation"]!=b["object_generation"]:return False
        proof=json.loads(self.execution.journal.read(record["artifacts"]["stopped"],8388608))
        cp=record["artifacts"]["checkpoint"]
        require(proof["execution_id"]==row["id"] and proof["object_generation"]==b["object_generation"]
                and proof["container_id"]==b["container_id"] and proof["exec_id"]==b["exec_id"]
                and proof["target_id"]==plan["resource"]["id"] and proof["domain"]==plan["request"]["domain"]
                and proof["binding_generation"]==plan["resource"]["revision"]
                and proof["base_version"]==plan["request"]["base_version"] and proof["prepared_ref"]==cp
                and proof["engine_state"] is not None and proof["engine_state"]["Running"] is False,
                "UNAUTHORIZED","original X stop/target/base proof differs")
        self.execution.journal.read(cp,8388608)
        if not record.get("released"):
            actual=self.execution.engine.inspect(b["container_id"])
            require(actual is not None and actual["State"]["Running"] is False,"UNAUTHORIZED","original X has not actually stopped")
        return True

    def _source(self,row):
        record=self._record(row)
        return dict(owner="trusted-Runtime-original-X-transport",original_execution_ref=self._result_ref(row),
                    archive_ref=record["artifacts"]["checkpoint"],stopped_ref=record["artifacts"]["stopped"])

    def _stop(self,row):
        record=self._record(row)
        return dict(owner="X",execution_id=row["id"],generation=record["binding"]["object_generation"],
                    original_stopped_ref=record["artifacts"]["stopped"],original_execution_ref=self._result_ref(row))

    def _binding(self,plan):
        r=plan["resource"]
        return dict(resource_id=r["id"],domain=r["kind"],path=r["path"],root={k:r[k] for k in ("dev","ino")},
                    revision=r["revision"],authorization=self.plans.host["authorization"])

    def _context_row(self,context):
        rid=context.get("request_id","")
        for prefix in ("tool-import-","tool-materialize-","tool-install-"):
            if rid.startswith(prefix):return self._row(rid[len(prefix):])
        return None

    def file_reference(self,ref,purpose,context):
        if purpose!="source" or context.get("operation")!="import_archive":return False
        row=self._context_row(context)
        if row is None:return False
        plan=row["payload"]["plan"];source=self._source(row);cp=source["archive_ref"]
        if ref!=source or context["source_ref"]!=source or context["binding"]!=self._binding(plan) or context["base_ref"]!=plan["base_ref"]:return False
        raw=self.execution.journal.read(cp,8388608)
        if context["archive"]!=dict(path=cp["path"],bytes=len(raw),sha256=digest(raw)) or context["actual_root"]!=plan["F"]["materialized"]["root"] or context["profile"]!="host-v1":return False
        scope=dict(resource=plan["resource"],base_ref=plan["base_ref"],execution_id=row["id"],generation=cp["object_generation"])
        return self.stopped_validator(self._stop(row),"stopped",scope) is True

    def file_authorization(self,ref,purpose,context):
        if ref!=self.plans.host["authorization"]:return False
        row=self._context_row(context)
        if row is None:return False
        plan=row["payload"]["plan"]
        if purpose=="import_archive":return self.file_reference(context["source_ref"],"source",context)
        if purpose=="materialize":
            saved=self.files.journal.get("tool-import-"+row["id"])
            parent=Path(plan["directory"])
            return saved is not None and saved["state"]=="complete" and context["version_ref"]==saved["result"]["version_ref"] and context["target_path"]==str(parent/"staged") and context["target_parent"]==dict(path=str(parent),root=identity(parent)) and context["profile"]=="host-v1"
        if purpose=="install":
            return self.publication.file_reference(context["intent"]["intent_ref"],"intent",context) and self.publication.file_reference(context["stopped_ref"],"stop",context)
        return False

    def _publication(self,row,pub):
        plan=row["payload"]["plan"];intent=pub["R_intent"]
        require(intent["request_id"]=="tool-install-"+row["id"] and intent["execution_id"]==row["id"]
                and intent["resource_id"]==plan["resource"]["id"] and intent["base_ref"]==plan["base_ref"],
                "UNAUTHORIZED","publication belongs to another original tool")
        pair=self.publication._installation(intent["request_id"])
        require(pair is not None and pair[0]==intent and pair[1]==pub["installation_ref"]
                and pub["installation_ref"]["original_query"]==pub["F_query"],"UNAUTHORIZED","original R installation confirmation differs")
        f=self.files.journal.get(intent["request_id"])
        require(f is not None and f["state"] in ("intent","installed") and f["inputs"]["intent"]==pub["F_query"]["original_intent"]
                and f["inputs"]["stopped_ref"]==pub["F_query"]["stopped_ref"],"UNAUTHORIZED","original F installation differs")
        material,provenance=self.publication._materialization("tool-materialize-"+row["id"])
        require(provenance["source_ref"]==self._source(row) and provenance["base_ref"]==plan["base_ref"]
                and material["version_ref"]==pub["F_query"]["version_ref"],"UNAUTHORIZED","original F import source differs")
        with self.control._lock:
            released=self.control.db.execute("SELECT * FROM releases WHERE resource_id=? AND execution_id=?",(intent["resource_id"],row["id"])).fetchone()
        require(released is not None and decode(released["binding_json"])==dict(stopped_ref=pub["F_query"]["stopped_ref"],published_ref=pub["installation_ref"])
                and decode(released["holder_json"])==dict(resource_id=intent["resource_id"],execution_id=row["id"],base_ref=plan["base_ref"])
                and pub["release"]==dict(resource_id=intent["resource_id"],execution_id=row["id"],released=True),
                "UNAUTHORIZED","original writer release missing/different")
        reg=pub["registration"];old=plan["resource"]
        require(reg==dict(old,revision=old["revision"]+1,**pub["F_query"]["current_root"]),
                "UNAUTHORIZED","original published registration projection differs")
        return copy.deepcopy(pub)

    def control_reference(self,ref,purpose,expected):
        if purpose!="receipt" or type(ref) is not dict:return False
        row=self._row(expected["request_id"])
        if row is None or any(ref.get(k)!=v for k,v in expected.items()) or ref.get("outcome")!="positive":return False
        f=ref["facility_ref"];record=self._record(row)
        require(f["kind"]=="ordinary_tool" and f["owner"]=="X" and f["execution_id"]==row["id"]
                and f["binding"]==row["payload"]["binding"] and f["frame"]==row["payload"]["frame"]
                and f["result_ref"]==self._result_ref(row) and f["original_stdout_ref"]==record["artifacts"]["stdout"]
                and f["stdout_ref"]==self.stdout_reference(record["artifacts"]["stdout"])
                and record.get("released") is True,"UNAUTHORIZED","tool original complete receipts differ")
        self._publication(row,f["publication_ref"])
        fact,data=file_object(Path(row["payload"]["plan"]["directory"])/"original-X-released.json")
        release=json.loads(data)
        require(f["original_release_response"]==release and release["binding"]==record["binding"]
                and release["result"]["execution_state"]=="STOPPED","UNAUTHORIZED","original X release differs")
        self.execution.journal.read(f["original_stdout_ref"],65536)
        require(all(x.get("status") in ("CONFIRMED","REJECTED") for x in f.get("event_receipts",[])),"UNAUTHORIZED","unknown event cannot confirm tool")
        return True

    def validate_publication(self,publication_ref,binding):
        row=self._row(publication_ref["R_intent"]["execution_id"],binding)
        require(row is not None and row["phase"]=="confirmed","UNAUTHORIZED","tool has no original confirmed receipt")
        require(row["receipt_ref"]["facility_ref"]["publication_ref"]==publication_ref,"UNAUTHORIZED","publication differs from original tool receipt")
        expected={k:row["receipt_ref"][k] for k in ("request_id","namespace","source","delivery_owner","request_digest")}
        require(self.control_reference(row["receipt_ref"],"receipt",expected),"UNAUTHORIZED","tool receipt invalid")
        return self._publication(row,publication_ref)

    def resolve_tool_source(self,effect_id,binding,publication_ref):
        row=self._row(effect_id,binding);require(row is not None,"UNAUTHORIZED","tool facility missing")
        self._publication(row,publication_ref);plan=row["payload"]["plan"];base=plan["F"]["bundle"]
        ref,data=file_object(base["archive_path"])
        require(digest(data)==plan["base_ref"]["archive_sha256"],"UNAUTHORIZED","original base archive differs")
        return dict(principal=self.principal,namespace=row["namespace"],domain=plan["request"]["domain"],
                    emit_allowed=plan["request"]["domain"]=="runtime",execution_id=effect_id,effect_id=effect_id,
                    binding=copy.deepcopy(binding),frame=copy.deepcopy(row["payload"]["frame"]),
                    base_archive_ref={k:ref[k] for k in ("path","bytes","sha256")},
                    output_archive_ref=self._record(row)["artifacts"]["checkpoint"],publication_ref=copy.deepcopy(publication_ref))
