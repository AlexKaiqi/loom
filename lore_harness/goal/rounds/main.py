"""Goal-mode trigger gate.

Start a Round only on a fresh objective/message, and never after the harness has
already declared completion. Completion is a declaration here, not a runtime
terminal state (landing §4.3 boundary 1-3).
"""
import lore_harness_base as base

WAKE_KINDS = ("work.objective.set", "user.message")


def should_start(*, work, facts, new, head, now=None):
    if not base.start_unless_completed(facts):
        return False
    return any(fact["kind"] in WAKE_KINDS for fact in new)


def should_continue(*, state):
    """Stop on an explicit final proposal, or once completion has been declared."""
    return base.continue_when(state, ("work.completed",), since=0)
