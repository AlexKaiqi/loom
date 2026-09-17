"""Goal-mode action parsing and settle hook.

The interaction format (single JSON object) is this harness's choice, not a
runtime protocol. `parse` must be shape-strict; malformed output is treated as a
final text rather than guessed into an action.
"""
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
    """No implicit completion: only explicit emit actions produce facts."""
    return []
