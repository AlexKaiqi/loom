"""System-design settle: derive freezing, freeze violations, staleness and completion.

Nothing here trusts the model's word about bytes: `design.unit.frozen` and
`design.freeze.violation` are computed from the files on disk.
"""
import hashlib
import json
from pathlib import Path


def _digest(path):
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _state(facts):
    spec, accepted, frozen, amended, stale, violations = None, {}, {}, {}, {}, {}
    done = False
    for fact in facts:
        kind, payload, seq = fact["kind"], fact["payload"], fact["seq"]
        if kind == "design.objective.set":
            spec = payload
        elif kind == "design.unit.accepted":
            accepted[payload.get("unit_id")] = seq
        elif kind == "design.unit.frozen":
            frozen[payload.get("unit_id")] = fact
        elif kind == "design.amendment.accepted":
            amended[payload.get("unit_id")] = seq
        elif kind == "design.unit.stale":
            stale[payload.get("unit_id")] = seq
        elif kind == "design.freeze.violation":
            violations[payload.get("unit_id")] = seq
        elif kind == "task.completed":
            done = True
    return spec, accepted, frozen, amended, stale, violations, done


def parse(text):
    raw = (text or "").strip()
    if not raw:
        return {"type": "none"}
    candidate = raw
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return {"type": "final", "text": raw}
    action = value.get("action", value) if isinstance(value, dict) else None
    if not isinstance(action, dict) or "type" not in action:
        return {"type": "final", "text": raw}
    if action["type"] == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "design.unit.accepted":
            if not payload.get("unit_id") or not isinstance(action.get("base_rev"), str):
                return {"type": "final", "text": raw}
    if action["type"] == "shell" and not isinstance(action.get("script"), str):
        return {"type": "final", "text": raw}
    return action


def guard(*, state, action):
    """Refuse to rewrite the current unit's file twice in one Round.

    The system-design failure mode is churn: the model keeps re-drafting the same
    deliverable and never declares progress. Rewriting is refused so the only
    forward action left is acceptance.
    """
    if action.get("type") != "shell":
        return None
    script = action.get("script") or ""
    facts = state.get("facts", [])
    spec, accepted, _frozen, amended, stale, violations, _done = _state(facts)
    current = None
    for unit in (spec or {}).get("units", []):
        unit_id = unit.get("id")
        seq = accepted.get(unit_id)
        if seq is None or amended.get(unit_id, 0) > seq or violations.get(unit_id, 0) > seq or stale.get(unit_id, 0) > seq:
            current = unit_id
            break
    if current is None:
        return None
    marker = "units/%s.md" % current
    if marker not in script:
        return None
    started_at = state.get("started_at_seq", 0)
    already = any(
        fact["kind"] == "sys.tool.result" and fact["seq"] > started_at and marker in (fact["payload"].get("script") or "")
        for fact in facts
    )
    if already:
        return ("%s was already written in this Round; do not rewrite it — emit "
                "design.unit.accepted with the committed revision as base_rev now" % marker)
    return None


def settle(state):
    content = Path(state["content_dir"])
    facts = state.get("facts", [])
    spec, accepted, frozen, amended, stale, violations, done = _state(facts)
    if done or not spec:
        return []
    out = []

    # 1) freeze units accepted in this Round (nothing frozen for this acceptance yet)
    for unit_id, seq in accepted.items():
        current = frozen.get(unit_id)
        if current is not None and current["seq"] >= seq:
            continue
        if amended.get(unit_id, 0) > seq:
            continue
        path = content / "units" / (unit_id + ".md")
        digest = _digest(path)
        if digest is None:
            # An accepted unit whose deliverable is missing is not frozen: it is a
            # visible violation, so the unit becomes pending again instead of
            # silently stalling the design.
            if violations.get(unit_id, 0) < seq:
                out.append({"kind": "design.freeze.violation",
                            "payload": {"unit_id": unit_id, "expected": None, "actual": None,
                                        "reason": "accepted unit file is missing: units/%s.md" % unit_id}})
            continue
        out.append({"kind": "design.unit.frozen",
                    "payload": {"unit_id": unit_id, "file": str(path.relative_to(content)),
                                "file_digest": digest}})

    # 2) freeze violations: frozen bytes changed without an accepted amendment or
    #    without the harness itself having marked the unit stale (staleness is the
    #    authorization to revise a dependent, exactly like an amendment)
    for unit_id, fact in list(frozen.items()):
        if amended.get(unit_id, 0) > fact["seq"]:
            continue
        if stale.get(unit_id, 0) > fact["seq"]:
            continue
        if violations.get(unit_id, 0) > fact["seq"]:
            continue
        digest = _digest(content / fact["payload"]["file"])
        if digest is not None and digest != fact["payload"]["file_digest"]:
            out.append({"kind": "design.freeze.violation",
                        "payload": {"unit_id": unit_id, "expected": fact["payload"]["file_digest"],
                                    "actual": digest}})

    # 3) staleness: a frozen unit whose dependency was amended after it was frozen
    for unit in spec.get("units", []):
        unit_id = unit.get("id")
        if unit_id not in frozen and unit_id not in accepted:
            continue
        for dependency in unit.get("depends_on", []) or []:
            amendment_seq = amended.get(dependency, 0)
            if amendment_seq and amendment_seq > stale.get(unit_id, 0):
                out.append({"kind": "design.unit.stale",
                            "payload": {"unit_id": unit_id, "because": dependency}})
                break

    # 4) completion: consider this Round's freezes, and refuse while anything is off
    frozen_now = dict(frozen)
    for item in out:
        if item["kind"] == "design.unit.frozen":
            frozen_now[item["payload"]["unit_id"]] = {"seq": 10 ** 9, "payload": item["payload"]}
    blocking = any(item["kind"] in ("design.freeze.violation", "design.unit.stale") for item in out)
    complete = not blocking
    for unit in spec.get("units", []):
        unit_id = unit.get("id")
        if frozen_now.get(unit_id) is None:
            complete = False
            break
        seq = accepted.get(unit_id, 0)
        if amended.get(unit_id, 0) > seq or violations.get(unit_id, 0) > seq or stale.get(unit_id, 0) > seq:
            complete = False
            break
    if complete:
        out.append({"kind": "task.completed",
                    "payload": {"units": [u.get("id") for u in spec.get("units", [])],
                                "revision": state.get("base_rev")}})
    return out
