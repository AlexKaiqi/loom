"""Bounded observation window dispatch.

2026-09-14 platform split (recorded revision, see governance/linux-environment.md
and docs/development.md): the lease+inotify implementation is Linux-only and is
kept verbatim in window_linux.py. Non-Linux hosts do not get a substitute
observation mechanism: import stays safe for syntax/import checks, and any
actual window use fails loudly with UNSUPPORTED instead of silently weakening
the capture/publication guarantees. Runtime validation therefore runs in the
Linux container; a darwin kqueue backend is recorded as future work, not part
of the current baseline.
"""
import sys

if sys.platform == "linux":
    from .window_linux import StableWindow
else:  # pragma: no cover - explicit platform limitation, not a fallback
    from .errors import FileError

    class StableWindow:
        """Explicit unsupported-platform window: never observes, never passes."""

        def __init__(self, roots, limits):
            self.roots = list(roots)
            self.limits = limits

        def _unsupported(self):
            raise FileError("UNSUPPORTED",
                            "lease+inotify observation window requires Linux; "
                            "run validation in the Linux container (sys.platform="
                            + sys.platform + ")")

        def tick(self):
            self._unsupported()

        def facts(self):
            self._unsupported()

        def assert_clean(self, exchange=None):
            self._unsupported()

        def verify_roots(self, exchanged=False):
            self._unsupported()

        def __enter__(self):
            self._unsupported()

        def __exit__(self, exc_type, exc, tb):
            return False
