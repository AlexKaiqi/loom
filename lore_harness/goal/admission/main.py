"""Admission rule for goal mode: accept only declared external kinds."""
import lore_harness_base as base

ACCEPTED = ("work.objective.set", "user.message")

accept = base.make_accept(*ACCEPTED)
