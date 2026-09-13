"""Finite strategy semantics, using only explicit inputs and generic transitions."""
from copy import deepcopy

class StrategyModel:
    def __init__(self, initial_state, variant=None):
        self.state = deepcopy(initial_state)
        self.variant = variant

    def snapshot(self):
        return deepcopy(self.state)

    def apply(self, op, args):
        s = self.state
        if op == "evaluate_feedback":
            if args["feedback"] != "confirmed_tool":
                raise ValueError("this finite operation requires a confirmed feedback")
            decision = args["external_decision"]
            if decision not in {"continue", "stop", "wait"}:
                raise ValueError("unknown externally accepted decision")
            s["decisions"][args["invocation"]] = "continue" if self.variant == "hardcode_continue" else decision
        elif op == "interpret_output":
            valid = args["complete"] and args["format_valid"] and not args["pending_request"]
            if self.variant == "accept_incomplete_final":
                valid = True
            target = "accepted_answers" if valid and args["kind"] == "final" else "rejected_outputs"
            s[target].append(args["output_id"])
        elif op == "stop_for_budget":
            s["series"][args["invocation"]].update(state="stopped", reason="budget")
            if self.variant == "stop_means_surface_success":
                s["surface_terminal"] = True
                s["business_success"] = True
        elif op == "start_invocation":
            s["series"][args["invocation"]] = {"state": "rejected" if s["surface_terminal"] else "active"}
        else:
            raise ValueError(f"unknown strategy operation: {op}")
