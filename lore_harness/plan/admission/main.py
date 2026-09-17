"""Admission rule for plan mode."""

ACCEPTED = ("plan.created", "plan.revised")


def accept(*, kind, payload):
    return kind in ACCEPTED
