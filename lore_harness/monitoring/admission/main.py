"""Admission rule for monitoring mode."""

ACCEPTED = ("monitor.condition.set", "monitor.signal")


def accept(*, kind, payload):
    return kind in ACCEPTED
