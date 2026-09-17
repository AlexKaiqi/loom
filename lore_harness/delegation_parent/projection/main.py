"""Parent projection: objective plus delegation/report state. Never reads child content."""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"emit","kind":"task.delegated","payload":{"child":"<child task id>","scope":"<what to produce>","input_refs":[]}}}',
    '{"action":{"type":"emit","kind":"task.completed","payload":{"evidence_refs":["task.reported"]}}}',
    base.FINAL_EXAMPLE,
])


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          workspaces=None, revision=None):
    folded = base.fold(facts, latest=("task.objective.set", "task.delegated", "task.reported"),
                       flags=("task.completed",))
    objective, delegated, reported = (folded["task.objective.set"], folded["task.delegated"],
                                      folded["task.reported"])
    lines = [
        "# Parent objective",
        json.dumps(objective, ensure_ascii=False),
        "",
        "# Delegation",
        json.dumps(delegated, ensure_ascii=False) if delegated else "(not delegated yet)",
        "",
        "# Report received from the child",
        json.dumps(reported, ensure_ascii=False) if reported else "(none yet)",
        "parent task completed: %s" % folded["task.completed"],
        "",
    ]
    lines += base.budget_lines(step, max_steps)
    lines += [
        "# Rules",
        "1. You cannot read or write the child's content. The only channel is events.",
        "2. If nothing is delegated yet, emit task.delegated with the child id and scope, then stop.",
        "3. If a task.reported fact is present, the child HAS reported and that report is the confirmation. "
        "Your next action MUST be emit task.completed with evidence_refs, then stop. Do not ask for more.",
        "4. You have no authority over the child beyond what the event admits; do not invent results.",
    ]
    lines += base.rejected_final_lines(rejected_final)
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": "You are the parent task in a delegation. Delegate once, then wait for the admitted report.",
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
