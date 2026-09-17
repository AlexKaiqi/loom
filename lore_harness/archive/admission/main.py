"""Admission rule for archive mode."""
import lore_harness_base as base

ACCEPTED = ("archive.requested",)

accept = base.make_accept(*ACCEPTED)
