"""Admission rule for archive mode."""

ACCEPTED = ("archive.requested",)


def accept(*, kind, payload):
    return kind in ACCEPTED
