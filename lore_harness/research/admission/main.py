"""Admission rule for research mode."""

ACCEPTED = ("research.question.set",)


def accept(*, kind, payload):
    return kind in ACCEPTED
