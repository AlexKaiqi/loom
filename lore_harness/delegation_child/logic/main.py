"""Child logic: report parsing, and completion derived from the report itself."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "task.reported" and not payload.get("result_ref"):
            return base.final_fallback(text)
    if action.get("type") == "shell" and not isinstance(action.get("script"), str):
        return base.final_fallback(text)
    return action


def settle(state):
    """A reported result completes the child's own work."""
    facts = state.get("facts", [])
    if any(fact["kind"] == "task.completed" for fact in facts):
        return []
    reported = [f for f in facts if f["kind"] == "task.reported"]
    if not reported:
        return []
    return [{"kind": "task.completed",
             "payload": {"evidence_refs": (reported[-1]["payload"].get("evidence_refs") or [])}}]
