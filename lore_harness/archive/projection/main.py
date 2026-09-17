"""Bounded projection for archive mode: file inventory + usage, fold protocol."""
import json
import os

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"shell","script":"mkdir -p archive && mv <old files> archive/"}}   lossless fold\n'
    '{"action":{"type":"emit","kind":"archive.performed","payload":{"scope":"...","moved":[{"from":"a","to":"archive/a"}],'
    '"original_refs":["archive/a"],"mode":"lossless"}}}\n'
    '{"action":{"type":"final","text":"<reason>"}}   end without folding'
)


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            config = json.load(fh)
    except OSError:
        config = {}
    inventory = []
    for path in sorted(content_dir.rglob("*")):
        if path.is_file():
            inventory.append((str(path.relative_to(content_dir)), path.stat().st_size))
    usage = [f["payload"] for f in facts if f["kind"] == "sys.context.usage"][-3:]
    performed = [f["payload"] for f in facts if f["kind"] == "archive.performed"]

    lines = [
        "# Context control",
        "threshold_bytes: %s" % config.get("threshold_bytes"),
        "keep_recent_files: %s" % config.get("keep_recent_files"),
        "recent usage observations: %s" % json.dumps(usage, ensure_ascii=False),
        "archives already performed: %d" % len(performed),
        "",
        "# Content inventory (path, bytes)",
    ]
    lines += ["- %s  %d" % (name, size) for name, size in inventory] or ["(empty)"]
    lines += [
        "",
        "# Rules",
        "1. Lossless fold only: move the OLDEST files into archive/ with `mv`; never delete or rewrite bytes.",
        "2. Keep the most recent files in place (keep_recent_files above).",
        "3. Then emit archive.performed with the exact moved list, original_refs and mode=lossless.",
        "4. If nothing needs folding, emit final with a reason.",
        "",
        ACTION_PROTOCOL,
    ]
    if rejected_final:
        lines += [
            "",
            "# Rejected final from this Round",
            "Your previous final ended the Round without an archive.performed declaration. A filesystem change "
            "without that declaration is not accepted. Emit archive.performed now (or explain via final only if "
            "you truly folded nothing). Previous text: %s" % rejected_final[:300],
        ]
    return {
        "system": (
            "You are the model inside one maintenance Round that controls context size. "
            "Fold older content losslessly into archive/ and record exactly what moved."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
