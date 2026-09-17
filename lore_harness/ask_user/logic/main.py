"""ask-user action parsing: ask.requested must carry a question."""
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
        if action.get("kind") == "ask.requested" and not (payload.get("ask_id") and payload.get("question")):
            return {"type": "final", "text": raw}
    if action["type"] == "shell" and not isinstance(action.get("script"), str):
        return {"type": "final", "text": raw}
    return action


def settle(state):
    return []
