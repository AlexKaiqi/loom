"""Exercise complete pipeline omissions and stored-evidence corruption."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import py_compile
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest
import uuid
from .audit import audit_batch, load_plan
from .frozen_loader import FrozenModels
from .observer import ProtocolError

ROOT = Path(__file__).resolve().parents[1]

class EvidenceAuditTests(unittest.TestCase):
    def boundary_omission(self, alteration):
        batch = "audit-probe-"+uuid.uuid4().hex
        script = "from simulations import run_g1 as r; import sys; "+alteration+"; sys.exit(r.run(['boundaries'], '"+batch+"'))"
        result = subprocess.run([sys.executable,"-c",script],cwd=ROOT,text=True,capture_output=True)
        self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn("missing, duplicate or extra case execution", result.stdout)

    def test_actual_enumerator_omits_extra_trajectory(self):
        self.boundary_omission("original=r.trajectories; r.trajectories=lambda suite: (c for c in original(suite) if '--' not in c['id'])")

    def test_actual_enumerator_omits_additional_mechanism(self):
        self.boundary_omission("r.variants=lambda case: [case['known_bad_variant']]")

    def corruption(self, mutation, refresh_hash=True):
        summary = json.loads((ROOT/'simulations/evidence/g1-001/summary.json').read_text())
        row = deepcopy(next(r for r in summary['runs'] if r['case']=='G1-STR-001' and r['variant'] is None))
        plan, _ = load_plan(ROOT, ['strategy'])
        plan = [r for r in plan if r['run_id']==row['run_id']]
        record = json.loads((ROOT/'simulations/evidence/g1-001'/row['artifact']).read_text())
        with TemporaryDirectory() as temporary:
            output = Path(temporary)
            path = output/row['artifact']
            mutation(record)
            path.write_text(json.dumps(record))
            if refresh_hash:
                row['sha256'] = sha256(path.read_bytes()).hexdigest()
            errors = audit_batch(ROOT, output, {'runs':[row]}, plan)
            self.assertTrue(errors, 'corrupt raw evidence was accepted')

    def test_raw_tampering_even_with_updated_report_digest_fails(self):
        self.corruption(lambda r: r['trace']['a3']['decisions'].update(B='continue'))

    def test_unreported_file_change_fails(self):
        self.corruption(lambda r: r['trace']['a3']['decisions'].update(B='continue'), refresh_hash=False)

    def test_missing_raw_checkpoint_fails(self):
        self.corruption(lambda r: r['trace'].pop('a2'))

    def test_missing_stored_assertion_fails(self):
        self.corruption(lambda r: r['checks'].pop())

    def test_missing_artifact_fails(self):
        plan, _ = load_plan(ROOT, ['strategy'])
        entry=plan[0]
        with TemporaryDirectory() as directory:
            self.assertTrue(audit_batch(ROOT,Path(directory),{'runs':[{'run_id':entry['run_id'],'artifact':'missing.json','sha256':'0'*64}]},[entry]))

    def test_source_changed_after_capture_is_rejected(self):
        name='simulations.capture_probe'
        with TemporaryDirectory() as directory:
            root=Path(directory); path=root/'capture_probe.py'; path.write_text('value=1\n')
            loader=FrozenModels(root,[path])
            try:
                path.write_text('value=2\n')
                with self.assertRaises(ProtocolError):
                    loader.load('capture_probe','value')
            finally:
                loader.close(); sys.modules.pop(name,None)

    def test_stale_bytecode_cannot_change_captured_source_execution(self):
        name='simulations.bytecode_probe'
        with TemporaryDirectory() as directory:
            root=Path(directory); path=root/'bytecode_probe.py'; path.write_text('value=1\n')
            before=path.stat(); py_compile.compile(str(path),doraise=True)
            path.write_text('value=2\n'); os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
            loader=FrozenModels(root,[path])
            try:
                self.assertEqual(loader.load('bytecode_probe','value'),2)
            finally:
                loader.close(); sys.modules.pop(name,None)

if __name__ == '__main__':
    unittest.main()
