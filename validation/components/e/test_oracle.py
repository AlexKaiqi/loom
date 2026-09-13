import tempfile
import unittest
from pathlib import Path
from oracle import raw_history,input_files,application_origin

class OraclePreparation(unittest.TestCase):
    def test_wrong_identity_content_and_gap(self):
        original=[{"sequence":1,"subject":"lore.n.app.a.r1","data":b"A"},{"sequence":2,"subject":"lore.n.app.a.r2","data":b"B"}]
        raw_history(original,original)
        for bad in ([],original[:1],[original[0],original[0]],[dict(original[0],data=b"Z"),original[1]],list(reversed(original))):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):raw_history(bad,original)
    def test_actual_missing_and_equal_length_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"events.jsonl"; p.write_bytes(b'A\n'); wanted={"events.jsonl":b'A\n'}
            input_files(tmp,wanted);p.write_bytes(b'B\n')
            with self.assertRaises(AssertionError):input_files(tmp,wanted)
            p.unlink()
            with self.assertRaises(AssertionError):input_files(tmp,wanted)
            with self.assertRaises(AssertionError):input_files(tmp,{})
    def test_application_never_runtime(self):
        application_origin({"origin":"application","source":"a","name":"done"},"a")
        for bad in ({"origin":"runtime","source":"a"},{"origin":"application","source":"b"},{}):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):application_origin(bad,"a")

if __name__=="__main__":unittest.main()
