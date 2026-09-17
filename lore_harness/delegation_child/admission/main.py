"""Child admission: only an admitted delegation from the parent."""

ACCEPTED = ("task.delegated",)


def accept(*, kind, payload):
    return kind in ACCEPTED
