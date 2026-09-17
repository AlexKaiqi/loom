"""Research trigger gate: keep rounds going while material arrives, stop at saturation."""


def _state(facts):
    question, sources, findings, recall, saturated, completed = None, [], [], [], False, False
    for fact in facts:
        kind = fact["kind"]
        if kind == "research.question.set":
            question = fact["payload"]
        elif kind == "research.source.added":
            sources.append(fact["payload"])
        elif kind == "research.finding.recorded":
            findings.append(fact["payload"])
        elif kind == "sys.recall.result":
            recall.append(fact["payload"])
        elif kind == "research.saturation.reached":
            saturated = True
        elif kind == "task.completed":
            completed = True
    return question, sources, findings, recall, saturated, completed


def should_start(*, task, facts, new, head, now=None):
    question, _sources, _findings, _recall, _saturated, completed = _state(facts)
    if question is None or completed or not new:
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
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] in ("research.finding.recorded", "research.saturation.reached") and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
