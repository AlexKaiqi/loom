"""Admission rule for system design: objectives and amendment decisions come from outside."""

ACCEPTED = ("design.objective.set", "design.amendment.requested", "design.amendment.accepted")


def accept(*, kind, payload):
    return kind in ACCEPTED
