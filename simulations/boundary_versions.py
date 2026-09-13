"""Versioned inputs and restored content remain independent of mutable paths."""
from copy import deepcopy


class VersionOperations:
    def _op_read_object(self, args):
        self._observe(args, **self._state["objects"][args["object"]])

    def _op_conditional_edit(self, args):
        obj = self._state["objects"][args["object"]]
        stale = args["base_revision"] != obj["revision"]
        if stale:
            proposal = {key: deepcopy(value) for key, value in args.items()
                        if key != "observation"}
            self._state["records"]["rejected_edits"].append(proposal)
            if self.variant != "ignore_external_edit":
                self._observe(args, status="conflict", revision=obj["revision"])
                return
            # Fault injection bypasses the write guard after the shared
            # conflict detector records the actual stale proposal.
        self._write_object(args["object"], args["value"])
        self._observe(args, status="applied", revision=obj["revision"])

    def _op_capture_object_version(self, args):
        actual = deepcopy(self._state["objects"][args["object"]])
        self._state["versions"][args["reference"]] = actual
        self._observe(args, status="captured", reference=args["reference"], **actual)

    def _op_begin_render(self, args):
        # Copy the bound set, rather than retaining an alias to mutable input.
        contents = deepcopy(self._state["input_sets"][args["input_set"]])
        self._state["renders"][args["render"]] = {
            "input_set": args["input_set"], "bound_inputs": contents,
            "materialized": {},
        }
        self._observe(args, status="bound", input_set=args["input_set"],
                      bound_inputs=contents)

    def _op_render_read(self, args):
        render = self._state["renders"][args["render"]]
        source = render["bound_inputs"]
        if self.variant == "read_latest_during_render":
            source = self._state["current_input"]
        render["materialized"][args["file"]] = deepcopy(source[args["file"]])
        self._observe(args, value=render["materialized"][args["file"]])

    def _op_finish_render(self, args):
        render = self._state["renders"][args["render"]]
        complete = render["materialized"] == render["bound_inputs"]
        self._observe(args, status="complete" if complete else "inconsistent",
                      materialized=render["materialized"],
                      input_set=render["input_set"])

    def _op_render_all(self, args):
        render = self._state["renders"][args["render"]]
        for file in render["bound_inputs"]:
            self._op_render_read({"render": args["render"], "file": file})
        self._op_finish_render(args)

    def _op_capture_snapshot(self, args):
        versions = self._state["versions"]
        required = args["required_references"]
        contents = {}
        for reference in required:
            entry = versions.get(reference)
            if entry is None:
                continue
            if self.variant == "tracked_only_snapshot" and not entry.get("tracked"):
                continue
            contents[reference] = deepcopy(entry["value"])
        missing = [reference for reference in required if reference not in contents]
        self._state["snapshots"][args["snapshot"]] = {
            "required_references": deepcopy(required), "contents": contents,
        }
        self._observe(args, status="incomplete" if missing else "complete",
                      missing=missing)

    def _op_restore_snapshot(self, args):
        captured = self._state["snapshots"].get(args["snapshot"])
        if captured is None:
            self._observe(args, status="incomplete")
            return
        restored = deepcopy(captured["contents"])
        self._state["restored"][args["snapshot"]] = restored
        missing = [reference for reference in captured["required_references"]
                   if reference not in restored]
        self._observe(args, status="incomplete" if missing else "complete",
                      missing=missing)

    def _op_restore_domains(self, args):
        requested = args["versions"]
        missing = [reference for reference in requested.values()
                   if self._state["versions"].get(reference) is None]
        if missing:
            self._observe(args, status="incomplete", missing=missing)
            return
        self._state["domain_versions"] = deepcopy(requested)
        history = self._state["records"]["history"]
        if self.variant == "rollback_erases_history":
            # Content erasure preserves actual sequence slots as tombstones.
            # snapshot does not synthesize these slots from assertions.
            history[:] = [None for _ in history]
        history.append({"kind": "rollback", "versions": deepcopy(requested)})
        self._observe(args, status="restored", versions=requested)

    def _op_replay_history(self, args):
        before = deepcopy(self._state["external_effects"])
        history = deepcopy(self._state["records"]["history"])
        after = self._state["external_effects"]
        count = sum(after.get(key, 0) - before.get(key, 0)
                    for key in set(before) | set(after))
        self._observe(args, history=history, side_effect_executions=count)

    def _op_begin_step(self, args):
        step = {"surface": args["surface"],
                "harness": self._state["bindings"][args["surface"]]}
        existing = self._state["steps"].get(args["step"])
        if existing is not None:
            # Starting the same identity again may not repin accepted work.
            self._observe(args, status="existing", harness=existing["harness"])
            return
        self._state["steps"][args["step"]] = step
        self._observe(args, status="started", harness=step["harness"])

    def _op_step_phase(self, args):
        if args["phase"] not in {"model", "template", "parser"}:
            raise ValueError("Unsupported Harness phase")
        step = self._state["steps"][args["step"]]
        reference = step["harness"]
        if self.variant == "latest_harness_each_phase":
            reference = self._state["bindings"][step["surface"]]
        harness = self._state["harness_versions"].get(reference)
        if harness is None or args["phase"] not in harness:
            self._observe(args, status="blocked", harness=reference)
            return
        self._observe(args, status="available", harness=reference,
                      value=harness[args["phase"]])
