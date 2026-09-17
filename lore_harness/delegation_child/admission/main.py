"""Child admission: only an admitted delegation from the parent."""
import lore_harness_base as base

ACCEPTED = ("work.delegated",)

accept = base.make_accept(*ACCEPTED)
