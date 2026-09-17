"""Child logic: report parsing, and completion derived from the report itself."""
import json


def parse(text):
    raw = (text or "").strip()
    if not raw:
        return {"type": "none"}
    candidate = raw
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return {"type": "final", "text": raw}
    action = value.get("action", value) if isinstance(value, dict) else None
    if not isinstance(action, dict) or "type" not in action:
        return {"type": "final", "text": raw}
    if action["type"] == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "task.reported" and not payload.get("result_ref"):
            return {"type": "final", "text": raw}
    if action["type"] == "shell" and not isinstance(action.get("script"), str):
        return {"type": "final", "text": raw}
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
