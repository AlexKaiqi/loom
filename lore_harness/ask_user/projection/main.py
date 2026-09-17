"""Projection for ask-user: objective, open question, answer if any."""
import json

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"emit","kind":"ask.requested","payload":{"ask_id":"q1","question":"...","options":["..."]}}}\n'
    '{"action":{"type":"shell","script":"<sh script>"}}   run inside the content directory\n'
    '{"action":{"type":"emit","kind":"task.completed","payload":{"evidence_refs":["<file>"]}}}\n'
    '{"action":{"type":"final","text":"<reason>"}}'
)


def _state(facts):
    objective, acceptance = None, []
    asked, answered = [], {}
    completed = False
    for fact in facts:
        kind = fact["kind"]
        if kind == "task.objective.set":
            objective = fact["payload"].get("objective")
            acceptance = fact["payload"].get("acceptance", [])
        elif kind == "ask.requested":
            asked.append(fact["payload"])
        elif kind == "ask.answered":
            answered[fact["payload"].get("ask_id")] = fact["payload"].get("answer")
        elif kind == "task.completed":
            completed = True
    open_ask = None
    for ask in reversed(asked):
        if ask.get("ask_id") not in answered:
            open_ask = ask
            break
    return objective, acceptance, asked, answered, open_ask, completed


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    objective, acceptance, asked, answered, open_ask, completed = _state(facts)
    files = sorted(str(p.relative_to(content_dir)) for p in content_dir.rglob("*") if p.is_file())
    scripts = [f["payload"].get("script", "") for f in facts if f["kind"] == "sys.tool.result"]

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
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
        "# Content directory",
        str(content_dir),
        "files: %s" % (", ".join(files) if files else "(empty)"),
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
    if rejected_final:
        lines += ["", "# Rejected final", rejected_final[:200]]
    lines += ["", ACTION_PROTOCOL]

    return {
        "system": (
            "You are the model inside one Round of an ask-user task. Ask instead of guessing; the answer "
            "arrives as an admitted fact in a later Round."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
