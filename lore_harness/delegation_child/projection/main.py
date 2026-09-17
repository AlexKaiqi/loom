"""Child projection: the delegated scope, its own content area, and the report protocol."""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"shell","script":"<sh script writing the deliverable in content>"}}',
    '{"action":{"type":"emit","kind":"work.reported","payload":{"result_ref":"<relative file>","evidence_refs":["<relative file>"]}}}',
    base.FINAL_EXAMPLE,
])


def build(*, work, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          userspaces=None, revision=None):
    folded = base.fold(facts, latest=("work.delegated",), flags=("work.reported",))
    delegated, reported = folded["work.delegated"], folded["work.reported"]
    scripts = [f["payload"].get("script", "") for f in base.facts_since(facts, "sys.tool.result", 0)]
    lines = [
        "# Delegated scope",
        json.dumps(delegated, ensure_ascii=False),
        "reported: %s" % reported,
        "",
        "# Your content area (cwd for every shell action)",
        str(content_dir),
        "files: %s" % (", ".join(base.content_files(content_dir)) or "(empty)"),
        "",
        "# Shell scripts already run in this Round (never repeat one)",
    ]
    lines += ["%d. %s" % (i, s.replace("\n", " ")[:160]) for i, s in enumerate(scripts[-4:], 1)] or ["(none yet)"]
    lines += [""]
    lines += base.budget_lines(step, max_steps)
    lines += [
        "# Rules",
        "1. Produce the deliverable with a RELATIVE path inside your own content area.",
        "2. Then emit work.reported with result_ref and evidence_refs naming the real file(s).",
        "3. Do not report success for a file you did not actually create.",
    ]
    lines += base.rejected_final_lines(rejected_final)
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": "You are the delegated child work. Do the scoped work in your own content area and report it.",
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
