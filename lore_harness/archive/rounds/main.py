"""Archive trigger gate: explicit request, or a declared context threshold crossed.

The threshold is harness configuration (`config.json`), never runtime semantics.
"""
import json
import os

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def _config():
    with open(CONFIG, encoding="utf-8") as fh:
        return json.load(fh)


def _last(facts, kind):
    return next((fact for fact in reversed(facts) if fact["kind"] == kind), None)


def should_start(*, task, facts, new, head, now=None):
    if any(fact["kind"] == "archive.requested" for fact in new):
        return True
    usage = _last(facts, "sys.context.usage")
    if usage is None or usage["payload"].get("projection_bytes", 0) < _config().get("threshold_bytes", 10 ** 9):
        return False
    performed = _last(facts, "archive.performed")
    return not (performed is not None and performed["seq"] > usage["seq"])


def should_continue(*, state):
    """The Round may only end once the fold has been declared as a fact.

    A `final` proposal is not enough: a filesystem change without an
    `archive.performed` declaration would be a side channel (design §4.4 E2/E5).
    """
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] == "archive.performed" and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
