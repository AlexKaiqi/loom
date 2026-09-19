"""Kernel parse: one JSON action. No implicit completion."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "emit":
        if "kind" not in action or not isinstance(action.get("payload", {}), dict):
            return base.final_fallback(text)
    if action.get("type") == "shell" and not isinstance(action.get("script"), str):
        return base.final_fallback(text)
    return action


def settle(state):
    return []
