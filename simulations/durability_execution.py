"""Crash, query, result and bounded scheduler transitions."""


class ExecutionTransitions:
    def op_crash(self, domain, cut=None):
        if domain not in {"runtime_volatile", "task_and_runtime_volatile", "all_volatile_and_sandbox"}:
            raise ValueError("unknown crash domain")
        if self._bad("invent_unsaved_result"):
            self._unsafe_cached_result = self._report.get("volatile_result")
        self._report["volatile_result"] = None
        self._notifications.clear()
        self._volatile_next = None
        if self._bad("lose_request_identity_on_restart"):
            self._identity_index.clear()
        if domain != "runtime_volatile":
            self._env.release(["agent", "connection", "sandbox"])
            self._env.process_alive = False
            self._env.child_alive = False
            self._content.crash_sandbox()
        self._work.lose_volatile()
        self._continuations = {key: value for key, value in self._continuations.items() if value["durable"]}
        self._crash_history.append({"domain": domain, "cut_annotation": cut})
        self._running = False

    def op_restart(self):
        self._running = True
        self._restart_count += 1

    def op_recover_saved_state(self):
        missing = [ref for ref in self._content.confirmations if self._content.resolve(ref) is None]
        if missing:
            self._report["recovery_status"] = "missing_confirmed_state"
            self._report["completion_claim"] = False
            return
        if self._bad("invent_unsaved_result") and self._unsafe_cached_result is not None:
            # Wrong observation source, without fabricating a fixture confirmation.
            self._false_saved_result = self._unsafe_cached_result
            self._report["recovery_status"] = "recovered"
            return
        unresolved = any(identity.endswith((":resolve_result", ":resolve")) for identity in self._work.pending())
        if self._result_ref is None and unresolved:
            self._report["recovery_status"] = "paused_unknown"
        else:
            self._report["recovery_status"] = "recovered"
        if self._deliveries:
            self._input_view = list(dict.fromkeys(r["event"] for r in self._deliveries))

    def op_save_result(self, result, operation, harness_version=None):
        self._content.confirm(result)
        self._result_ref = result
        self._result_records.append({"result": result, "operation": operation, "harness_version": harness_version})
        self._report["volatile_result"] = None
        if self._bad("drop_responsibility_after_result"):
            self._retire_feedback("incorrect result-as-terminal acknowledgement")
            self._volatile_next = {"source": result, "policy": self._report["harness_policy"]}
            return
        for identity in list(self._work.pending()):
            if identity.endswith(":resolve_result"):
                next_identity = identity.rsplit(":", 1)[0] + ":decide"
                self._work.accept(next_identity, [result])
                self._work.retire(identity, "saved result, durable interpretation responsibility")

    def op_settle_enabled_recovery(self, fair):
        if fair is not True:
            raise ValueError("finite scheduler requires the preregistered fair driving condition")
        transitions = [self._advance_accepted_decision, self._advance_feedback,
                       self._launch_accepted_step, self._deliver_wait]
        for tick in range(8):
            changed = False
            for transition in transitions:
                if transition():
                    self._scheduler_history.append({"transition": transition.__name__, "tick": tick})
                    changed = True
                    break
            if not changed:
                return
        self._report["scheduler_status"] = "INCONCLUSIVE_NOT_PASS"
        raise RuntimeError("finite transition bound exhausted")

    def op_query_external(self, operation, answer, result=None):
        if answer not in {"found_completed", "unavailable", "not_found_nonfinal"}:
            raise ValueError("unsupported fixture query answer")
        if self._bad("retry_unknown_before_query") and self._report["execution_status"] == "unknown":
            self._env.effect(operation, "incorrect_retry_before_query", blind=True)
        self._env.query_facts[operation] = {"answer": answer, "result": result, "source": "target_fixture"}
        self._report["query_status"] = answer
        self._report["external_operation_identity"] = operation
        if self._bad("retry_on_nonfinal_not_found") and answer == "not_found_nonfinal":
            self._env.effect(operation, "incorrect_nonfinal_not_found_retry", blind=True)

    def op_recover_execution_result(self, operation):
        observed = self._env.query_facts.get(operation)
        if not observed or observed["answer"] != "found_completed" or observed["result"] is None:
            self._report["recovery_status"] = "paused_unknown"
            return
        self.op_save_result(observed["result"], operation)
        self._report["execution_status"] = "finished"
        self._report["recovery_status"] = "recovered"
        self._work.retire(f"{operation}:resolve", "same-identity target result durably saved")

    def op_request_safe_continuation(self, operation, safe_retry_basis):
        observed = self._env.query_facts.get(operation, {})
        if not safe_retry_basis:
            if self._bad("discard_unknown_operation_on_query_failure") and observed.get("answer") == "unavailable":
                self._work.retire(f"{operation}:resolve", "incorrect query-failure-as-completion")
                self._report["completion_claim"] = True
                self._report["recovery_status"] = "completed"
            else:
                self._work.accept(f"{operation}:resolve")
                self._report["recovery_status"] = "paused_unknown"
                self._report["completion_claim"] = False
            return
        # No registered trajectory supplies this additional safety contract.
        raise ValueError("safe retry semantics require a separately registered fixture basis")

    def op_external_effect_occurs(self, operation, origin):
        self._env.effect(operation, origin)

    def op_request_cancel(self, operation):
        self._report["cancel_requested"] = True
        self._cancel_history.append({"operation": operation, "event": "cancel_requested"})
        if self._bad("cancel_request_means_stopped"):
            self._report["execution_status"] = "finished"

    def op_executor_confirms_stop(self, operation, include_children):
        self._env.process_alive = False
        if include_children:
            self._env.child_alive = False
        self._env.history.append({"event": "executor_stop_observed", "operation": operation, "include_children": include_children})
        if not self._env.process_alive and not self._env.child_alive:
            self._report["execution_status"] = "finished"
