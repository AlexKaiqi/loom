"""Liveness fixture rounds role: a Round ends only when the model proposes final.

should_start accepts any new facts, so the offline driver wakes the Round by
admitting a liveness.request fact; trigger plumbing is bypassed on purpose.
"""


def should_continue(*, state):
    return state.get("final") is None


def should_start(*, task, facts, new, head, now):
    return bool(new)
