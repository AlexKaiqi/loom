"""Parent admission: objectives from outside, reports from the delegated child."""
import lore_harness_base as base

ACCEPTED = ("task.objective.set", "task.reported")

accept = base.make_accept(*ACCEPTED)
