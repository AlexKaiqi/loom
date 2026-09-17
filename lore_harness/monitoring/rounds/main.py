"""Monitoring trigger gate: time- or signal-driven, never a polling loop.

The runtime hands the current epoch to `should_start`; the harness decides whether
the condition is due. Between Rounds the task is pure data (zero residency).
"""


def _monitor_state(facts):
    condition, signals, closed = None, [], False
    for fact in facts:
        if fact["kind"] == "monitor.condition.set":
            condition = fact["payload"]
        elif fact["kind"] == "monitor.signal":
            signals.append(fact["payload"])
        elif fact["kind"] in ("monitor.condition.met", "monitor.condition.expired"):
            closed = True
    return condition, signals, closed


def should_start(*, task, facts, new, head, now=None):
    condition, signals, closed = _monitor_state(facts)
    if condition is None or closed:
        return False
    monitor_id = condition.get("monitor_id")
    if any(signal.get("monitor_id") == monitor_id for signal in signals):
        return True
    deadline = condition.get("deadline_epoch")
    if deadline is not None and now is not None and int(now) >= int(deadline):
        return True
    return False


def should_continue(*, state):
    if state.get("final") is not None:
        return False
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] in ("monitor.condition.met", "monitor.condition.expired") and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
