"""Kernel projection: working directory, recent tools, action protocol.

Objective text is listed when present. Pinning it against later working-set
trimming is a combination branch (`h/kernel/pin`), not this kernel.
"""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    base.SHELL_EXAMPLE,
    '{"action":{"type":"emit","kind":"work.completed","payload":{"evidence_refs":["<relative path>"]}}}',
    base.FINAL_EXAMPLE + " without completing",
])


def build(*, work, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          userspaces=None, revision=None):
    folded = base.fold(facts, latest=("work.objective.set",), flags=("work.completed",))
    objective = folded["work.objective.set"] or {}
    lines = [
        "# Work",
        "objective: %s" % (objective.get("objective") or "(none)"),
        "completed: %s" % folded["work.completed"],
        "",
    ]
    lines += base.budget_lines(step, max_steps)
    lines += [
        "# Content directory",
        str(content_dir),
        "files: %s" % (", ".join(base.content_files(content_dir)) or "(empty)"),
        "",
    ]
    lines += base.tool_history_lines(facts)
    lines += [
        "",
        "# Rules",
        "1. Work in the content directory with ordinary shell commands.",
        "2. Do not repeat a shell script already listed above.",
        "3. When the work is done, emit work.completed with evidence_refs.",
        "",
        ACTION_PROTOCOL,
    ]
    lines += base.rejected_final_lines(rejected_final)
    return {
        "system": (
            "You are the model inside one Round. Use shell in the content directory. "
            "work.completed is a claim backed by evidence_refs, not a runtime terminal state."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
