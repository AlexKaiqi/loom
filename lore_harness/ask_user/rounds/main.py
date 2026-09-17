"""ask-user trigger gate: wait as data until the open question is answered.

Zero-residency waiting: between Rounds there is no process and no connection —
only facts. A Round only opens on a fresh objective, or on an answer that closes
the currently open question.
"""
import lore_harness_base as base


def _asks(facts):
    asked, answered = [], set()
    for fact in facts:
        if fact["kind"] == "ask.requested":
            asked.append(fact["payload"].get("ask_id"))
        elif fact["kind"] == "ask.answered":
            answered.add(fact["payload"].get("ask_id"))
    return asked, answered


def _open_ask(facts):
    asked, answered = _asks(facts)
    for ask_id in reversed(asked):
        if ask_id not in answered:
            return ask_id
    return None


def should_start(*, work, facts, new, head, now=None):
    if not base.start_unless_completed(facts):
        return False
    open_ask = _open_ask(facts)
    if open_ask is not None:
        return any(
            fact["kind"] == "ask.answered" and fact["payload"].get("ask_id") == open_ask
            for fact in new
        )
    return any(fact["kind"] in ("work.objective.set", "ask.answered") for fact in new)


def should_continue(*, state):
    """The Round ends when it asks a question, completes, or explicitly stops."""
    return base.continue_when(state, ("ask.requested", "work.completed"))
