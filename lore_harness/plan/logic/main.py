"""Plan-mode action parsing and derived completion."""
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
        if "kind" not in action or not isinstance(action.get("payload", {}), dict):
            return {"type": "final", "text": raw}
    if action["type"] == "shell" and not isinstance(action.get("script"), str):
        return {"type": "final", "text": raw}
    return action


def settle(state):
    """Derive plan.completed once every declared stage has a completion fact."""
    facts = state.get("facts", [])
    spec, completed, done = None, [], False
    for fact in facts:
        if fact["kind"] in ("plan.created", "plan.revised"):
            spec = fact["payload"]
        elif fact["kind"] == "plan.stage.completed":
            stage_id = fact["payload"].get("stage_id")
            if stage_id not in completed:
                completed.append(stage_id)
        elif fact["kind"] == "plan.completed":
            done = True
    if done or not spec:
        return []
    stage_ids = [s.get("id") for s in spec.get("stages", [])]
    if stage_ids and all(stage_id in completed for stage_id in stage_ids):
        return [{"kind": "plan.completed", "payload": {"plan_id": spec.get("plan_id"), "stages": completed}}]
    return []
