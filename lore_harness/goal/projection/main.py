"""Bounded projection for goal mode (v2 after the ark-goal-001 no-progress counterexample).

Shows objective, acceptance, phase, the scripts already run in this Round, the
last tool result with its exit code, the remaining step budget and the action
protocol. The step budget and the no-repeat rule are the harness's progress
policy, not runtime semantics.
"""
import json

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"shell","script":"<sh script>"}}   run a command inside the content directory\n'
    '{"action":{"type":"emit","kind":"task.completed","payload":{"evidence_refs":["<relative path>"]}}}\n'
    '{"action":{"type":"final","text":"<short reason>"}}   end this round without completing'
)


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    objective, acceptance, completed, phase = None, [], False, "open"
    scripts, last_result = [], None
    for fact in facts:
        if fact["kind"] == "task.objective.set":
            objective = fact["payload"].get("objective")
            acceptance = fact["payload"].get("acceptance", [])
        elif fact["kind"] == "task.phase.changed":
            phase = fact["payload"].get("to", phase)
        elif fact["kind"] == "task.completed":
            completed = True
        elif fact["kind"] == "sys.tool.result":
            scripts.append(fact["payload"].get("script", ""))
            last_result = fact["payload"]
    files = sorted(str(p.relative_to(content_dir)) for p in content_dir.rglob("*") if p.is_file())

    lines = [
        "# Goal",
        "objective: %s" % (objective or "(none)"),
        "acceptance: %s" % json.dumps(acceptance, ensure_ascii=False),
        "phase: %s   completed: %s" % (phase, completed),
        "",
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
        "# Content directory (your only working area)",
        str(content_dir),
        "files: %s" % (", ".join(files) if files else "(empty)"),
        "",
        "# Shell scripts already run in this Round (do NOT run any of these again)",
    ]
    if scripts:
        for index, script in enumerate(scripts, 1):
            lines.append("%d. exit=%s  %s" % (index, (last_result or {}).get("exit", "?"), script.replace("\n", " ")[:200]))
    else:
        lines.append("(none yet)")
    if last_result is not None:
        lines += [
            "",
            "# Last tool result (exit=%s)" % last_result.get("exit"),
            "stdout: %s" % (last_result.get("stdout") or "").replace("\n", "\\n")[:600],
            "stderr: %s" % (last_result.get("stderr") or "").replace("\n", "\\n")[:300],
        ]
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
