"""Bounded projection for plan mode: current stage + immediately next stage only."""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"shell","script":"<sh script>"}}   run inside the content directory',
    '{"action":{"type":"emit","kind":"plan.stage.completed","payload":{"stage_id":"<id>","evidence_refs":["<file>"]}}}',
    base.FINAL_EXAMPLE + " without completing the stage",
])


def _plan(facts):
    folded = base.fold(facts, latest=("plan.created", "plan.revised"), collect=("plan.stage.completed",))
    spec = folded["plan.created"] or folded["plan.revised"]
    return spec, [p.get("stage_id") for p in folded["plan.stage.completed"]]


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    spec, completed = _plan(facts)
    stages = (spec or {}).get("stages", [])
    remaining = [s for s in stages if s.get("id") not in completed]
    current = remaining[0] if remaining else None
    following = remaining[1] if len(remaining) > 1 else None
    scripts = [f["payload"].get("script", "") for f in base.facts_since(facts, "sys.tool.result", 0)]
    last_tool = next((f["payload"] for f in reversed(facts) if f["kind"] == "sys.tool.result"), None)

    lines = [
        "# Plan",
        "plan_id: %s" % (spec or {}).get("plan_id"),
        "completed stages: %s" % json.dumps(completed, ensure_ascii=False),
        "",
        "# Current stage (do ONLY this one)",
        json.dumps(current, ensure_ascii=False) if current else "(none: all stages completed)",
        "",
        "# Next stage (context only, do not start it)",
        json.dumps(following, ensure_ascii=False) if following else "(none)",
        "",
    ]
    lines += base.budget_lines(step, max_steps)
    lines += [
        "# Content directory",
        str(content_dir),
        "files: %s" % (", ".join(base.content_files(content_dir)) or "(empty)"),
        "",
        "# Shell scripts already run in this Round (never repeat one)",
    ]
    lines += ["%d. %s" % (i, s.replace("\n", " ")[:160]) for i, s in enumerate(scripts[-6:], 1)] or ["(none yet)"]
    if last_tool is not None:
        lines += ["", "# Last tool result (outcome=%s exit=%s)" % (last_tool.get("outcome"), last_tool.get("exit")),
                  "stdout: %s" % (last_tool.get("stdout") or "").replace("\n", "\\n")[:500]]
    lines += [
        "",
        "# Rules",
        "1. Work only on the current stage; do not touch later stages.",
        "2. Once the current stage deliverable exists and is verified at most once, emit plan.stage.completed "
        "with evidence_refs and stop.",
        "3. Never repeat a shell script listed above.",
        "4. If no current stage remains, emit plan.completed instead.",
        "5. When remaining steps reach 0 you must decide: emit the stage result or final with a reason.",
        "",
        ACTION_PROTOCOL,
    ]
    return {
        "system": (
            "You are the model inside one Round of a plan-mode task. Advance exactly one stage, in order, "
            "inside the content directory. Declare stage results only with declared kinds."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
