"""ask-user action parsing: ask.requested must carry a question."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "ask.requested" and not (payload.get("ask_id") and payload.get("question")):
            return base.final_fallback(text)
    if action.get("type") == "shell" and not isinstance(action.get("script"), str):
        return base.final_fallback(text)
    return action


def settle(state):
    return []
