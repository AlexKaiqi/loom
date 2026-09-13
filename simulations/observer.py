"""Independent comparison and completeness checks for frozen G1 traces."""
from copy import deepcopy
from hashlib import sha256
import json

class ProtocolError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

def merge(base, overlay):
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result

def resolve(state, path, nullable_identity_maps=()):
    parts = path.split(".") if isinstance(path, str) else path
    if not isinstance(parts, list) or not parts:
        raise ProtocolError("empty or invalid observation path")
    value = state
    for i, part in enumerate(parts):
        if isinstance(value, dict):
            if part not in value:
                if i == 1 and parts[0] in nullable_identity_maps:
                    return None
                raise KeyError(f"missing observation segment {parts[:i+1]}")
            value = value[part]
        elif isinstance(value, list) and ((isinstance(part, int) and not isinstance(part, bool)) or (isinstance(part, str) and part.isdecimal())):
            value = value[int(part)]
        else:
            raise KeyError(f"cannot traverse observation segment {parts[:i+1]}")
    return value

def compare(actual, op, expected):
    if op == "eq":
        return canonical(actual) == canonical(expected)
    if op == "ne":
        return canonical(actual) != canonical(expected)
    if op == "contains":
        return isinstance(actual, list) and any(canonical(v) == canonical(expected) for v in actual)
    if op == "set_eq":
        return isinstance(actual, list) and isinstance(expected, list) and {canonical(v) for v in actual} == {canonical(v) for v in expected}
    raise ProtocolError(f"unknown comparator {op}")

def evaluate(expected, trace, nullable_identity_maps=()):
    if not expected or not trace or "initial" not in trace:
        raise ProtocolError("missing assertions or trace")
    checks = []
    for number, assertion in enumerate(expected, 1):
        ident = assertion.get("id", f"E{number:03}")
        at = assertion.get("at", "final")
        points = list(trace) if at == "all" else [list(trace)[-1] if at == "final" else at]
        op = assertion.get("op", assertion.get("operator"))
        if op not in {"eq", "ne", "contains", "set_eq"}:
            raise ProtocolError(f"unknown comparator {op}")
        for point in points:
            if point not in trace:
                raise ProtocolError(f"missing checkpoint {point}")
            row = {"assertion": ident, "checkpoint": point, "path": assertion["path"], "op": op, "expected": assertion["value"]}
            try:
                actual = resolve(trace[point], assertion["path"], nullable_identity_maps)
                row.update(actual=actual, passed=compare(actual, op, assertion["value"]))
            except (KeyError, IndexError) as error:
                raise ProtocolError(f"missing observation is invalid evidence: {error}") from error
            checks.append(row)
    if not checks:
        raise ProtocolError("no evaluated assertions")
    return checks

def verify_hashes(root, bindings):
    if not bindings:
        raise ProtocolError("empty version bindings")
    for filename, digest in bindings.items():
        file = root / filename
        if not file.is_file() or sha256(file.read_bytes()).hexdigest() != digest:
            raise ProtocolError(f"version mismatch or missing input: {filename}")

def validate_inventory(expected_ids, observed_ids):
    if not expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise ProtocolError("empty or duplicate registered cases")
    if len(observed_ids) != len(set(observed_ids)) or set(expected_ids) != set(observed_ids):
        raise ProtocolError("missing, duplicate or extra case execution")
