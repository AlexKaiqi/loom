"""Guard the declared execution-backend seam against drift (D-X-SEAM-001).

Declaration of record: lore_execution/backend.py and
design/g3/x/backend-seam.md. These checks are static conformance only; they do
not execute a backend and do not constitute component acceptance.
"""
import inspect
import re
from pathlib import Path
import unittest

from lore_execution.backend import (
    BACKEND_OWNED_BUDGET_FIELDS,
    BACKEND_OWNED_ENVIRONMENT,
    BACKEND_OWNED_REQUEST_FIELDS,
    OWNER_INTERNALS,
    SEAM_METHODS,
    SERIALIZED_WRAPPED,
    ExecutionBackend,
)
from lore_execution.requests import FIELDS, MAXIMA
from lore_execution.store import ExecutionStore

ROOT = Path(__file__).resolve().parents[1]


def _parameter_names(function):
    return [p.name for p in inspect.signature(function).parameters.values()]


class ExecutionBackendSeamTests(unittest.TestCase):
    def test_store_satisfies_declared_protocol(self):
        self.assertTrue(issubclass(ExecutionStore, ExecutionBackend))

    def test_every_seam_method_exists_on_store(self):
        for name in SEAM_METHODS:
            self.assertTrue(callable(getattr(ExecutionStore, name, None)), name)

    def test_protocol_parameter_shapes_match_store(self):
        for name in SEAM_METHODS:
            proto = _parameter_names(getattr(ExecutionBackend, name))
            store = _parameter_names(getattr(ExecutionStore, name))
            self.assertEqual(proto, store, name)

    def test_seam_list_covers_protocol_and_stays_exact(self):
        declared = {name for name in dir(ExecutionBackend)
                    if not name.startswith("_") and callable(getattr(ExecutionBackend, name))}
        self.assertEqual(set(SEAM_METHODS), declared)

    def test_profile_owned_contents_exist_in_request_contract(self):
        # requests.py treats readonly_mounts as an optional extension outside
        # FIELDS; backend-owned contents must stay outside the neutral core.
        self.assertTrue(BACKEND_OWNED_REQUEST_FIELDS.isdisjoint(FIELDS))
        self.assertTrue(BACKEND_OWNED_BUDGET_FIELDS <= set(MAXIMA))
        self.assertIsInstance(BACKEND_OWNED_ENVIRONMENT, str)

    def test_upper_layers_use_only_seam_methods_or_owner_internals(self):
        pattern = re.compile(r"self\.(?:x|execution)\.([a-z_]+)")
        callers = ("lore_session/execution.py", "lore_runtime/tool_service.py")
        allowed = set(SEAM_METHODS) | OWNER_INTERNALS
        for relative in callers:
            used = set(pattern.findall((ROOT / relative).read_text()))
            self.assertTrue(used <= allowed, (relative, sorted(used - allowed)))

    def test_duplex_calls_are_the_serialized_wrapped_three(self):
        self.assertEqual(SERIALIZED_WRAPPED,
                         frozenset({"channel_read", "channel_write", "close_stdin"}))


if __name__ == "__main__":
    unittest.main()
