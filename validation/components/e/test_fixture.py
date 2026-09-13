"""Input authority and syscall-observer preparation, not a passing E surrogate."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from fixture import reference_checker
from input_cases import expected_input,FsyncObserver
from support import sha
class FixturePreparation(unittest.TestCase):
    def test_actual_input_binding_authority(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/"input";directory.mkdir()
            context={"surface_ref":{"id":"surface"},"previous_session_ref":{"id":"old"},"execution_targets":[{"id":"workspace"}]}
            files=expected_input("i1","n1","alice",1,0,0,{},[],context)
            for name,raw in files.items():(directory/name).write_bytes(raw)
            st=directory.stat();ref={"owner":"E","kind":"input","id":"i1","path":str(directory),"root":{"dev":st.st_dev,"ino":st.st_ino},"manifest_sha256":sha(files["manifest.json"])}
            binding={"namespace":"n1","source":"alice","start_sequence":1,"filters":{},"page_size":128,**context}
            checker=reference_checker(root,"nats://unused")
            self.assertTrue(checker(ref,"input",{"invocation_id":"i1","binding":binding}))
            self.assertFalse(checker(ref,"receipt"))
            for field,value in [("source","bob"),("page_size",2),("previous_session_ref",{"id":"other"}),("execution_targets",[])]:
                self.assertFalse(checker(ref,"input",{"invocation_id":"i1","binding":{**binding,field:value}}))
            path=directory/"invocation.json";original=path.read_bytes();path.write_bytes(original.replace(b"alice",b"bobby"))
            self.assertEqual(path.stat().st_size,len(original));self.assertFalse(checker(ref,"input",{"invocation_id":"i1","binding":binding}))
    def test_actual_fsync_witness(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"file"
            with FsyncObserver() as observer:
                with path.open("wb") as file:file.write(b"original");file.flush();os.fsync(file.fileno())
                directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory)
                finally:os.close(directory)
            self.assertEqual(len(observer.calls),2)
            self.assertEqual(observer.calls[0]["sha256"],sha(b"original"))
            self.assertNotEqual(observer.calls[0]["sha256"],sha(b"modified"))
            self.assertTrue(observer.calls[1]["is_dir"])
if __name__=="__main__":unittest.main()
