"""Child trigger gate: start on an admitted delegation, stop once reported."""
import lore_harness_base as base


def _facts(facts):
    folded = base.fold(facts, latest=("work.delegated",), flags=("work.reported", "work.completed"))
    return folded["work.delegated"], folded["work.reported"], folded["work.completed"]


def should_start(*, work, facts, new, head, now=None):
    delegated, reported, completed = _facts(facts)
    if delegated is None or reported or completed:
        return False
    return any(fact["kind"] == "work.delegated" for fact in new)


def should_continue(*, state):
    return base.continue_when(state, ("work.reported",))
