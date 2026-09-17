"""System-design trigger gate: one pending unit at a time, then stop at completion."""


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


def pending_units(facts):
    spec, accepted, _frozen, amended, stale, violations, done = _state(facts)
    if not spec or done:
        return []
    pending = []
    for unit in spec.get("units", []):
        unit_id = unit.get("id")
        seq = accepted.get(unit_id)
        if seq is None:
            pending.append(unit)
            continue
        if amended.get(unit_id, 0) > seq or violations.get(unit_id, 0) > seq or stale.get(unit_id, 0) > seq:
            pending.append(unit)
    return pending


def should_start(*, task, facts, new, head, now=None):
    if not new:
        return False
    return bool(pending_units(facts))


def should_continue(*, state):
    """The Round may only end with progress: a unit accepted, or completion.

    A bare `final` (including a truncated/empty reply) does not end the Round —
    otherwise a long design answer that was never written or accepted would look
    like success.
    """
    started_at = state.get("started_at_seq", 0)
    return not any(
        fact["kind"] in ("design.unit.accepted", "task.completed") and fact["seq"] > started_at
        for fact in state.get("facts", [])
    )
