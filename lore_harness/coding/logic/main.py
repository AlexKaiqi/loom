"""Coding action parsing: strict shell/emit shapes."""
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
    if action["type"] == "shell":
        if not isinstance(action.get("script"), str):
            return {"type": "final", "text": raw}
        if action.get("target") is not None and not isinstance(action["target"], str):
            return {"type": "final", "text": raw}
    if action["type"] == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "code.test.declared" and payload.get("outcome") not in ("pass", "fail"):
            return {"type": "final", "text": raw}
        if action.get("kind") == "code.change.declared" and not payload.get("files"):
            return {"type": "final", "text": raw}
        if "kind" not in action or not isinstance(payload, dict):
            return {"type": "final", "text": raw}
    return action


def settle(state):
    return []
