"""Admission rule for monitoring mode."""
import lore_harness_base as base

ACCEPTED = ("monitor.condition.set", "monitor.signal")

accept = base.make_accept(*ACCEPTED)
