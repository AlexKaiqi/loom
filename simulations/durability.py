"""Finite durability model implementing the frozen G1 operation protocol.

This module performs no I/O and never loads case IDs, expectations or suite files.
The caller supplies a fully merged initial fixture and individual operations.
"""
from copy import deepcopy

if __package__:
    from .durability_facts import ContentFacts, EnvironmentFacts, Responsibilities, bounded_count
    from .durability_requests import RequestTransitions
    from .durability_events import EventTransitions
    from .durability_execution import ExecutionTransitions
else:
    from durability_facts import ContentFacts, EnvironmentFacts, Responsibilities, bounded_count
    from durability_requests import RequestTransitions
    from durability_events import EventTransitions
    from durability_execution import ExecutionTransitions


class DurabilityModel(RequestTransitions, EventTransitions, ExecutionTransitions):
    VARIANTS = frozenset({
        "bytes_implies_completion", "acceptance_starts_model", "lose_request_identity_on_restart",
        "overwrite_conflicting_request", "query_causes_side_effects", "invent_unsaved_result",
        "drop_responsibility_after_result", "volatile_next_step_acceptance", "sandbox_only_confirmed_content",
        "retry_unknown_before_query", "discard_unknown_operation_on_query_failure", "retry_on_nonfinal_not_found",
        "ignore_preexisting_events", "scan_subscribe_gap", "ignore_future_events", "ignore_wait_origin",
        "notification_only_worklist", "read_view_marks_processed", "notify_creates_new_business_step",
        "expire_promised_record", "archive_leaves_stale_reference", "preserve_task_waiter",
        "release_before_durable_wait", "cancel_request_means_stopped", "replay_executes_event_payload",
        "missing_history_means_success", "result_implies_automatic_continue", "recompute_accepted_decision",
        "ignore_decision_association_conflict",
    })

    def __init__(self, initial_state, variant=None):
        if variant is not None and variant not in self.VARIANTS:
            raise ValueError("unknown durability mutation")
        self.variant = variant
        self._report = deepcopy(initial_state)
        self._env = EnvironmentFacts(initial_state)
        self._content = ContentFacts(initial_state["confirmed_refs"], initial_state["resolvable_refs"],
                                     initial_state["record_locations"], self._bad("sandbox_only_confirmed_content"))
        self._result_ref = initial_state["saved_result"]
        if self._result_ref is not None:
            # The protocol explicitly seeds a saved_result as independent persistent content.
            if self._result_ref not in self._content.confirmations:
                self._content.confirm(self._result_ref)
            elif self._content.resolve(self._result_ref) is None:
                self._content.confirm(self._result_ref)
        self._result_records = []
        if self._result_ref is not None:
            self._result_records.append({"result": self._result_ref, "origin": "initial_persistent_fixture"})
        self._work = Responsibilities(initial_state["pending_responsibility"], list(self._content.confirmations))
        self._receiver = {identity: deepcopy(record) for identity, record in initial_state["request"].items()
                          if record.get("phase") in {"accepted", "completed"}}
        self._receiver_history = [{"event": "initial_receiver_fact", "request": key, "record": deepcopy(value)}
                                  for key, value in self._receiver.items()]
        self._identity_index = set(self._receiver)
        self._registrations = deepcopy(initial_state["registration"])
        self._registration_bindings = {}
        self._false_request_phases = {}
        self._transport = []
        self._accepted_decisions = {key: deepcopy(value) for key, value in initial_state["decision"].items()
                                    if value.get("phase") == "accepted"}
        self._decision_history = []
        self._continuations = {}
        for identity in self._work.pending():
            if identity.endswith(":launch"):
                target = identity.rsplit(":", 1)[0]
                self._continuations[target] = {"target": target, "execution_id": None,
                                                "source_result": self._result_ref, "durable": True}
        if initial_state["next_step_accepted"] and not self._continuations:
            # This finite suite's singular next-step counter denotes its declared step2.
            self._continuations["step2"] = {"target": "step2", "execution_id": None,
                                             "source_result": self._result_ref, "durable": True}
            self._work.accept("step2:launch", [self._result_ref] if self._result_ref else [])
        self._continuation_history = [{"event": "initial_acceptance", "record": deepcopy(value)}
                                       for value in self._continuations.values()]
        if self._bad("volatile_next_step_acceptance"):
            for value in self._continuations.values():
                value["durable"] = False
            for identity, value in self._work.records.items():
                if identity.endswith(":launch"):
                    value["durable"] = False
        for fact in self._env.step_launches:
            fact["step"] = "step2"
        self._active_operation = initial_state["active_operation_identity"]
        self._answer_record = None
        if initial_state["answer_saved"]:
            self._answer_record = {"content": "initial_saved_answer", "durable": True}
        self._hypothetical_execution_id = None
        self._events = deepcopy(initial_state["events"])
        self._event_history = [{"event": "initial_persisted_event", "record": deepcopy(e)} for e in self._events]
        event_lookup = {event["id"]: event for event in self._events}
        self._deliveries = [{"relation": f"initial:{identity}:{step}", "event": identity, "step": step,
                             "payload": deepcopy(event_lookup[identity]["payload"])}
                            for identity, step in initial_state["event_bindings"].items()]
        self._processed_events = set(initial_state["event_bindings"]) if initial_state["event_processing_completed"] else set()
        self._input_view = list(initial_state["input_view"])
        self._view_reads = []
        self._replayed = set(initial_state["replayed_event_ids"])
        self._notifications = set()
        self._scans = []
        self._scan_event_ids = None
        self._wait = deepcopy(initial_state["wait"])
        pending_waits = [key for key in self._work.pending() if key.endswith(":wait")]
        self._wait_identity = pending_waits[0].rsplit(":", 1)[0] if pending_waits else "w1"
        self._wait_saved = self._wait["phase"] in {"accepted", "waiting", "delivered"}
        self._wait_boundary = max((event["position"] for event in self._events), default=-1)
        self._wait_initial_events = {event["id"] for event in self._events}
        self._required_state_receipts = []
        if initial_state["required_state_saved"]:
            self._required_state_receipts.append({"origin": "initial_persistence_fixture", "refs": list(self._content.confirmations)})
        if self._wait_saved and self._wait["phase"] != "delivered":
            self._work.accept(f"{self._wait_identity}:wait", self._required_refs())
        self._resource_requests = []
        self._retention_history = []
        self._cancel_history = []
        self._crash_history = []
        self._scheduler_history = []
        self._running = True
        self._restart_count = 0
        self._volatile_next = None
        self._unsafe_cached_result = None
        self._false_saved_result = None
        self._action_history = []

    def _bad(self, name):
        return self.variant == name

    def _required_refs(self):
        return list(dict.fromkeys(ref for receipt in self._required_state_receipts for ref in receipt["refs"]))

    def _required_state_saved(self):
        return bool(self._required_state_receipts) and all(self._content.resolve(ref) is not None for ref in self._required_refs())

    def apply(self, op, args):
        if not isinstance(op, str) or not isinstance(args, dict):
            raise TypeError("operation must be a name with an argument dictionary")
        handler = getattr(self, "op_" + op, None)
        if handler is None or not callable(handler):
            raise ValueError(f"unknown durability operation: {op}")
        handler(**deepcopy(args))
        self._action_history.append({"op": op, "args": deepcopy(args)})

    def snapshot(self):
        view = deepcopy(self._report)
        requests = deepcopy(view["request"])
        for identity, received in self._receiver.items():
            caller_view = requests.get(identity, {}).get("caller_view", "unknown")
            requests[identity] = {**deepcopy(received), "caller_view": caller_view}
        for identity, phase in self._false_request_phases.items():
            requests[identity]["phase"] = phase
        decisions = deepcopy(view["decision"])
        decisions.update(deepcopy(self._accepted_decisions))
        bindings = {}
        for relationship in self._deliveries:
            bindings.setdefault(relationship["event"], relationship["step"])
        result = self._content.resolve(self._result_ref) if self._result_ref is not None else None
        if self._false_saved_result is not None:
            result = self._false_saved_result
        view.update({
            "request": requests, "registration": deepcopy(self._registrations), "decision": decisions,
            "logical_request_count": bounded_count(self._receiver), "launch_count": bounded_count(self._env.launches),
            "step2_launch_count": bounded_count([f for f in self._env.step_launches if f.get("step") == "step2"]),
            "next_step_accepted": bounded_count(self._continuations), "saved_result": result,
            "confirmed_refs": list(self._content.confirmations), "resolvable_refs": self._content.resolvable(),
            "pending_responsibility": self._work.pending(),
            "recoverable_responsibility": self._work.recoverable(self._content, self._events),
            "answer_saved": bool(self._answer_record and self._answer_record["durable"]),
            "model_call_count": bounded_count(self._env.model_calls), "external_effect_count": bounded_count(self._env.effects),
            "blind_retry_count": bounded_count(self._env.retries), "active_operation_identity": self._active_operation,
            "events": deepcopy(self._events), "event_bindings": bindings,
            "delivery_responsibility_count": bounded_count(self._deliveries),
            "delivered_payloads": [deepcopy(r["payload"]) for r in self._deliveries],
            "replayed_event_ids": sorted(self._replayed), "input_view": list(self._input_view),
            "event_processing_completed": bool(bindings) and all(key in self._processed_events for key in bindings),
            "wait": deepcopy(self._wait), "required_state_saved": self._required_state_saved(),
            "resources": {key: len(value) for key, value in self._env.resources.items()},
            "record_locations": deepcopy(self._content.locators),
            "observed_process_alive": self._env.process_alive, "observed_child_alive": self._env.child_alive,
        })
        view["_evidence"] = {
            "receiver_requests": deepcopy(self._receiver), "receiver_history": deepcopy(self._receiver_history),
            "transport": deepcopy(self._transport), "contents": self._content.evidence(), "environment": self._env.evidence(),
            "responsibilities": deepcopy(self._work.records), "responsibility_history": deepcopy(self._work.history),
            "accepted_decisions": deepcopy(self._accepted_decisions), "decision_history": deepcopy(self._decision_history),
            "continuations": deepcopy(self._continuations), "continuation_history": deepcopy(self._continuation_history),
            "result_records": deepcopy(self._result_records), "answer_record": deepcopy(self._answer_record),
            "delivery_relationships": deepcopy(self._deliveries), "event_history": deepcopy(self._event_history),
            "required_state_receipts": deepcopy(self._required_state_receipts), "resource_requests": deepcopy(self._resource_requests),
            "retention": deepcopy(self._retention_history), "cancel_requests": deepcopy(self._cancel_history),
            "crashes": deepcopy(self._crash_history), "scheduler": deepcopy(self._scheduler_history),
            "actions": deepcopy(self._action_history), "restart_count": self._restart_count,
        }
        return view
