"""Admission rule for coding mode."""
import lore_harness_base as base

ACCEPTED = ("task.objective.set",)

accept = base.make_accept(*ACCEPTED)
