"""Kernel round gate: wake on a new objective, stop on completion or final."""
import lore_harness_base as base


def should_start(*, work, facts, new, head, now=None):
    if not base.start_unless_completed(facts):
        return False
    return any(fact["kind"] == "work.objective.set" for fact in new)


def should_continue(*, state):
    return base.continue_when(state, ("work.completed",))
