"""Plan-mode trigger gate and per-Round end condition.

One Round advances exactly one stage: the Round ends as soon as this Round has
declared a stage completed. `plan.completed` is a derived declaration produced by
`logic.settle` when every stage is done, and stops further Rounds.
"""
import lore_harness_base as base


def _state(facts):
    folded = base.fold(facts, latest=("plan.created", "plan.revised"),
                       collect=("plan.stage.completed",), flags=("plan.completed",))
    spec = folded["plan.created"] or folded["plan.revised"]
    completed = [p.get("stage_id") for p in folded["plan.stage.completed"]]
    return spec, completed, folded["plan.completed"]


def should_start(*, task, facts, new, head, now=None):
    spec, _completed, done = _state(facts)
    if done or spec is None:
        return False
    return any(fact["kind"] in ("plan.created", "plan.revised", "plan.stage.completed") for fact in new)


def should_continue(*, state):
    return base.continue_when(state, ("plan.stage.completed",))
