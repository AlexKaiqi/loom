"""Finite strict JSON, used for data transformation only."""
import json
import math


class WireError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def require(condition, reason="invalid_wire"):
    if not condition:
        raise WireError(reason)


def depth(value, level=0):
    if isinstance(value, (dict, list)):
        level += 1
        require(level <= 32)
        for child in (value.values() if isinstance(value, dict) else value):
            depth(child, level)
    elif isinstance(value, float):
        require(math.isfinite(value))


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def strict_load(raw):
    try:
        text = raw.decode("utf-8", "strict") if isinstance(raw, bytes) else raw
        result = json.loads(text, object_pairs_hook=pairs,
                            parse_constant=lambda value: (_ for _ in ()).throw(WireError("invalid_wire")))
        depth(result)
        return result
    except (ValueError, UnicodeError, RecursionError, TypeError) as error:
        raise WireError("invalid_wire") from error


def encode(value):
    depth(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
