"""Shared receiver, decision and feedback transitions for the finite model."""
from copy import deepcopy


class RequestTransitions:
    def _request_view(self, identity):
        return self._report["request"].setdefault(identity, {"phase": "absent", "caller_view": "not_submitted", "payload": None})

    def op_transport_write(self, request, receiver_accepts=False):
        self._transport.append({"request": request, "bytes_written": True})
        self._request_view(request)["caller_view"] = "bytes_written"
        if receiver_accepts:
            self.op_accept_request(request, self._request_view(request).get("payload"))
        if self._bad("bytes_implies_completion"):
            # Deliberately select a controller declaration instead of receiver evidence.
            self._request_view(request)["phase"] = "completed"
            self._false_request_phases[request] = "completed"

    def op_accept_request(self, request, payload, kind=None, surface=None):
        existing = self._receiver.get(request)
        if existing:
            if existing["payload"] != payload:
                self._report["conflict_reported"] = True
                return
        else:
            self._receiver[request] = {"phase": "accepted", "payload": deepcopy(payload), "kind": kind, "surface": surface}
            self._receiver_history.append({"event": "accepted", "request": request, "payload": deepcopy(payload)})
        self._identity_index.add(request)
        self._request_view(request).update({"payload": deepcopy(payload), "caller_view": "accepted"})
        if self._bad("acceptance_starts_model") and kind == "register":
            self.op_complete_registration(request, surface, "implicitly-selected")
            self.op_explicit_start(surface, "implicitly-selected")

    def op_lose_reply(self, request):
        self._request_view(request)["caller_view"] = "unknown"

    def op_complete_registration(self, request, surface, harness):
        if request not in self._receiver:
            raise ValueError("registration requires an accepted request")
        received = self._receiver[request]
        self._registrations[surface] = True
        self._registration_bindings[surface] = harness
        received.update({"phase": "completed", "surface": surface, "harness": harness})
        self._receiver_history.append({"event": "registration_completed", "request": request, "surface": surface, "harness": harness})
        self._request_view(request)["caller_view"] = "completed"

    def op_explicit_start(self, surface, harness):
        if not self._registrations.get(surface, False):
            raise ValueError("explicit start requires a registered surface")
        self._env.launches.append({"surface": surface, "harness": harness, "origin": "explicit_start"})
        self._env.model_calls.append({"surface": surface, "harness": harness, "origin": "explicit_start"})

    def op_resubmit(self, request, payload):
        original = self._receiver.get(request)
        if self._bad("lose_request_identity_on_restart") and request not in self._identity_index:
            new_identity = f"{request}:retry:{len(self._receiver)}"
            self.op_accept_request(new_identity, payload)
            return
        if original and original["payload"] != payload:
            if self._bad("overwrite_conflicting_request"):
                original["payload"] = deepcopy(payload)
                self._receiver_history.append({"event": "conflicting_payload_overwrite", "request": request, "payload": deepcopy(payload)})
                self._report["conflict_reported"] = False
            else:
                self._report["conflict_reported"] = True
            return
        if original:
            self._request_view(request)["caller_view"] = original["phase"]
        else:
            self.op_accept_request(request, payload)

    def op_query_request(self, request):
        existing = self._receiver.get(request)
        self._request_view(request)["caller_view"] = existing["phase"] if existing else "absent"
        if self._bad("query_causes_side_effects") and existing and existing.get("surface"):
            self.op_explicit_start(existing["surface"], existing.get("harness"))

    def _retire_feedback(self, reason):
        for identity in list(self._work.pending()):
            if identity.endswith((":resolve_result", ":decide")):
                self._work.retire(identity, reason)

    def _accept_continuation(self, target, execution_id=None, source_result=None):
        if target not in self._continuations:
            self._continuations[target] = {"target": target, "execution_id": execution_id,
                                           "source_result": source_result, "durable": True}
        record = self._continuations[target]
        sources = [record["source_result"]] if record.get("source_result") else []
        self._work.accept(f"{target}:launch", sources)
        self._retire_feedback("continuation durably accepted")

    def op_accept_decision(self, decision, payload, execution_id, source_result, harness_version):
        original = self._accepted_decisions.get(decision)
        if original:
            proposal = {"payload": payload, "execution_id": execution_id,
                        "source_result": source_result, "harness_version": harness_version}
            compared_fields = tuple(proposal)
            if self._bad("ignore_decision_association_conflict"):
                compared_fields = ("payload", "execution_id")
            if any(original.get(field) != proposal[field] for field in compared_fields):
                self._report["conflict_reported"] = True
            return
        if self._content.resolve(source_result) is None:
            raise ValueError("decision source result is not available")
        self._accepted_decisions[decision] = {"phase": "accepted", "payload": payload,
                                              "execution_id": execution_id, "source_result": source_result,
                                              "harness_version": harness_version}
        self._decision_history.append({"event": "accepted", "identity": decision,
                                       "record": deepcopy(self._accepted_decisions[decision])})
        self._work.accept(f"decision:{decision}:apply", [source_result])
        self._retire_feedback("decision durably accepted")

    def op_set_harness_candidate(self, candidate, hypothetical_execution_id=None):
        self._report["harness_candidate"] = candidate
        self._hypothetical_execution_id = hypothetical_execution_id

    def op_propose_decision(self, decision, payload, execution_id):
        original = self._accepted_decisions.get(decision)
        if original is None:
            raise ValueError("proposal requires an existing decision identity in this finite protocol")
        if (payload, execution_id) != (original["payload"], original["execution_id"]):
            self._report["conflict_reported"] = True
            self._decision_history.append({"event": "conflict_rejected", "identity": decision, "payload": payload, "execution_id": execution_id})

    def _save_final_answer(self, source, harness_version=None):
        value = self._content.resolve(source)
        if value is None:
            return False
        self._answer_record = {"source_result": source, "content": f"final:{value}", "harness_version": harness_version, "durable": True}
        self._retire_feedback("final answer durably saved")
        return True

    def _advance_accepted_decision(self):
        for identity, accepted in self._accepted_decisions.items():
            responsibility = f"decision:{identity}:apply"
            if responsibility not in self._work.pending():
                continue
            if self._content.resolve(accepted.get("source_result")) is None:
                self._report["recovery_status"] = "missing_confirmed_state"
                return False
            payload, operation = accepted["payload"], accepted["execution_id"]
            if self._bad("recompute_accepted_decision"):
                payload = self._report["harness_candidate"]
                operation = self._hypothetical_execution_id
                self._decision_history.append({"event": "wrong_recomputed_branch", "identity": identity, "candidate": payload, "operation": operation})
            if payload.startswith("continue:"):
                self._accept_continuation(payload.split(":", 1)[1], operation, accepted.get("source_result"))
            elif payload == "stop":
                self._save_final_answer(accepted.get("source_result"), accepted.get("harness_version"))
            else:
                raise ValueError("unsupported finite decision payload")
            self._work.retire(responsibility, "accepted branch implemented")
            return True
        return False

    def _advance_feedback(self):
        if not any(key.endswith((":resolve_result", ":decide")) for key in self._work.pending()):
            return False
        result = self._content.resolve(self._result_ref)
        if result is None:
            return False
        policy = self._report["harness_policy"]
        if self._bad("result_implies_automatic_continue"):
            policy = f"continue_after_{result}"
        if policy == f"continue_after_{result}":
            self._accept_continuation("step2", source_result=self._result_ref)
            return True
        if policy == f"final_after_{result}":
            return self._save_final_answer(self._result_ref)
        return False

    def _launch_accepted_step(self):
        for target, record in self._continuations.items():
            pending = f"{target}:launch"
            if pending not in self._work.pending():
                continue
            if record.get("source_result") and self._content.resolve(record["source_result"]) is None:
                return False
            operation = record.get("execution_id") or f"continuation:{target}"
            fact = {"step": target, "operation": operation, "origin": "accepted_continuation"}
            self._env.step_launches.append(fact)
            self._env.launches.append(deepcopy(fact))
            self._active_operation = operation
            sources = [record["source_result"]] if record.get("source_result") else []
            self._work.accept(f"{target}:running", sources)
            self._work.retire(pending, "execution fixture reports started")
            return True
        return False
