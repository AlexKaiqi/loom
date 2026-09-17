"""Coding trigger gate: start on a fresh objective, stop at completion."""
import lore_harness_base as base


def should_start(*, task, facts, new, head, now=None):
    if not base.start_unless_completed(facts):
        return False
    return any(fact["kind"] == "task.objective.set" for fact in new)


def should_continue(*, state):
    return base.continue_when(state, ("task.completed",))
