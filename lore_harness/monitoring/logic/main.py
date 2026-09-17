"""Monitoring action parsing."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") in ("monitor.condition.met", "monitor.condition.expired") and not payload.get("monitor_id"):
            return base.final_fallback(text)
    if action.get("type") == "shell" and not isinstance(action.get("script"), str):
        return base.final_fallback(text)
    return action


def settle(state):
    return []
