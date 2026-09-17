"""Admission rule for ask-user mode."""

ACCEPTED = ("task.objective.set", "ask.answered")


def accept(*, kind, payload):
    return kind in ACCEPTED
