"""Admission rule for coding mode."""

ACCEPTED = ("task.objective.set",)


def accept(*, kind, payload):
    return kind in ACCEPTED
