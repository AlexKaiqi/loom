"""Writer responsibility is separate from fixture capability and exit facts."""


class WriterOperations:
    def _op_change_owner_record(self, args):
        self._state["control"]["owners"][args["resource"]] = args["owner"]
        self._observe(args, status="recorded", owner=args["owner"])

    def _op_request_takeover(self, args):
        state = self._state
        resource, writer = args["resource"], args["writer"]
        writers = state["effective_writers"].setdefault(resource, [])
        others = [item for item in writers if item != writer]
        ignore_others = False
        if self.variant == "owner_record_as_revocation":
            ignore_others = state["control"]["owners"].get(resource) == writer
        if self.variant == "surface_lock_is_workspace_lock":
            source = args.get("source_surface")
            ignore_others = writer in state["effective_writers"].get(source, [])
        if self.variant == "parent_exit_as_tree_stop":
            assumed = state["control"].get("assumed_stopped_processes", [])
            ignore_others = bool(others) and all(item in assumed for item in others)
        if others and not ignore_others:
            self._observe(args, status="blocked")
            return
        # A faulty grant adds a second actual writer. Changing the owner
        # record cannot erase the old executor's independent capability.
        if others:
            if writer not in writers:
                writers.append(writer)
        else:
            state["effective_writers"][resource] = [writer]
        self._observe(args, status="granted")

    def _op_attempt_write(self, args):
        writers = self._state["effective_writers"].get(args["resource"], [])
        allowed = args["writer"] in writers
        if allowed:
            self._write_object(args["resource"], args["value"])
        self._observe(args, status="allowed" if allowed else "rejected")

    def _op_observe_revocation(self, args):
        if not args["witness"]:
            raise ValueError("Revocation requires an independent fixture witness")
        writers = self._state["effective_writers"].get(args["resource"], [])
        self._state["effective_writers"][args["resource"]] = [
            writer for writer in writers if writer not in args["revoked_writers"]
        ]
        self._observe(args, status="observed", effective_writers=
                      self._state["effective_writers"][args["resource"]])

    def _op_request_cancel(self, args):
        self._state["processes"][args["process"]]["cancel_requested"] = True
        self._observe(args, status="requested")

    def _op_observe_process_exit(self, args):
        exited = {args["process"]}
        processes = self._state["processes"]
        if self.variant == "parent_exit_as_tree_stop":
            assumed = set(exited)
            while True:
                children = {name for name, process in processes.items()
                            if process.get("parent") in assumed}
                children.update(child for name in assumed
                                for child in processes[name].get("children", []))
                if children.issubset(assumed):
                    break
                assumed.update(children)
            # This is a deliberately wrong controller inference, not a
            # fixture witness. Actual descendants retain their write ability.
            self._state["control"]["assumed_stopped_processes"] = sorted(assumed)
        for name in exited:
            processes[name]["running"] = False
        for resource, writers in self._state["effective_writers"].items():
            self._state["effective_writers"][resource] = [
                writer for writer in writers if writer not in exited
            ]
        self._observe(args, status="exited", process=args["process"])
