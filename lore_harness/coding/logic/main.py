"""Coding action parsing: strict shell/emit shapes."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "shell":
        if not isinstance(action.get("script"), str):
            return base.final_fallback(text)
        if action.get("target") is not None and not isinstance(action["target"], str):
            return base.final_fallback(text)
    if action.get("type") == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "code.test.declared" and payload.get("outcome") not in ("pass", "fail"):
            return base.final_fallback(text)
        if action.get("kind") == "code.change.declared" and not payload.get("files"):
            return base.final_fallback(text)
        if "kind" not in action or not isinstance(payload, dict):
            return base.final_fallback(text)
    return action


def settle(state):
    return []
