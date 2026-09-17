"""Goal-mode trigger gate.

Start a Round only on a fresh objective/message, and never after the harness has
already declared completion. Completion is a declaration here, not a runtime
terminal state (landing §4.3 boundary 1-3).
"""


def should_start(*, task, facts, new, head, now=None):
    if any(fact["kind"] == "task.completed" for fact in facts):
        return False
    return any(fact["kind"] in ("task.objective.set", "user.message") for fact in new)


def should_continue(*, state):
    """Stop on an explicit final proposal, or once completion has been declared."""
    if state.get("final") is not None:
        return False
    return not any(fact["kind"] == "task.completed" for fact in state.get("facts", []))
