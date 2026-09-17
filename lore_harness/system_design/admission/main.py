"""Admission rule for system design: objectives and amendment decisions come from outside."""
import lore_harness_base as base

ACCEPTED = ("design.objective.set", "design.amendment.requested", "design.amendment.accepted")

accept = base.make_accept(*ACCEPTED)
