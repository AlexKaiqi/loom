"""Bounded projection for goal mode (v2 after the ark-goal-001 no-progress counterexample).

Shows objective, acceptance, phase, the scripts already run in this Round, the
last tool result with its outcome, the remaining step budget and the action
protocol. The step budget and the no-repeat rule are the harness's progress
policy, not runtime semantics.
"""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    base.SHELL_EXAMPLE,
    '{"action":{"type":"emit","kind":"task.completed","payload":{"evidence_refs":["<relative path>"]}}}',
    base.FINAL_EXAMPLE + " without completing",
])


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    folded = base.fold(facts, latest=("task.objective.set", "task.phase.changed"), flags=("task.completed",))
    objective_payload = folded["task.objective.set"] or {}
    objective = objective_payload.get("objective")
    acceptance = objective_payload.get("acceptance", [])
    phase = (folded["task.phase.changed"] or {}).get("to", "open")
    completed = folded["task.completed"]

    lines = [
        "# Goal",
        "objective: %s" % (objective or "(none)"),
        "acceptance: %s" % json.dumps(acceptance, ensure_ascii=False),
        "phase: %s   completed: %s" % (phase, completed),
        "",
    ]
    lines += base.budget_lines(step, max_steps)
    lines += [
        "# Content directory (your only working area)",
        str(content_dir),
        "files: %s" % (", ".join(base.content_files(content_dir)) or "(empty)"),
        "",
    ]
    lines += base.tool_history_lines(facts)
    lines += [
        "",
        "# Rules",
        "1. Run at most one verification command for the acceptance conditions, and only if it has not run yet.",
        "2. If the acceptance conditions are already satisfied by the current content, your next action MUST be "
        "emit task.completed with evidence_refs naming the files that prove it.",
        "3. Never run a shell script that already appears in the list above.",
        "4. When remaining steps reach 0 you must decide: emit task.completed or final with a reason.",
        "",
        ACTION_PROTOCOL,
    ]

    return {
        "system": (
            "You are the model inside one Round of a goal-mode task. Work inside the content directory with "
            "ordinary shell commands. Declare state changes only with declared kinds. task.completed is a claim "
            "backed by evidence_refs, not a runtime terminal state."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
