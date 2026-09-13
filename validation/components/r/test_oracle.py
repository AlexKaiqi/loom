import copy
import unittest
from oracle import exact_binding, responsibility, exact_identity_counts, fair_prefix

class OraclePreparation(unittest.TestCase):
    def test_original_and_association_changes(self):
        original={"principal":"a", "namespace":"n", "kind":"step", "payload":{"source_ref":"r1","harness_ref":"h1","input_ref":"i1","value":1}}
        exact_binding(copy.deepcopy(original), original)
        for field in ("source_ref", "harness_ref", "input_ref", "value"):
            changed=copy.deepcopy(original);changed["payload"][field]="changed"
            with self.subTest(field=field),self.assertRaises(AssertionError):exact_binding(changed,original)
        for field in ("principal","namespace","kind"):
            changed=copy.deepcopy(original);changed[field]="changed"
            with self.subTest(field=field),self.assertRaises(AssertionError):exact_binding(changed,original)
        changed=copy.deepcopy(original);changed["payload"]["value"]=True
        with self.assertRaises(AssertionError):exact_binding(changed,original)
    def test_orphan_and_empty_rejected(self):
        responsibility([{"old":1,"successor":0,"saved_stop":0},{"old":0,"successor":1,"saved_stop":0}])
        for bad in ([],[{"old":0,"successor":0,"saved_stop":0}],[{"old":False,"successor":True,"saved_stop":0}]):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):responsibility(bad)
    def test_duplicate_missing_and_starvation(self):
        exact_identity_counts(["a","b"],["a","b"])
        for bad in (["a","a"],["a"],[]):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):exact_identity_counts(bad,["a","b"])
        fair_prefix(["a","b","c","a"],["a","b","c"])
        changed_order=["a","b","c","c","b","a"]
        with self.assertRaises(AssertionError):
            for start in range(len(changed_order)-2):fair_prefix(changed_order[start:start+3],["a","b","c"])
        for bad in (["a","a","c"],[]):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):fair_prefix(bad,["a","b","c"])

if __name__=="__main__":unittest.main()
