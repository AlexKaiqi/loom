"""Runner controls only; no EventService model or fake passing implementation."""
import unittest
from run_contract import verdict,EXPECTED
class RunnerPreparation(unittest.TestCase):
    def result(self):
        result=unittest.TestResult();result.testsRun=15;return result
    def test_complete_control(self):
        self.assertTrue(verdict(self.result(),sorted(EXPECTED)))
    def test_zero_missing_duplicate_inventory(self):
        self.assertFalse(verdict(self.result(),[]))
        self.assertFalse(verdict(self.result(),sorted(EXPECTED)[:-1]))
        self.assertFalse(verdict(self.result(),sorted(EXPECTED)+["E01"]))
        result=self.result();result.testsRun=0;self.assertFalse(verdict(result,sorted(EXPECTED)))
    def test_error_skip_and_bad_result_propagate(self):
        for field in ("errors","failures","skipped","expectedFailures","unexpectedSuccesses"):
            result=self.result();getattr(result,field).append(("synthetic-control","deliberate"))
            self.assertFalse(verdict(result,sorted(EXPECTED)),field)
if __name__=="__main__":unittest.main()
