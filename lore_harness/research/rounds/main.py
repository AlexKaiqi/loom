"""Research trigger gate: keep rounds going while material arrives, stop at saturation."""
import lore_harness_base as base


def _state(facts):
    folded = base.fold(facts, latest=("research.question.set",),
                       collect=("research.source.added", "research.finding.recorded", "sys.recall.result"),
                       flags=("research.saturation.reached", "task.completed"))
    return folded


def should_start(*, task, facts, new, head, now=None):
    folded = _state(facts)
    if folded["research.question.set"] is None or folded["task.completed"] or not new:
        return False
    # Only `task.completed` ends the work. A saturation CLAIM does not: the harness
    # derives saturation from verified evidence, so an early claim must not freeze
    # a task that still needs sources.
    return True


def should_continue(*, state):
    """Only a recorded finding or saturation ends the Round.

    A bare `final` (e.g. the answer written only in the reply) is not progress:
    the answer must exist as a finding fact backed by real files.
    """
    return base.continue_when(state, ("research.finding.recorded", "research.saturation.reached"),
                              stop_on_final=False)
