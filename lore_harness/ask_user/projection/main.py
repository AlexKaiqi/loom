"""Projection for ask-user: objective, open question, answer if any."""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"emit","kind":"ask.requested","payload":{"ask_id":"q1","question":"...","options":["..."]}}}',
    '{"action":{"type":"shell","script":"<sh script>"}}   run inside the content directory',
    '{"action":{"type":"emit","kind":"task.completed","payload":{"evidence_refs":["<file>"]}}}',
    base.FINAL_EXAMPLE,
])


def _state(facts):
    folded = base.fold(facts, latest=("task.objective.set",), collect=("ask.requested", "ask.answered"),
                       flags=("task.completed",))
    objective_payload = folded["task.objective.set"] or {}
    asked = folded["ask.requested"]
    answered = {a.get("ask_id"): a.get("answer") for a in folded["ask.answered"]}
    open_ask = None
    for ask in reversed(asked):
        if ask.get("ask_id") not in answered:
            open_ask = ask
            break
    return (objective_payload.get("objective"), objective_payload.get("acceptance", []),
            asked, answered, open_ask, folded["task.completed"])


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    objective, acceptance, _asked, answered, open_ask, completed = _state(facts)
    scripts = [f["payload"].get("script", "") for f in base.facts_since(facts, "sys.tool.result", 0)]

    lines = [
        "# Goal",
        "objective: %s" % (objective or "(none)"),
        "acceptance: %s" % json.dumps(acceptance, ensure_ascii=False),
        "completed: %s" % completed,
        "",
        "# Open question (if any)",
        json.dumps(open_ask, ensure_ascii=False) if open_ask else "(none)",
        "",
        "# Answers received",
        json.dumps(answered, ensure_ascii=False),
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
    lines += [
        "",
        "# Rules",
        "1. NEVER guess information the objective does not provide. If a required input is missing, emit "
        "ask.requested exactly once and end the Round — the task then waits as data.",
        "2. When the open question has an answer above, use that answer and finish the work.",
        "3. Once acceptance is satisfied, emit task.completed with evidence_refs.",
        "4. Never repeat a shell script listed above.",
    ]
    lines += base.rejected_final_lines(rejected_final)
    lines += ["", ACTION_PROTOCOL]

    return {
        "system": (
            "You are the model inside one Round of an ask-user task. Ask instead of guessing; the answer "
            "arrives as an admitted fact in a later Round."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
