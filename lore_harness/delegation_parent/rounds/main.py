"""Parent trigger gate: delegate once, then wait as data for the child's report."""
import lore_harness_base as base


def _facts(facts):
    folded = base.fold(facts, latest=("task.objective.set", "task.delegated", "task.reported"),
                       flags=("task.completed",))
    return (folded["task.objective.set"], folded["task.delegated"], folded["task.reported"],
            folded["task.completed"])


def should_start(*, task, facts, new, head, now=None):
    objective, delegated, reported, completed = _facts(facts)
    if completed or objective is None:
        return False
    if delegated is None:
        return any(fact["kind"] == "task.objective.set" for fact in new)
    return any(fact["kind"] == "task.reported" for fact in new)


def should_continue(*, state):
    """Only real progress ends the Round: a delegation or a completion.

    A bare `final` (e.g. "I cannot confirm the report") does not end the Round,
    so the model must either delegate or acknowledge the admitted report.
    """
    return base.continue_when(state, ("task.delegated", "task.completed"), stop_on_final=False)
