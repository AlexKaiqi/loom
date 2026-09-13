"""Authority, projections and unknown effects use separate source records."""
from copy import deepcopy


class RecordOperations:
    def _register_message(self, body, validate=True):
        surface = body["surface"]
        identity = body.get("directory_identity")
        if validate:
            matching = [target for target in self._state["targets"].values()
                        if surface in target["writes"]
                        and target["object_identity"] == identity
                        and self._state["directory_identity"].get(
                            target["location"]) == identity]
            if not matching:
                return False
        self._state["registry"][surface] = deepcopy(body)
        self._state["events"]["runtime"].append({
            "kind": "registration-confirmed", "source": "runtime",
            "surface": surface,
        })
        return True

    def _op_submit_message(self, args):
        kind = args["kind"]
        authorized = kind in self._state["submission_grants"].get(
            args["principal"], [])
        if not authorized:
            self._observe(args, status="rejected", registration_completed=False)
            return
        if kind == "application":
            event = {"kind": "application", "name": args["name"],
                     "body": deepcopy(args["body"]), "source": args["principal"]}
            self._state["events"]["app"].append(event)
            if self.variant == "event_name_is_authority":
                if args["name"] == "surface.registered":
                    completed = self._register_message(args["body"], validate=False)
                    self._observe(args, record_kind="runtime",
                                  registration_completed=completed)
                    return
            self._observe(args, record_kind="application",
                          registration_completed=False)
        elif kind == "register":
            completed = self._register_message(args["body"])
            self._observe(args, record_kind="runtime",
                          status="registered" if completed else "rejected",
                          registration_completed=completed)
        else:
            raise ValueError("Unsupported message kind")

    def _op_read_untrusted_content(self, args):
        actions = []
        if self.variant == "auto_execute_blocks" and args["source"] == "block":
            # This deliberately unsafe finite interpreter actually changes
            # named objects. No real shell or host action is ever executed.
            in_block = False
            for line in args["text"].splitlines():
                if line.startswith(chr(96) * 3):
                    in_block = not in_block
                    continue
                words = line.strip().split()
                if in_block and len(words) >= 2 and words[0] == "write":
                    actual = words[1]
                    if actual in self._state["objects"]:
                        self._write_object(actual, args["text"])
                        actions.append({"kind": "write", "object": actual})
        self._observe(args, text=args["text"], source=args["source"],
                      control_actions=len(actions), actual_actions=actions)

    def _op_read_input_view(self, args):
        self._observe(args, value=self._state["input_views"][args["view"]])

    def _op_mutate_private_view(self, args):
        previous = self._state["input_views"][args["view"]]
        if self.variant == "view_is_authority":
            for events in self._state["events"].values():
                for index, event in enumerate(events):
                    if event.get("id") == previous.get("id"):
                        events[index] = deepcopy(args["value"])
        self._state["input_views"][args["view"]] = deepcopy(args["value"])
        self._observe(args, status="mutated",
                      value=self._state["input_views"][args["view"]])

    def _op_notify_existing_input(self, args):
        found = any(event.get("id") == args["event"]
                    for events in self._state["events"].values()
                    for event in events)
        self._observe(args, status="notified" if found else "missing")

    def _op_regenerate_input_view(self, args):
        matches = [event for events in self._state["events"].values()
                   for event in events if event.get("id") == args["event"]]
        if len(matches) != 1:
            self._observe(args, status="missing-or-ambiguous")
            return
        self._state.setdefault("input_views", {})[args["view"]] = deepcopy(matches[0])
        self._observe(args, status="regenerated")

    def _op_trim_projection(self, args):
        records = self._state["records"]
        source = records["raw"][args["source"]]
        required = {key: deepcopy(records["projection"][key])
                    for key in args["required_context"]
                    if key in records["projection"]}
        records["projection"]["log"] = deepcopy(args["retained"])
        truncated = source != args["retained"]
        if self.variant == "trim_deletes_raw":
            records["raw"][args["source"]] = deepcopy(args["retained"])
        if self.variant == "trim_drops_unknown":
            removed = {operation for operation, value in records["saved"].items()
                       if isinstance(value, dict) and value.get("state") == "unknown"}
            for operation in removed:
                del records["saved"][operation]
            records["pending"] = [op for op in records["pending"] if op not in removed]
        self._observe(args, truncated=truncated, source=args["source"],
                      required_context=required)

    def _op_read_source(self, args):
        authorized = args["reference"] in self._state["read_grants"].get(
            args["environment"], [])
        raw = self._state["records"]["raw"]
        if not authorized:
            self._observe(args, status="denied")
        elif args["reference"] not in raw:
            self._observe(args, status="missing")
        else:
            self._observe(args, status="allowed", value=raw[args["reference"]])

    def _op_retry_operation(self, args):
        operation = args["operation"]
        records = self._state["records"]
        known = records["saved"].get(operation)
        if isinstance(known, dict) and known.get("state") == "confirmed":
            self._observe(args, status="already-completed")
            return
        if self.variant == "trim_drops_unknown" and known is None:
            effects = self._state["external_effects"]
            effects[operation] = effects.get(operation, 0) + 1
            self._observe(args, status="retried")
            return
        # No fixture in this protocol declares safe retry/not-started proof.
        # Absence of a saved record cannot stand in for that proof.
        self._observe(args, status="blocked")

    def _op_query_effect(self, args):
        operation = args["operation"]
        actual = self._state["external_effects"].get(operation)
        records = self._state["records"]
        if actual is None:
            self._observe(args, status="unknown")
            return
        records["saved"][operation] = {
            "state": "confirmed", "effect_count": actual,
            "query_reference": operation,
        }
        records["pending"] = [pending for pending in records["pending"]
                              if pending != operation]
        self._observe(args, status="confirmed", effect_count=actual)

    def _op_project_context(self, args):
        available = self._state["available_inputs"]
        missing = [key for key in args["required_inputs"]
                   if key not in available or available[key] is None]
        inputs = {key: deepcopy(available[key]) for key in args["required_inputs"]
                  if key in available}
        self._observe(args, status="incomplete" if missing else "complete",
                      inputs=inputs, missing=missing,
                      domain_versions=self._state["domain_versions"])
