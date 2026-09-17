"""Child trigger gate: start on an admitted delegation, stop once reported."""
import lore_harness_base as base


def _facts(facts):
    folded = base.fold(facts, latest=("task.delegated",), flags=("task.reported", "task.completed"))
    return folded["task.delegated"], folded["task.reported"], folded["task.completed"]


def should_start(*, task, facts, new, head, now=None):
    delegated, reported, completed = _facts(facts)
    if delegated is None or reported or completed:
        return False
    return any(fact["kind"] == "task.delegated" for fact in new)


def should_continue(*, state):
    return base.continue_when(state, ("task.reported",))
