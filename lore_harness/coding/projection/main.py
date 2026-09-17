"""Projection for coding: objective, the two domains, and the edit/test loop rules.

Content directory = notes and reports (Surface). Workspace = the code under test
(external authorized range, referenced by target). Both are ordinary directories;
the runtime routes `target`, it does not sandbox (isolation is X's job, not wired).
"""
import json

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"shell","target":"workspace","script":"<sh script>"}}   run in the code workspace\n'
    '{"action":{"type":"shell","script":"<sh script>"}}                        run in the content directory\n'
    '{"action":{"type":"emit","kind":"code.change.declared","payload":{"summary":"...","files":["a.py"]}}}\n'
    '{"action":{"type":"emit","kind":"code.test.declared","payload":{"command":"...","outcome":"pass|fail","evidence_refs":["..."]}}}\n'
    '{"action":{"type":"emit","kind":"task.completed","payload":{"evidence_refs":["report.md"]}}}\n'
    '{"action":{"type":"final","text":"<reason>"}}'
)


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    objective, acceptance, completed = None, [], False
    changes, tests, tools = [], [], []
    for fact in facts:
        kind = fact["kind"]
        if kind == "task.objective.set":
            objective = fact["payload"].get("objective")
            acceptance = fact["payload"].get("acceptance", [])
        elif kind == "code.change.declared":
            changes.append(fact["payload"])
        elif kind == "code.test.declared":
            tests.append(fact["payload"])
        elif kind == "sys.tool.result":
            tools.append(fact["payload"])
        elif kind == "task.completed":
            completed = True
    files = sorted(str(p.relative_to(content_dir)) for p in content_dir.rglob("*") if p.is_file())
    workspace_lines = []
    for workspace in (workspaces or []):
        root = workspace.get("path")
        listing = []
        try:
            from pathlib import Path
            listing = sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file())[:30]
        except OSError:
            listing = ["(unreadable)"]
        workspace_lines.append("%s -> %s  files: %s" % (workspace.get("id"), root, ", ".join(listing) or "(empty)"))

    lines = [
        "# Objective",
        "objective: %s" % (objective or "(none)"),
        "acceptance: %s" % json.dumps(acceptance, ensure_ascii=False),
        "completed: %s" % completed,
        "",
        "# Authorized execution targets",
        "- content (notes/reports): %s" % content_dir,
        "  files: %s" % (", ".join(files) if files else "(empty)"),
    ] + ["- workspace: %s" % line for line in workspace_lines] + [
        "",
        "# Changes declared so far",
        json.dumps(changes[-3:], ensure_ascii=False),
        "# Test outcomes declared so far",
        json.dumps(tests[-3:], ensure_ascii=False),
        "",
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
        "# Recent tool results",
    ]
    for tool in tools[-4:]:
        lines.append("- target=%s exit=%s  %s" % (tool.get("target"), tool.get("exit"),
                                                  (tool.get("stdout") or "").replace("\n", "\\n")[:200]))
    lines += [
        "",
        "# Rules",
        "1. Code lives in the workspace; notes/reports live in content. Use `target` to choose.",
        "2. Never claim a test passed without running it and reading the real exit code.",
        "3. Declare code.change.declared after editing, and code.test.declared with the real outcome.",
        "4. Only emit task.completed after a real passing test and with evidence_refs.",
        "5. Never repeat a shell script listed in the recent tool results.",
    ]
    if rejected_final:
        lines += ["", "# Rejected final", rejected_final[:200]]
    lines += ["", ACTION_PROTOCOL]

    return {
        "system": (
            "You are the model inside one Round of a coding task. Edit code in the authorized workspace, run "
            "the real tests there, and declare the actual outcome. Never present an unverified claim as a result."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
