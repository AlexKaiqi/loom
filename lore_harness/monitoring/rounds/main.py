"""Monitoring trigger gate: time- or signal-driven, never a polling loop.

The runtime hands the current epoch to `should_start`; the harness decides whether
the condition is due. Between Rounds the work is pure data (zero residency).
"""
import lore_harness_base as base


def _monitor_state(facts):
    folded = base.fold(facts, latest=("monitor.condition.set",), collect=("monitor.signal",),
                       flags=("monitor.condition.met", "monitor.condition.expired"))
    return folded["monitor.condition.set"], folded["monitor.signal"], (
        folded["monitor.condition.met"] or folded["monitor.condition.expired"])


def should_start(*, work, facts, new, head, now=None):
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
    return base.continue_when(state, ("monitor.condition.met", "monitor.condition.expired"))
