"""Framework-provided standard library for harness authoring (lore_harness_base).

This module is part of the framework, versioned with the runtime, and NOT part
of any harness digest: importing it is the same class of dependency as the role
hook signatures themselves (a harness always runs against the runtime version it
was registered with). It exists because the ten example harnesses duplicated the
same scaffolding (harness inventory 2026-09-17, items 1-12); the domain
semantics - which kinds mean what, which rules apply - stay in each harness.

Composition ruling (2026-09-17): harness reuse happens at authoring time via
this shared library plus reference-merge; there is no runtime composition
mechanism. Stdlib only; this module must never import lore_task.
"""
import hashlib
import json
from pathlib import Path

# -- action protocol ---------------------------------------------------------

ACTION_PREAMBLE = (
    "Reply with exactly one JSON object and no prose. One of:"
)


def action_protocol(examples) -> str:
    """The single-JSON action protocol, with the harness's domain examples."""
    return ACTION_PREAMBLE + "\n" + "\n".join(examples)


SHELL_EXAMPLE = '{"action":{"type":"shell","script":"<sh script>","budget_ms":30000}}   run a command (budget_ms optional: policy budget in ms)'
EMIT_EXAMPLE = '{"action":{"type":"emit","kind":"<declared kind>","payload":{...}}}   declare a state change'
FINAL_EXAMPLE = '{"action":{"type":"final","text":"<short reason>"}}   end this round'


def parse_action(text) -> dict:
    """Common action prefix shared by every harness parse (and the runtime default).

    Strips whitespace and code fences, parses one JSON object, extracts the
    inner action. Malformed output is never guessed into an action: it becomes a
    final proposal carrying the raw text. Empty input becomes {"type":"none"}.
    Domain-specific shape checks stay in the harness and may fall back to
    `final_fallback(text)`.
    """
    raw = (text or "").strip()
    if not raw:
        return {"type": "none"}
    candidate = raw
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return final_fallback(raw)
    action = value.get("action", value) if isinstance(value, dict) else None
    if not isinstance(action, dict) or "type" not in action:
        return final_fallback(raw)
    return action


def final_fallback(text) -> dict:
    return {"type": "final", "text": (text or "").strip()}


# -- fact folding ------------------------------------------------------------

def fold(facts, *, latest=(), collect=(), flags=(), since=0) -> dict:
    """Fold a fact stream into per-kind state (the shared half of every `_state`).

    Returns a dict keyed by kind: `latest` kinds map to their newest payload
    (None if absent), `collect` kinds to the list of payloads in stream order,
    `flags` kinds to True once seen. `since` restricts to seq > since.
    Which kinds mean what stays in the harness.
    """
    out = {kind: None for kind in latest}
    out.update({kind: [] for kind in collect})
    out.update({kind: False for kind in flags})
    for fact in facts:
        if fact["seq"] <= since:
            continue
        kind = fact["kind"]
        if kind in out:
            if kind in latest:
                out[kind] = fact["payload"]
            elif kind in collect:
                out[kind].append(fact["payload"])
            else:
                out[kind] = True
    return out


def facts_since(facts, kinds, since_seq) -> list:
    """Facts of the given kind(s) with seq > since_seq (round-scoped views)."""
    if isinstance(kinds, str):
        kinds = (kinds,)
    return [f for f in facts if f["kind"] in kinds and f["seq"] > since_seq]


# -- round gate skeletons ------------------------------------------------------

def continue_when(state, kinds, *, stop_on_final=True, since=None) -> bool:
    """Shared should_continue skeleton: final stops, then a watched-kind fact
    inside this Round stops it. `since=None` uses the round's started_at_seq
    watermark; pass 0 to watch the whole stream."""
    if stop_on_final and state.get("final") is not None:
        return False
    watermark = state.get("started_at_seq", 0) if since is None else since
    return not facts_since(state.get("facts", []), kinds, watermark)


def start_unless_completed(facts, kind="task.completed") -> bool:
    """Shared should_start guard: never start a new Round after completion was
    declared (completion is a claim, not a runtime terminal state)."""
    return not any(f["kind"] == kind for f in facts)


def make_accept(*kinds):
    """Admission rule factory: accept only the harness's declared external kinds."""
    def accept(*, kind, payload):
        return kind in kinds
    return accept


# -- projection scaffolding ----------------------------------------------------

def content_files(content_dir) -> list:
    """Sorted relative file list of the content directory."""
    return sorted(str(p.relative_to(content_dir)) for p in Path(content_dir).rglob("*") if p.is_file())


def budget_lines(step, max_steps) -> list:
    return [
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
    ]


def tool_history_lines(facts, *, since_seq=0) -> list:
    """'scripts already run in this Round' block plus the last tool result."""
    results = facts_since(facts, "sys.tool.result", since_seq)
    lines = ["# Shell scripts already run in this Round (do NOT run any of these again)"]
    if results:
        for index, fact in enumerate(results, 1):
            payload = fact["payload"]
            lines.append("%d. outcome=%s exit=%s  %s"
                         % (index, payload.get("outcome", "?"), payload.get("exit", "?"),
                            payload.get("script", "").replace("\n", " ")[:200]))
    else:
        lines.append("(none yet)")
    if results:
        last = results[-1]["payload"]
        lines += [
            "",
            "# Last tool result (outcome=%s exit=%s)" % (last.get("outcome"), last.get("exit")),
            "stdout: %s" % (last.get("stdout") or "").replace("\n", "\\n")[:600],
            "stderr: %s" % (last.get("stderr") or "").replace("\n", "\\n")[:300],
        ]
    return lines


def rejected_final_lines(rejected_final, limit=200) -> list:
    if not rejected_final:
        return []
    return ["", "# Rejected final", rejected_final[:limit]]


# -- small shared utilities ------------------------------------------------------

def file_digest(path):
    """sha256 of a file's bytes, or None if unreadable (evidence, not trust)."""
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def load_config(defaults=None, *, config_path) -> dict:
    """Merge harness config.json over defaults; unreadable config = defaults."""
    config = dict(defaults or {})
    try:
        with open(config_path, encoding="utf-8") as fh:
            config.update(json.load(fh))
    except (OSError, json.JSONDecodeError):
        pass
    return config
