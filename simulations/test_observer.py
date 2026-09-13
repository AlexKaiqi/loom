"""Reject the corruptions preregistered in simulation-protocol.md."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from .observer import ProtocolError, compare, evaluate, validate_inventory, verify_hashes
from .run_g1 import trajectories, variants, run_one
from .strategy import StrategyModel

class ObserverRejectionTests(unittest.TestCase):
    def test_type_sensitive_truth(self):
        self.assertFalse(compare(True, "eq", 1))
        self.assertFalse(compare(None, "eq", "null"))
        self.assertTrue(compare({"value": 10}, "eq", {"value": 10}))

    def test_missing_observation_not_default_pass(self):
        with self.assertRaises(ProtocolError):
            evaluate([{"path": "result", "op": "eq", "value": None}], {"initial": {}})

    def test_all_checks_initial_and_every_transition(self):
        checks = evaluate([{"at": "all", "path": "effects", "op": "eq", "value": 1}], {"initial": {"effects": 1}, "a1": {"effects": 2}, "a2": {"effects": 1}})
        self.assertEqual(len(checks), 3)
        self.assertEqual([r["passed"] for r in checks], [True, False, True])

    def test_empty_assertions_and_missing_trace_fail(self):
        with self.assertRaises(ProtocolError):
            evaluate([], {"initial": {}})
        with self.assertRaises(ProtocolError):
            evaluate([{"path": "result", "op": "eq", "value": 1}], {})

    def test_unknown_comparator_and_missing_checkpoint_fail(self):
        for assertion in [{"path": "v", "op": "approximately", "value": 1}, {"at": "a2", "path": "v", "op": "eq", "value": 1}]:
            with self.assertRaises(ProtocolError):
                evaluate([assertion], {"initial": {"v": 1}})

    def test_zero_missing_duplicate_and_extra_cases_fail(self):
        for expected, observed in [([], []), (["a", "b"], ["a"]), (["a"], ["a", "a"]), (["a"], ["a", "b"])]:
            with self.assertRaises(ProtocolError):
                validate_inventory(expected, observed)

    def test_changed_version_and_missing_file_fail(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / "artifact"
            file.write_text("original")
            bindings = {"artifact": sha256(file.read_bytes()).hexdigest()}
            verify_hashes(root, bindings)
            file.write_text("changed")
            with self.assertRaises(ProtocolError):
                verify_hashes(root, bindings)
            file.unlink()
            with self.assertRaises(ProtocolError):
                verify_hashes(root, bindings)

    def test_frozen_boundary_nested_inventory_is_not_skipped(self):
        suite = json.loads((Path(__file__).resolve().parents[1] / "design/g1/cases-boundaries.json").read_text())
        cases = list(trajectories(suite))
        self.assertEqual(len(cases), 22)
        self.assertEqual(sum(len(variants(c)) for c in cases), 23)
        self.assertIn("G1-BND-018--missing-pinned-harness", [c["id"] for c in cases])
        self.assertEqual(sum(len(c["expected"]) for c in cases), 136)

    def test_unknown_operation_rejected(self):
        with self.assertRaises(ValueError):
            StrategyModel({}).apply("not_registered", {})

    def test_model_crash_is_not_a_killed_semantic_mutation(self):
        class CrashingModel:
            def __init__(self, initial_state, variant=None):
                pass
            def snapshot(self):
                return {"value": 1}
            def apply(self, op, args):
                raise RuntimeError("injected crash")
        case = {"id": "fixture", "initial_state": {}, "actions": [{"op": "x", "args": {}}], "expected": [{"id": "E1", "path": "value", "op": "eq", "value": 1}]}
        with TemporaryDirectory() as temporary:
            result = run_one(CrashingModel, case, {}, {"name": "crash", "must_violate": ["E1"]}, (), Path(temporary)/"record.json")
            self.assertEqual(result["status"], "FAIL")
            self.assertNotIn("mutation_rejected", result)

if __name__ == "__main__":
    unittest.main()
