"""Target selection and actual capability use for the finite model."""
from copy import deepcopy


class ExecutionOperations:
    def _resolve_target(self, args):
        state = self._state
        name = args.get("target")
        location = args.get("location")
        if name is None:
            candidates = state["locations"].get(location, [])
            if len(candidates) == 1:
                name = candidates[0]
            elif candidates and self.variant == "ambiguous_first_match":
                name = candidates[0]
            else:
                return None, None
        if name not in state["targets"]:
            return None, None
        if location is not None and name not in state["locations"].get(location, []):
            return None, None
        if name not in state["grants"].get(args["principal"], []):
            return None, None
        profile = deepcopy(state["targets"][name])
        actual = state["directory_identity"].get(profile["location"])
        if self.variant != "stale_registration_cache":
            if actual is None or actual != profile["object_identity"]:
                return None, None
        return name, profile

    def _command_object(self, command):
        if "alias" in command:
            return self._state["aliases"].get(command["alias"])
        return command["object"]

    def _can_write(self, profile, command, actual):
        if self.variant == "promote_runtime_worker":
            if profile["profile"] == "restricted-runtime":
                return actual in self._state["objects"]
        if self.variant == "caller_profile_override":
            if profile["profile"] == "unrestricted":
                return actual in self._state["objects"]
        if self.variant == "path_prefix_only" and "alias" in command:
            path = self._state.get("path_strings", {}).get(command["alias"], "")
            prefix = self._state.get("path_policy_prefix")
            return prefix is not None and path.startswith(prefix)
        return actual in profile["writes"]

    def _run_commands(self, args, name, profile, authorized_objects=None):
        state = self._state
        denied = []
        for command in args.get("commands", []):
            if command["op"] == "cd":
                if self.variant == "route_from_cd":
                    candidates = state["locations"].get(command["location"], [])
                    if len(candidates) == 1:
                        name = candidates[0]
                        profile = deepcopy(state["targets"][name])
                continue
            if command["op"] != "write":
                raise ValueError("Only finite write/cd commands are supported")
            actual = self._command_object(command)
            allowed = self._can_write(profile, command, actual)
            if authorized_objects is not None:
                # Deliberate cached-check mutation: actual target is reopened
                # while permission comes from a previously authorized object.
                allowed = bool(authorized_objects)
            if actual not in state["objects"] or not allowed:
                denied.append(actual)
                continue
            self._write_object(actual, command["value"])
        state["counters"]["executions"] += 1
        self._observe(
            args, status="executed", target=name,
            environment=profile["environment"], identity=profile["identity"],
            profile=profile["profile"], handles=profile["handles"],
            denied_writes=denied,
        )

    def _op_execute(self, args):
        name, profile = self._resolve_target(args)
        if profile is None:
            if self.variant != "host_fallback_on_invalid":
                self._observe(args, status="rejected")
                return
            # The bad fallback grants real broad write capability and counts
            # an actual host execution; it is not just a changed status.
            name = "host"
            profile = {
                "environment": "host", "identity": "host-worker",
                "profile": "unrestricted", "handles": [],
                "writes": list(self._state["objects"]),
            }
            self._state["counters"]["host_executions"] += 1
        if self.variant == "caller_profile_override":
            profile.update(deepcopy(args.get("claimed_profile", {})))
        self._run_commands(args, name, profile)

    def _op_prepare_execution(self, args):
        name, profile = self._resolve_target(args)
        actual = self._state["aliases"].get(args["alias"])
        if profile is None or actual not in profile["writes"]:
            self._observe(args, status="rejected")
            return
        request = deepcopy(args)
        request.update(target=name, authorized_object=actual)
        self._prepared[args["request_id"]] = request
        self._observe(args, status="prepared", object=actual)

    def _op_execute_prepared(self, args):
        prepared = self._prepared.get(args["request_id"])
        if prepared is None:
            self._observe(args, status="rejected")
            return
        name, profile = self._resolve_target(prepared)
        actual = self._state["aliases"].get(prepared["alias"])
        changed = actual != prepared["authorized_object"]
        if profile is None or (changed and self.variant != "check_then_reopen_alias"):
            self._observe(args, status="rejected")
            return
        request = {
            "commands": [{"op": "write", "alias": prepared["alias"],
                          "value": prepared["value"]}],
        }
        if "observation" in args:
            request["observation"] = args["observation"]
        cached = None
        if self.variant == "check_then_reopen_alias":
            cached = [prepared["authorized_object"]]
        self._run_commands(request, name, profile, cached)

    def _op_start_process(self, args):
        profile = self._state["targets"][args["target"]]
        inherited = args["parent_handles"]
        if self.variant != "inherit_parent_handles":
            inherited = [h for h in inherited if h in profile["handles"]]
        process = {
            "identity": profile["identity"], "handles": deepcopy(inherited),
            "running": True, "parent": None, "children": [],
        }
        self._state["processes"][args["process"]] = process
        self._observe(args, **process)

    def _op_start_child(self, args):
        parent = self._state["processes"][args["parent"]]
        child = {
            "identity": parent["identity"], "handles": deepcopy(parent["handles"]),
            "running": parent["running"], "parent": args["parent"],
            "children": [],
        }
        self._state["processes"][args["process"]] = child
        parent.setdefault("children", []).append(args["process"])
        self._observe(args, **child)

    def _op_use_handle(self, args):
        process = self._state["processes"][args["process"]]
        permitted = self._state["handle_permissions"].get(args["handle"], [])
        allowed = (process["running"] and args["handle"] in process["handles"]
                   and args["action"] in permitted)
        if allowed and args["action"] == "register":
            self._state["registry"][args["process"]] = {
                "via_handle": args["handle"],
            }
        self._observe(args, status="allowed" if allowed else "rejected")

    def _op_update_registration(self, args):
        profile = self._state["targets"][args["target"]]
        writes = args["requested_writes"]
        if not set(writes).issubset(profile["writes"]):
            self._observe(args, status="rejected")
            return
        actual = self._state["directory_identity"].get(profile["location"])
        if actual is None or actual != args["directory_identity"]:
            self._observe(args, status="rejected")
            return
        profile["object_identity"] = actual
        profile["writes"] = deepcopy(writes)
        self._state["bindings"][args["target"]] = args["binding"]
        self._observe(args, status="updated")
