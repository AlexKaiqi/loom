"""Persistent event delivery, wait and retention transitions."""
from copy import deepcopy


class EventTransitions:
    def op_record_event(self, event, position, kind, payload):
        record = {"id": event, "position": position, "kind": kind, "payload": deepcopy(payload)}
        old = next((e for e in self._events if e["id"] == event), None)
        if old is not None:
            if old != record:
                raise ValueError("event identity content conflict")
            return
        self._events.append(record)
        self._event_history.append({"event": "persisted", "record": deepcopy(record)})

    def op_begin_wait(self, wait, origin, match, target):
        if self._wait_saved:
            raise ValueError("one finite wait already accepted")
        self._wait_identity = wait
        self._wait.update({"phase": "preparing", "origin": origin, "match": match, "target": target})

    def op_accept_wait(self, wait):
        self._wait_identity = wait
        if not self._required_state_saved():
            self._wait["phase"] = "preparing"
            return
        self._wait_saved = True
        self._wait["phase"] = "accepted"
        self._wait_boundary = max((e["position"] for e in self._events), default=-1)
        self._wait_initial_events = {e["id"] for e in self._events}
        self._work.accept(f"{wait}:wait", self._required_refs())
        # Save-before-wait work may retire only after the new wait record exists.
        for identity in list(self._work.pending()):
            if identity.endswith(":save_before_wait"):
                self._work.retire(identity, "wait durably accepted")

    def op_scan_history(self, wait, origin, match):
        self._scan_event_ids = {e["id"] for e in self._events if e["position"] >= origin and e["kind"] == match}
        self._scans.append({"wait": wait, "origin": origin, "match": match, "events": sorted(self._scan_event_ids)})

    def op_notify(self, event):
        if not any(e["id"] == event for e in self._events):
            raise ValueError("notification has no persisted event")
        self._notifications.add(event)
        if self._bad("notify_creates_new_business_step"):
            previous = next((r for r in self._deliveries if r["event"] == event), None)
            if previous:
                new = deepcopy(previous)
                new["relation"] = f"notification:{len(self._deliveries)}:{event}"
                self._deliveries.append(new)
                self._env.effect(event, "incorrect_duplicate_notification")

    def op_drop_notification(self, event):
        self._notifications.discard(event)

    def _wait_matches(self):
        if not self._wait_saved or self._wait["phase"] not in {"accepted", "waiting"}:
            return []
        matches = []
        for event in sorted(self._events, key=lambda e: e["position"]):
            if event["kind"] != self._wait["match"]:
                continue
            if not self._bad("ignore_wait_origin") and event["position"] < self._wait["origin"]:
                continue
            if self._bad("ignore_preexisting_events") and event["position"] <= self._wait_boundary:
                continue
            if self._bad("ignore_future_events") and event["id"] not in self._wait_initial_events:
                continue
            if self._bad("notification_only_worklist") and event["id"] not in self._notifications:
                continue
            if (self._bad("scan_subscribe_gap") and self._scan_event_ids is not None
                    and event["id"] not in self._scan_event_ids and event["position"] <= self._wait_boundary):
                continue
            matches.append(event)
        return matches

    def _deliver_wait(self):
        matches = self._wait_matches()
        if not matches:
            return False
        # The preregistered fixture condition consumes the first matching event.
        event = matches[0]
        existing = next((r for r in self._deliveries if r["event"] == event["id"]), None)
        if existing is None:
            target_step = f"{self._wait['target']}:step1"
            relation = {"relation": f"{self._wait_identity}:{event['id']}", "event": event["id"],
                        "step": target_step, "payload": deepcopy(event["payload"])}
            self._deliveries.append(relation)
            self._work.accept(f"{target_step}:process_{event['id']}", event_refs=[event["id"]])
        self._work.retire(f"{self._wait_identity}:wait", "delivery durably accepted")
        self._wait["phase"] = "delivered"
        self._input_view = [event["id"]]
        return True

    def op_read_input_view(self, step):
        self._view_reads.append({"step": step, "events": list(self._input_view)})
        if self._bad("read_view_marks_processed"):
            self._processed_events.update(self._input_view)
            for identity in list(self._work.pending()):
                if identity.startswith(f"{step}:process_"):
                    self._work.retire(identity, "incorrect read-as-processing acknowledgement")

    def op_request_expiry(self, record, promise_active):
        depended_on = any(record in r["required_refs"] for r in self._work.records.values() if r["status"] == "pending")
        if (self._report["promise_active"] or promise_active or depended_on) and not self._bad("expire_promised_record"):
            self._retention_history.append({"event": "expiry_refused", "record": record})
            return
        self._content.expire(record)

    def op_archive_record(self, record, destination, content_identity):
        if self._content.resolve(record) != content_identity:
            raise ValueError("archive identity does not match actual source content")
        self._content.archive(record, destination, self._bad("archive_leaves_stale_reference"))

    def op_release_task_resources(self, task, executor_confirms):
        if not self._required_state_saved():
            return
        if executor_confirms:
            kinds = ["sandbox"] if self._bad("preserve_task_waiter") else ["agent", "connection", "sandbox"]
            self._env.release(kinds)
            if "agent" in kinds:
                self._env.process_alive = False
                self._env.child_alive = False
        self._resource_requests.append({"task": task, "confirmed": bool(executor_confirms)})

    def op_declare_waiting(self, task):
        if self._wait_saved and self._required_state_saved():
            if all(not self._env.resources[k] for k in ["agent", "connection", "sandbox"]):
                self._wait["phase"] = "waiting"
            elif self._bad("preserve_task_waiter"):
                self._wait["phase"] = "waiting"  # False controller declaration; inventory is unchanged.

    def op_request_enter_wait(self, wait, persistence_ack_available):
        self._wait_identity = wait
        self._wait["phase"] = "preparing"
        self._report["persistence_ack_available"] = persistence_ack_available
        if self._bad("release_before_durable_wait"):
            self._wait["phase"] = "accepted"
            self._env.release(["agent", "connection", "sandbox"])
        elif persistence_ack_available and self._required_state_saved():
            self.op_accept_wait(wait)

    def op_confirm_required_state_saved(self, refs):
        for ref in refs:
            self._content.confirm(ref)
        self._required_state_receipts.append({"origin": "persistence_fixture", "refs": list(refs)})
        self._report["persistence_ack_available"] = True

    def op_replay_events(self, origin, through):
        for event in self._events:
            if origin <= event["position"] <= through:
                self._replayed.add(event["id"])
                if self._bad("replay_executes_event_payload"):
                    self._env.effect(event["payload"], "incorrect_event_replay")

    def op_request_out_of_scope_history(self, record, availability):
        self._report["requested_historical_ref"] = record
        if availability == "expired" and self._content.resolve(record) is None:
            self._report["recovery_status"] = "history_unavailable"
            self._report["completion_claim"] = False
            if self._bad("missing_history_means_success"):
                self._report["recovery_status"] = "recovered"
                self._report["completion_claim"] = True
