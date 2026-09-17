"""Projection for system design: bounded to the current unit plus frozen interfaces."""
import json
from pathlib import Path

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"shell","script":"<sh script writing units/<id>.md>"}}',
    '{"action":{"type":"emit","kind":"design.unit.accepted","base_rev":"<committed revision shown above>",'
    '"payload":{"unit_id":"<id>"}}}',
    base.FINAL_EXAMPLE,
])


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


def _status(unit_id, accepted, frozen, amended, stale, violations):
    seq = accepted.get(unit_id)
    if seq is None:
        return "pending"
    if amended.get(unit_id, 0) > seq:
        return "amended (re-accept required)"
    if violations.get(unit_id, 0) > seq:
        return "violation (re-accept required)"
    if stale.get(unit_id, 0) > seq:
        return "stale (re-accept required)"
    if frozen.get(unit_id) is not None and frozen[unit_id]["seq"] >= seq:
        return "frozen"
    return "accepted"


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          workspaces=None, revision=None):
    spec, accepted, frozen, amended, stale, violations, done = _state(facts)
    units = (spec or {}).get("units", [])
    current = None
    for unit in units:
        if _status(unit.get("id"), accepted, frozen, amended, stale, violations) != "frozen":
            current = unit
            break
    files = base.content_files(content_dir)
    rejected = [f["payload"] for f in base.facts_since(facts, "sys.declaration.rejected", 0)]

    lines = [
        "# Design objective",
        (spec or {}).get("objective") or "(none)",
        "committed revision (use this exact value as base_rev when accepting): %s" % (revision or "(unknown)"),
        "completed: %s" % done,
        "",
        "# Unit status (dependency order)",
    ]
    for unit in units:
        unit_id = unit.get("id")
        lines.append("- %s [%s] depends_on=%s :: %s" % (
            unit_id, _status(unit_id, accepted, frozen, amended, stale, violations),
            ",".join(unit.get("depends_on", []) or []) or "-", unit.get("deliverable") or unit.get("title")))
    lines += [
        "",
        "# Current unit (work on exactly this one)",
        json.dumps(current, ensure_ascii=False) if current else "(none: all units frozen)",
        "",
        "# Frozen bytes (do not modify these files; amendments are external)",
    ]
    for unit_id, fact in frozen.items():
        lines.append("- %s  %s  %s" % (unit_id, fact["payload"].get("file"), fact["payload"].get("file_digest")))
    lines += [
        "",
        "# Rejected conditional declarations in this run",
        json.dumps([r for r in rejected[-2:]], ensure_ascii=False),
        "",
        "# Freeze violations (fix these: missing file, or bytes changed without an amendment)",
        json.dumps([f["payload"] for f in base.facts_since(facts, "design.freeze.violation", 0)][-3:], ensure_ascii=False),
        "",
        "# Actions refused in this Round (do not repeat them)",
        json.dumps([f["payload"] for f in base.facts_since(facts, "sys.action.rejected", 0)][-2:], ensure_ascii=False),
        "",
        "# Content index",
        "Shell cwd IS this directory (no prefix needed): %s" % content_dir,
        "files: %s" % (", ".join(files) if files else "(empty)"),
        "",
        "# Shell scripts already run in this Round (do NOT run any of these again)",
    ]
    scripts = [f["payload"].get("script", "") for f in base.facts_since(facts, "sys.tool.result", 0)]
    lines += ["%d. %s" % (i, s.replace("\n", " ")[:160]) for i, s in enumerate(scripts[-4:], 1)] or ["(none yet)"]
    lines += [""]
    lines += base.budget_lines(step, max_steps)
    lines += [
        "# Rules",
        "0. Your reply must be exactly ONE JSON object. The design text belongs in the file you write "
        "with shell, never in the reply; a reply with no action does not end the Round.",
        "1. The design lives in `units/<unit_id>.md` (a RELATIVE path). Use plain relative paths such as "
        "`mkdir -p units && cat > units/u1.md`; NEVER copy the absolute content directory into a path.",
        "2. Write the unit file at most ONCE per Round. If you already wrote it this Round, your next action "
        "must be design.unit.accepted; rewriting the same file again makes no progress.",
        "3. Never modify a frozen unit's file; only an accepted amendment from outside unfreezes it.",
        "4. Accept the unit with the exact committed revision above as base_rev; a stale base is refused.",
        "5. Accept exactly one unit per Round, then stop.",
    ]
    lines += base.rejected_final_lines(rejected_final)
    lines += ["", ACTION_PROTOCOL]

    return {
        "system": (
            "You are the model inside one Round of a top-down system design task. Refine exactly one unit, "
            "respect frozen decisions, and declare acceptance against the committed revision you were shown."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
