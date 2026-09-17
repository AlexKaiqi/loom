"""Plan-mode trigger gate and per-Round end condition.

One Round advances exactly one stage: the Round ends as soon as this Round has
declared a stage completed. `plan.completed` is a derived declaration produced by
`logic.settle` when every stage is done, and stops further Rounds.
"""


def _state(facts):
    spec, completed = None, []
    for fact in facts:
        if fact["kind"] in ("plan.created", "plan.revised"):
            spec = fact["payload"]
        elif fact["kind"] == "plan.stage.completed":
            completed.append(fact["payload"].get("stage_id"))
        elif fact["kind"] == "plan.completed":
            return spec, completed, True
    return spec, completed, False


def should_start(*, task, facts, new, head, now=None):
    spec, _completed, done = _state(facts)
    if done or spec is None:
        return False
    return any(fact["kind"] in ("plan.created", "plan.revised", "plan.stage.completed") for fact in new)


def should_continue(*, state):
    if state.get("final") is not None:
        return False
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] == "plan.stage.completed" and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
