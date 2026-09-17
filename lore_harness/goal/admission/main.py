"""Admission rule for goal mode: accept only declared external kinds."""
import lore_harness_base as base

ACCEPTED = ("task.objective.set", "user.message")

accept = base.make_accept(*ACCEPTED)
