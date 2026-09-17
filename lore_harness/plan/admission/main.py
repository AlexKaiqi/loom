"""Admission rule for plan mode."""
import lore_harness_base as base

ACCEPTED = ("plan.created", "plan.revised")

accept = base.make_accept(*ACCEPTED)
