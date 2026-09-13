"""Independent finite checks; no production imports or expected values from SUT."""
import json

def exact_binding(actual, expected):
    if not isinstance(actual, dict) or set(actual) != set(expected):
        raise AssertionError("binding field set mismatch")
    left = json.dumps(actual, sort_keys=True, separators=(",", ":"), allow_nan=False)
    right = json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if left != right:
        raise AssertionError("full binding mismatch")

def responsibility(checkpoints):
    if not checkpoints:
        raise AssertionError("no observed checkpoints")
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict) or set(checkpoint) != {"old", "successor", "saved_stop"}:
            raise AssertionError("invalid checkpoint")
        if any(type(x) is not int or x < 0 for x in checkpoint.values()):
            raise AssertionError("invalid raw count")
        if not any(checkpoint.values()):
            raise AssertionError("orphaned accepted responsibility")

def exact_identity_counts(rows, expected_ids):
    if len(rows) != len(expected_ids) or sorted(rows) != sorted(expected_ids):
        raise AssertionError("missing or duplicate actual identity")

def fair_prefix(namespaces, eligible):
    if len(namespaces) < len(eligible) or set(namespaces[:len(eligible)]) != set(eligible):
        raise AssertionError("eligible namespace starved in declared round")
