"""Parent trigger gate: delegate once, then wait as data for the child's report."""


def _facts(facts):
    objective, delegated, reported, completed = None, None, None, False
    for fact in facts:
        if fact["kind"] == "task.objective.set":
            objective = fact["payload"]
        elif fact["kind"] == "task.delegated":
            delegated = fact["payload"]
        elif fact["kind"] == "task.reported":
            reported = fact["payload"]
        elif fact["kind"] == "task.completed":
            completed = True
    return objective, delegated, reported, completed


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
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] in ("task.delegated", "task.completed") and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
