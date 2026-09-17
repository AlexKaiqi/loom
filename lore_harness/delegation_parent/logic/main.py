"""Parent action parsing."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "task.delegated" and not (payload.get("child") and payload.get("scope")):
            return base.final_fallback(text)
    return action


def settle(state):
    return []
