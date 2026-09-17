"""Coding trigger gate: start on a fresh objective, stop at completion."""


def should_start(*, task, facts, new, head, now=None):
    if any(fact["kind"] == "task.completed" for fact in facts):
        return False
    return any(fact["kind"] == "task.objective.set" for fact in new)


def should_continue(*, state):
    if state.get("final") is not None:
        return False
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] == "task.completed" and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
