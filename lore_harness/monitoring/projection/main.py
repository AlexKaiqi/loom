"""Projection for monitoring: condition, deadline, current time, check command."""
import json
import time

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"shell","script":"<check command>"}}   evaluate the condition in content',
    '{"action":{"type":"emit","kind":"monitor.condition.met","payload":{"monitor_id":"...","evidence_refs":["..."]}}}',
    '{"action":{"type":"emit","kind":"monitor.condition.expired","payload":{"monitor_id":"...","reason":"..."}}}',
    base.FINAL_EXAMPLE,
])


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None, workspaces=None, revision=None):
    folded = base.fold(facts, latest=("monitor.condition.set",), collect=("monitor.signal", "sys.tool.result"),
                       flags=("monitor.condition.met", "monitor.condition.expired"))
    condition = folded["monitor.condition.set"]
    signals, tools = folded["monitor.signal"], folded["sys.tool.result"]
    closed = folded["monitor.condition.met"] or folded["monitor.condition.expired"]
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
    ]
    lines += base.budget_lines(step, max_steps)
    lines += ["# Recent tool results"]
    for tool in tools[-3:]:
        lines.append("- outcome=%s exit=%s  %s" % (tool.get("outcome"), tool.get("exit"),
                                                   (tool.get("stdout") or "").replace("\n", "\\n")[:200]))
    lines += [
        "",
        "# Rules",
        "1. Evaluate the condition with at most one check command.",
        "2. Emit monitor.condition.met only with real evidence; otherwise emit monitor.condition.expired with a reason.",
        "3. This Round is the only time work happens: the runtime is not a polling loop and keeps nothing alive while waiting.",
    ]
    lines += base.rejected_final_lines(rejected_final)
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": (
            "You are the model inside one Round of a monitoring task. Decide whether the watched condition is "
            "met, expired, or neither — and say so as a declared fact."
        ),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
