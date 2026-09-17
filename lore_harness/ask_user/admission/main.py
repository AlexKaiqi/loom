"""Admission rule for ask-user mode."""
import lore_harness_base as base

ACCEPTED = ("task.objective.set", "ask.answered")

accept = base.make_accept(*ACCEPTED)
