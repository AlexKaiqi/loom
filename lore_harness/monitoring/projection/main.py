"""Projection for monitoring: condition, deadline, current time, check command."""
import json
import time

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"shell","script":"<check command>"}}   evaluate the condition in content\n'
    '{"action":{"type":"emit","kind":"monitor.condition.met","payload":{"monitor_id":"...","evidence_refs":["..."]}}}\n'
    '{"action":{"type":"emit","kind":"monitor.condition.expired","payload":{"monitor_id":"...","reason":"..."}}}\n'
    '{"action":{"type":"final","text":"<reason>"}}'
)


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    condition, signals, closed = None, [], False
    tools = []
    for fact in facts:
        kind = fact["kind"]
        if kind == "monitor.condition.set":
            condition = fact["payload"]
        elif kind == "monitor.signal":
            signals.append(fact["payload"])
        elif kind in ("monitor.condition.met", "monitor.condition.expired"):
            closed = True
        elif kind == "sys.tool.result":
            tools.append(fact["payload"])
    now = int(time.time())
    deadline = (condition or {}).get("deadline_epoch")
    lines = [
        "# Monitored condition",
        json.dumps(condition, ensure_ascii=False),
        "",
        "# Time",
        "now_epoch: %d   deadline_epoch: %s   due: %s" % (now, deadline, deadline is not None and now >= int(deadline)),
        "",
        "# External signals received",
        json.dumps(signals[-3:], ensure_ascii=False),
        "closed: %s" % closed,
        "",
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
        "# Recent tool results",
    ]
    for tool in tools[-3:]:
        lines.append("- exit=%s  %s" % (tool.get("exit"), (tool.get("stdout") or "").replace("\n", "\\n")[:200]))
    lines += [
        "",
        "# Rules",
        "1. Evaluate the condition with at most one check command.",
        "2. Emit monitor.condition.met only with real evidence; otherwise emit monitor.condition.expired with a reason.",
        "3. This Round is the only time work happens: the runtime is not a polling loop and keeps nothing alive while waiting.",
    ]
    if rejected_final:
        lines += ["", "# Rejected final", rejected_final[:200]]
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": (
            "You are the model inside one Round of a monitoring task. Decide whether the watched condition is "
            "met, expired, or neither — and say so as a declared fact."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
