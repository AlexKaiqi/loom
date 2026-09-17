"""Admission rule for research mode."""
import lore_harness_base as base

ACCEPTED = ("research.question.set",)

accept = base.make_accept(*ACCEPTED)
