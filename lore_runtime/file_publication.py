"""Publish an original F materialization through the existing R/F installation records."""
import json
from pathlib import Path

from lore_control.values import decode, encode, fail, same
from lore_files.errors import FileError
from lore_files.util import identity, ordinary_path


def detached(value):
    return decode(encode(value))


def require(value, message):
    if not value:
        fail("reference_invalid", message)


class FilePublication:
    """Host-only adapter. The supplied checkers remain the authority for original refs."""

    def __init__(self, control, files, stopped_validator):
        require(callable(stopped_validator), "original X stopped validator required")
        self.control, self.files = control, files
        self.stopped_validator = stopped_validator

    def _installation(self, install_id):
        # Read the owner's original row, including while its own reference callback runs.
        # Starting a nested SQLite transaction here would be incorrect.
        with self.control._lock:
            row = self.control.db.execute(
                "SELECT binding_json,installation_ref_json FROM installations WHERE request_id=?",
                (install_id,),
            ).fetchone()
            return None if row is None else (decode(row[0]), decode(row[1]))

    def _materialization(self, request_id):
        record = self.files.journal.get(request_id)
        require(record is not None and record.get("state") == "complete", "original F materialization absent")
        require(record["inputs"].get("operation") == "materialize", "not an original materialize request")
        materialized = detached(record["result"])
        require(materialized["path"] == record["inputs"]["target_path"] and
                same(materialized["version_ref"], record["inputs"]["version_ref"]),
                "materialization differs from its original request")
        version = materialized["version_ref"]
        self.files.versions.load(version)
        provenance = json.loads(self.files.versions.git("cat-file", "blob", version["git_ref"] + ":provenance.json"))
        return materialized, provenance

    def _scope(self, call, materialized, provenance):
        resource, base = call["resource"], call["base_ref"]
        require(resource["namespace"] == call["namespace"] and resource["kind"] in ("surface", "workspace"), "original resource namespace/domain differs")
        for version in (base, materialized["version_ref"]):
            require(version["resource_id"] == resource["id"] and version["domain"] == resource["kind"], "version resource/domain differs")
        self.files.versions.load(base)
        require(provenance.get("operation") == "import_archive" and same(provenance.get("base_ref"), base), "output is not the original import of this base")
        require(provenance["binding"]["resource_id"] == resource["id"] and provenance["binding"]["domain"] == resource["kind"], "import provenance scope differs")
        # Identity comes from the source already accepted by F, not the offered stop ref.
        source = provenance["source_ref"]
        original_execution = source.get("original_execution_ref", source.get("original_binding"))
        require(type(original_execution) is dict, "import lacks its original execution reference")
        execution_id = original_execution.get("execution_id")
        generation = original_execution.get("object_generation")
        require(type(execution_id) is str and type(generation) is int and generation > 0, "original execution identity absent")
        require(call["stopped_ref"].get("execution_id") == execution_id and call["stopped_ref"].get("generation") == generation, "stop execution/generation differs from F source")
        return dict(principal=call["principal"], namespace=call["namespace"], resource=resource,
                    base_ref=base, execution_id=execution_id, generation=generation,
                    materialization_request_id=call["materialization_request_id"],
                    materialization=materialized, provenance=provenance)

    def _validate_stop(self, call, scope):
        try:
            valid = self.stopped_validator(detached(call["stopped_ref"]), "stopped", detached(scope))
        except Exception as exc:
            fail("reference_invalid", "original stop authority unavailable: " + str(exc))
        require(valid is True, "original X stop or complete publication association invalid")

    @staticmethod
    def _intent_ref(install_id):
        return dict(owner="R", kind="installation", id=install_id)

    def _stage(self, call):
        materialized, provenance = self._materialization(call["materialization_request_id"])
        scope = self._scope(call, materialized, provenance)
        self._validate_stop(call, scope)
        stage = dict(owner="F", kind="materialized", request_id=call["materialization_request_id"],
                     root=dict(path=materialized["path"], **materialized["root"]),
                     materialization=materialized, version_ref=materialized["version_ref"],
                     publication=call)
        return stage, scope

    def _stop_projection(self, intent):
        stage = intent["staged_ref"]
        call = stage["publication"]
        materialized, provenance = self._materialization(stage["request_id"])
        scope = self._scope(call, materialized, provenance)
        self._validate_stop(call, scope)
        return dict(owner="X", execution_id=scope["execution_id"], generation=scope["generation"],
                    original_stopped_ref=call["stopped_ref"],
                    publication_intent_ref=self._intent_ref(intent["request_id"]))

    def _f_intent(self, intent):
        stage, old = intent["staged_ref"], intent["old_root"]
        call = stage["publication"]
        binding = dict(resource_id=intent["resource_id"], domain=call["resource"]["kind"],
                       path=old["path"], root={k: old[k] for k in ("dev", "ino")},
                       revision=intent["expected_revision"], authorization=call["authorization"])
        stop = self._stop_projection(intent)
        return dict(resource_id=intent["resource_id"], domain=binding["domain"], binding=binding,
                    staged_path=stage["root"]["path"], staged_root={k: stage["root"][k] for k in ("dev", "ino")},
                    version_ref=stage["version_ref"], base_ref=intent["base_ref"],
                    execution_id=intent["execution_id"], generation=stop["generation"],
                    intent_ref=self._intent_ref(intent["request_id"]))

    def _projection(self, intent, query):
        require(same(query["original_intent"], self._f_intent(intent)) and
                same(query["stopped_ref"], self._stop_projection(intent)) and
                query["request_id"] == intent["request_id"], "actual F installation differs from R original intent")
        if query["status"] != "installed_pending_confirmation" or query.get("observation_error") is not None:
            raise FileError("PUBLICATION_UNKNOWN", "original F query does not establish installation: " + query["status"])
        old, stage = intent["old_root"], intent["staged_root"]
        require(query["current_root"] == {k: stage[k] for k in ("dev", "ino")} and
                query["retired_root"] == {k: old[k] for k in ("dev", "ino")}, "actual original installation layout differs")
        return dict(owner="F", kind="installation", id=intent["request_id"], request_id=intent["request_id"],
                    status=query["status"], current=dict(path=old["path"], **query["current_root"]),
                    retired=dict(path=stage["path"], **query["retired_root"]),
                    version_ref=query["version_ref"], staged_ref=intent["staged_ref"],
                    stopped_ref=query["stopped_ref"], original_query=query)

    def file_reference(self, ref, purpose, context):
        if purpose not in ("intent", "stop") or context.get("operation") != "install":
            return False
        key = ref if purpose == "intent" else ref.get("publication_intent_ref", {})
        if key != self._intent_ref(context["request_id"]):
            return False
        pair = self._installation(key["id"])
        if pair is None:
            return False
        intent = pair[0]
        return same(context["intent"], self._f_intent(intent)) and same(context["stopped_ref"], self._stop_projection(intent))

    def control_reference(self, ref, purpose, expected):
        if purpose == "staged":
            if type(ref) is not dict or "publication" not in ref:
                return False
            stage, scope = self._stage(ref["publication"])
            association = dict(resource_id=scope["resource"]["id"], execution_id=scope["execution_id"], base_ref=scope["base_ref"])
            return same(stage, ref) and all(same(association.get(k), v) for k, v in expected.items()) and identity(ordinary_path(ref["root"]["path"])) == {k: ref["root"][k] for k in ("dev", "ino")}
        if purpose == "stopped":
            key = ref.get("publication_intent_ref", {})
        elif purpose in ("installation", "published"):
            key = self._intent_ref(ref.get("request_id"))
        else:
            return False
        pair = self._installation(key.get("id"))
        if pair is None:
            return False
        intent = pair[0]
        association = {k: intent[k] for k in ("request_id", "resource_id", "execution_id", "base_ref")}
        association["version_ref"] = intent["staged_ref"]
        if not all(same(association.get(k), v) for k, v in expected.items()):
            return False
        if purpose == "stopped":
            return same(ref, self._stop_projection(intent))
        return same(ref, self._projection(intent, self.files.query_install(intent["request_id"])))

    def publish(self, principal, namespace, install_id, resource, base_ref,
                materialization_request_id, stopped_ref, authorization):
        call = detached(dict(principal=principal, namespace=namespace, install_id=install_id,
                             resource=resource, base_ref=base_ref,
                             materialization_request_id=materialization_request_id,
                             stopped_ref=stopped_ref, authorization=authorization))
        principal, namespace, install_id = (call[k] for k in ("principal", "namespace", "install_id"))
        resource, base_ref, authorization = (call[k] for k in ("resource", "base_ref", "authorization"))
        prior = self._installation(install_id)
        if prior is not None:
            require(same(prior[0]["staged_ref"]["publication"], call), "original installation identity/content conflict")
        stage, scope = self._stage(call)
        if prior is not None:
            require(same(prior[0]["staged_ref"], stage), "original installation identity/content conflict")
            intent = prior[0]
        else:
            current = self.control.resolve(principal, namespace, resource["id"], "write")
            require(same(current, resource), "actual R registration differs from original publication binding")
            require(identity(ordinary_path(stage["root"]["path"])) == stage["materialization"]["root"], "actual original staging root replaced")
            self.control.acquire(resource["id"], scope["execution_id"], base_ref)
            intent = self.control.prepare_install(principal, install_id, resource["id"], scope["execution_id"], resource["revision"], base_ref, stage)
        # This public call also rechecks original principal/namespace authorization on recovery.
        intent = self.control.prepare_install(principal, install_id, resource["id"], scope["execution_id"], resource["revision"], base_ref, stage)
        f_intent, stop = self._f_intent(intent), self._stop_projection(intent)
        existing = self.files.journal.get(install_id)
        if existing is None:
            query = self.files.install(install_id, f_intent, stop)
        else:
            # Query does not perform an install authorization check itself. Recovery
            # must not turn a revoked original grant into permission to confirm.
            context = self.files.context("install", request_id=install_id, intent=f_intent,
                                         stopped_ref=stop,
                                         actual_current_root=identity(ordinary_path(f_intent["binding"]["path"])),
                                         actual_staged_root=identity(ordinary_path(f_intent["staged_path"])))
            self.files.authorize(authorization, "install", context)
            query = self.files.query_install(install_id)
        projection = self._projection(intent, query)
        self.control.confirm_install(install_id, projection)
        release = self.control.release(resource["id"], scope["execution_id"], stop, projection)
        registration = self.control.resolve(principal, namespace, resource["id"], "write")
        return detached(dict(R_intent=intent, F_query=query, installation_ref=projection,
                             registration=registration, release=release))
