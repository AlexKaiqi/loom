"""Archive trigger gate: explicit request, or a declared context threshold crossed.

The threshold is harness configuration (`config.json`), never runtime semantics.
"""
from pathlib import Path

import lore_harness_base as base

CONFIG = Path(__file__).resolve().parents[1] / "config.json"


def _last(facts, kind):
    return next((fact for fact in reversed(facts) if fact["kind"] == kind), None)


def should_start(*, task, facts, new, head, now=None):
    if any(fact["kind"] == "archive.requested" for fact in new):
        return True
    usage = _last(facts, "sys.context.usage")
    if usage is None or usage["payload"].get("projection_bytes", 0) < base.load_config({"threshold_bytes": 10 ** 9}, config_path=CONFIG).get("threshold_bytes"):
        return False
    performed = _last(facts, "archive.performed")
    return not (performed is not None and performed["seq"] > usage["seq"])


def should_continue(*, state):
    """The Round may only end once the fold has been declared as a fact.

    A `final` proposal is not enough: a filesystem change without an
    `archive.performed` declaration would be a side channel (design §4.4 E2/E5).
    """
    return base.continue_when(state, ("archive.performed",), stop_on_final=False)
