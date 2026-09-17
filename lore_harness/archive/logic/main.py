"""Archive-mode action parsing; no implicit fold."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") != "archive.performed" or not isinstance(payload.get("moved"), list):
            return base.final_fallback(text)
        if payload.get("mode") == "lossy" and not payload.get("fold_digest"):
            return base.final_fallback(text)
    if action.get("type") == "shell" and not isinstance(action.get("script"), str):
        return base.final_fallback(text)
    return action


def settle(state):
    return []
