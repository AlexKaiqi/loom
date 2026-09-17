"""Admission rule for goal mode: accept only declared external kinds."""

ACCEPTED = ("task.objective.set", "user.message")


def accept(*, kind, payload):
    return kind in ACCEPTED
