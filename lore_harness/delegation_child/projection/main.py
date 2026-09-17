"""Child projection: the delegated scope, its own content area, and the report protocol."""
import json

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"shell","script":"<sh script writing the deliverable in content>"}}\n'
    '{"action":{"type":"emit","kind":"task.reported","payload":{"result_ref":"<relative file>","evidence_refs":["<relative file>"]}}}\n'
    '{"action":{"type":"final","text":"<reason>"}}'
)


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          workspaces=None, revision=None):
    delegated, reported = None, False
    for fact in facts:
        if fact["kind"] == "task.delegated":
            delegated = fact["payload"]
        elif fact["kind"] == "task.reported":
            reported = True
    files = sorted(str(p.relative_to(content_dir)) for p in content_dir.rglob("*") if p.is_file())
    scripts = [f["payload"].get("script", "") for f in facts if f["kind"] == "sys.tool.result"]
    lines = [
        "# Delegated scope",
        json.dumps(delegated, ensure_ascii=False),
        "reported: %s" % reported,
        "",
        "# Your content area (cwd for every shell action)",
        str(content_dir),
        "files: %s" % (", ".join(files) if files else "(empty)"),
        "",
        "# Shell scripts already run in this Round (never repeat one)",
    ]
    lines += ["%d. %s" % (i, s.replace("\n", " ")[:160]) for i, s in enumerate(scripts[-4:], 1)] or ["(none yet)"]
    lines += [
        "",
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
        "# Rules",
        "1. Produce the deliverable with a RELATIVE path inside your own content area.",
        "2. Then emit task.reported with result_ref and evidence_refs naming the real file(s).",
        "3. Do not report success for a file you did not actually create.",
    ]
    if rejected_final:
        lines += ["", "# Rejected final", rejected_final[:200]]
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": "You are the delegated child task. Do the scoped work in your own content area and report it.",
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
