"""Independent-review counterexamples OR01-04, retained before fixes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest
import uuid
from .observer import evaluate
from .run_g1 import run_one

class ReviewCounterexamples(unittest.TestCase):
    def test_missing_evidence_cannot_kill_semantic_mutant(self):
        class MissingModel:
            def __init__(self, initial_state, variant=None):
                pass
            def snapshot(self):
                return {}
            def apply(self, op, args):
                pass
        case = {"id":"missing-evidence", "initial_state":{}, "actions":[{"op":"observe","args":{}}], "expected":[{"id":"E1","path":"actual_effects","op":"eq","value":1}]}
        with TemporaryDirectory() as directory:
            row = run_one(MissingModel, case, {}, {"name":"omit_observation","must_violate":["E1"]}, (), Path(directory)/"record.json")
            self.assertEqual(row["status"], "FAIL", "missing observation is invalid evidence, not a detected semantic error")

    def test_frozen_string_list_index_is_supported(self):
        checks = evaluate([{"path":["history","0"],"operator":"eq","value":"original"}], {"initial":{"history":["original"]}})
        self.assertTrue(checks[0]["passed"])

    def subprocess_probe(self, alteration):
        batch = "review-probe-"+uuid.uuid4().hex
        script = "from simulations import run_g1 as r; import sys; "+alteration+"; sys.exit(r.run(['strategy'], '"+batch+"'))"
        result = subprocess.run([sys.executable,"-c",script],cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True)
        self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_executor_omission_cannot_shrink_its_own_inventory(self):
        self.subprocess_probe("original=r.trajectories; r.trajectories=lambda suite: iter(list(original(suite))[:-1])")

    def test_unexpected_preloaded_model_is_rejected(self):
        self.subprocess_probe("import simulations.strategy")

if __name__ == "__main__":
    unittest.main()
