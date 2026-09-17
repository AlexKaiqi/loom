"""Child admission: only an admitted delegation from the parent."""
import lore_harness_base as base

ACCEPTED = ("task.delegated",)

accept = base.make_accept(*ACCEPTED)
