"""Child trigger gate: start on an admitted delegation, stop once reported."""


def _facts(facts):
    delegated, reported, completed = None, False, False
    for fact in facts:
        if fact["kind"] == "task.delegated":
            delegated = fact["payload"]
        elif fact["kind"] == "task.reported":
            reported = True
        elif fact["kind"] == "task.completed":
            completed = True
    return delegated, reported, completed


def should_start(*, task, facts, new, head, now=None):
    delegated, reported, completed = _facts(facts)
    if delegated is None or reported or completed:
        return False
    return any(fact["kind"] == "task.delegated" for fact in new)


def should_continue(*, state):
    if state.get("final") is not None:
        return False
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] == "task.reported" and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
