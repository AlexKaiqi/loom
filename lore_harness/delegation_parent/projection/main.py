"""Parent projection: objective plus delegation/report state. Never reads child content."""
import json

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"emit","kind":"task.delegated","payload":{"child":"<child task id>","scope":"<what to produce>","input_refs":[]}}}\n'
    '{"action":{"type":"emit","kind":"task.completed","payload":{"evidence_refs":["task.reported"]}}}\n'
    '{"action":{"type":"final","text":"<reason>"}}'
)


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          workspaces=None, revision=None):
    objective, delegated, reported, completed = None, None, None, False
    for fact in facts:
        if fact["kind"] == "task.objective.set":
            objective = fact["payload"]
        elif fact["kind"] == "task.delegated":
            delegated = fact["payload"]
        elif fact["kind"] == "task.reported":
            reported = fact["payload"]
        elif fact["kind"] == "task.completed":
            completed = True
    lines = [
        "# Parent objective",
        json.dumps(objective, ensure_ascii=False),
        "",
        "# Delegation",
        json.dumps(delegated, ensure_ascii=False) if delegated else "(not delegated yet)",
        "",
        "# Report received from the child",
        json.dumps(reported, ensure_ascii=False) if reported else "(none yet)",
        "parent task completed: %s" % completed,
        "",
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
        "# Rules",
        "1. You cannot read or write the child's content. The only channel is events.",
        "2. If nothing is delegated yet, emit task.delegated with the child id and scope, then stop.",
        "3. If a task.reported fact is present, the child HAS reported and that report is the confirmation. "
        "Your next action MUST be emit task.completed with evidence_refs, then stop. Do not ask for more.",
        "4. You have no authority over the child beyond what the event admits; do not invent results.",
    ]
    if rejected_final:
        lines += ["", "# Rejected final", rejected_final[:200]]
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": "You are the parent task in a delegation. Delegate once, then wait for the admitted report.",
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
