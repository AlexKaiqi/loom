"""Parent projection: objective plus delegation/report state. Never reads child content."""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"emit","kind":"work.delegated","payload":{"child":"<child work id>","scope":"<what to produce>","input_refs":[]}}}',
    '{"action":{"type":"emit","kind":"work.completed","payload":{"evidence_refs":["work.reported"]}}}',
    base.FINAL_EXAMPLE,
])


def build(*, work, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          userspaces=None, revision=None):
    folded = base.fold(facts, latest=("work.objective.set", "work.delegated", "work.reported"),
                       flags=("work.completed",))
    objective, delegated, reported = (folded["work.objective.set"], folded["work.delegated"],
                                      folded["work.reported"])
    lines = [
        "# Parent objective",
        json.dumps(objective, ensure_ascii=False),
        "",
        "# Delegation",
        json.dumps(delegated, ensure_ascii=False) if delegated else "(not delegated yet)",
        "",
        "# Report received from the child",
        json.dumps(reported, ensure_ascii=False) if reported else "(none yet)",
        "parent work completed: %s" % folded["work.completed"],
        "",
    ]
    lines += base.budget_lines(step, max_steps)
    lines += [
        "# Rules",
        "1. You cannot read or write the child's content. The only channel is events.",
        "2. If nothing is delegated yet, emit work.delegated with the child id and scope, then stop.",
        "3. If a work.reported fact is present, the child HAS reported and that report is the confirmation. "
        "Your next action MUST be emit work.completed with evidence_refs, then stop. Do not ask for more.",
        "4. You have no authority over the child beyond what the event admits; do not invent results.",
    ]
    lines += base.rejected_final_lines(rejected_final)
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": "You are the parent work in a delegation. Delegate once, then wait for the admitted report.",
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
