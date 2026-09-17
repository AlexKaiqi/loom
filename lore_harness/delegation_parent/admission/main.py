"""Parent admission: objectives from outside, reports from the delegated child."""

ACCEPTED = ("task.objective.set", "task.reported")


def accept(*, kind, payload):
    return kind in ACCEPTED
