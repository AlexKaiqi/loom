"""Minimal replaceable policy: ordinary files, bounded views, native Pi hooks."""
import copy
import json
from pathlib import Path
import re
from archive import encode, save

PROMPT = """Work on the user's objective using the available tools. Task files live in Userspace.
Maintain report.md and notes.md in Surface: record results, evidence and remaining uncertainty.
Maintain plan.md as an ordinary Markdown plan for work needing multiple steps. Focus on its first
unchecked step, record evidence paths before checking it, then proceed to the next step. A checkbox
or a model assertion is a progress note, not independent proof of completion. Revise the plan when
new facts warrant it; do not let an old plan override the current user's objective.
Use shell to inspect and update those ordinary files. Tool execution happens remotely.
The initial view and long histories are bounded. Omitted Surface files stay in place; list them with
`find . -type f` in the Surface domain. Read original archived facts and native contexts with shell
at their archive/*.json paths; archive/index.jsonl lists them. Archive records may point to earlier
archives. These are lossless originals, not summaries. Do not treat omission as absence.
Finish with a concise account of what was actually achieved. Do not invent evidence.
If waiting for information, describe the missing information in report.md and stop."""
ARCHIVE_MARKER = "LOOM_KERNEL_ARCHIVE "


class Kernel:
    def __init__(self, harness):
        self.harness = Path(harness)
        self.surface = self.harness.parent / "surface"
        self.config = json.loads((self.harness / "policy.json").read_text())
        required = {"projection_bytes", "archive_trigger_bytes", "retained_turns", "recent_facts", "max_turns", "timeout", "context_bytes_per_token", "context_reserve_percent", "max_output_tokens"}
        if set(self.config) != required or any(type(value) is not int or value <= 0 for value in self.config.values()):
            raise ValueError("invalid fixed kernel policy configuration")
        if self.config["context_reserve_percent"] >= 100:
            raise ValueError("kernel context reserve must leave input space")
        if self.config["projection_bytes"] >= self.config["archive_trigger_bytes"]:
            raise ValueError("kernel archive trigger must exceed projection budget")

    def bounds(self, params):
        budget = self.config["projection_bytes"]
        trigger = self.config["archive_trigger_bytes"]
        model = params.get("model_semantics") or {}
        window, supported_output = model.get("contextWindow"), model.get("maxTokens")
        output = self.config["max_output_tokens"]
        if isinstance(supported_output, int):
            output = min(output, supported_output)
        if isinstance(window, int):
            output = min(output, max(1, window // 4))
            # This configurable byte/token estimate bounds the policy's working
            # set; it is not provider-token accounting. Reserve output plus a
            # fraction for protocol/tools instead of a fixed minimum window.
            reserve = (window * self.config["context_reserve_percent"] + 99) // 100
            available = window - output - reserve
            if available <= 0:
                raise ValueError("declared model window leaves no kernel input space")
            trigger = min(trigger, available * self.config["context_bytes_per_token"])
            budget = min(budget, trigger * 3 // 4)
        return budget, trigger, output

    def start(self, params):
        budget, trigger, output = self.bounds(params)
        start_budget = budget // 2  # Reserve room for native turns in later prepared contexts.
        facts, surface = params["facts"], params["surface"]
        objectives = [index for index, fact in enumerate(facts) if fact.get("kind") == "work.objective.set"]
        indices = [objectives[-1]] if objectives else []
        updates = [index for index, fact in enumerate(facts) if fact.get("kind") == "work.message"]
        if updates and (not objectives or updates[-1] > objectives[-1]):
            indices.append(updates[-1])
        visible = {"facts": [facts[index] for index in indices], "surface": {},
                   "projection": {"surface_files": len(surface), "fact_count": len(facts),
                                  "archive_trigger_bytes": trigger, "projection_bytes": budget,
                                  "omitted_files": "Use Surface shell find/read; archive bodies are never injected."}}
        timestamp = params["timestamp"]
        def context():
            return {"systemPrompt": PROMPT, "messages": [{"role": "user", "content": encode(visible).decode(), "timestamp": timestamp}]}
        # Derive mandatory metadata space from the actual pointer shape. Small
        # valid windows must not fail because of an unrelated fixed reserve.
        reserved = {}
        if len(indices) < len(facts):
            reserved["fact_archive"] = {"path": "archive/" + "0" * 64 + ".json", "sha256": "0" * 64,
                                        "bytes": len(encode(facts)), "mode": "lossless"}
        if any(name.startswith("archive/") for name in surface):
            reserved["archive_index"] = {"path": "archive/index.jsonl", "files": len(surface)}
        if len(encode(context())) + len(encode(reserved)) > start_budget:
            raise ValueError("current objective exceeds kernel projection budget; shorten it or use a referenced Surface file")
        for index in range(len(facts) - 1, max(-1, len(facts) - 1 - self.config["recent_facts"]), -1):
            if index in indices:
                continue
            visible["facts"].append(facts[index])
            if len(encode(context())) > start_budget // 2:
                visible["facts"].pop()
            else:
                indices.append(index)
        visible["facts"] = [facts[index] for index in sorted(indices)]
        if len(indices) < len(facts):
            visible["fact_archive"] = save(self.surface, "facts", facts)
        priorities = [name for name in ("plan.md", "report.md", "notes.md") if name in surface]
        candidates = priorities + sorted(name for name in surface if name not in priorities and not name.startswith("archive/"))
        for name in candidates:
            content = surface[name]
            view = self.plan_view(content) if name == "plan.md" and isinstance(content, str) else content
            visible["surface"][name] = view
            if len(encode(context())) > start_budget - 256:
                visible["surface"][name] = {"path": name, "read_with": "Surface shell"}
                if len(encode(context())) > start_budget - 256:
                    del visible["surface"][name]
        archive_count = sum(name.startswith("archive/") for name in surface)
        if archive_count:
            visible["archive_index"] = {"path": "archive/index.jsonl", "files": archive_count}
        if len(encode(context())) > start_budget:
            raise ValueError("kernel projection metadata exceeds configured budget")
        return {"context": context(), "options": {"maxTokens": output},
                "max_turns": self.config["max_turns"], "timeout": self.config["timeout"]}

    @staticmethod
    def plan_view(content):
        active = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        steps = re.findall(r"^\s*[-*]\s+\[([ xX])\]\s+(.+)$", active, re.MULTILINE)
        pending = [title for checked, title in steps if checked == " "]
        return {"path": "plan.md", "current_step": pending[0] if pending else None,
                "next_step": pending[1] if len(pending) > 1 else None,
                "checked_steps": sum(checked != " " for checked, _ in steps),
                "content": content if len(content.encode()) <= 4096 else "Read complete plan and evidence with Surface shell.",
                "meaning": "Advisory progress only; checked boxes are not independently verified completion."}

    @staticmethod
    def continuation(params):
        return params["turn"]["message"].get("stopReason") == "toolUse"

    def prepare(self, params):
        context = params["turn"]["context"]
        messages = context["messages"]
        budget, trigger = self.config["projection_bytes"], self.config["archive_trigger_bytes"]
        if messages and messages[0].get("role") == "user" and isinstance(messages[0].get("content"), str):
            try:
                projection = json.loads(messages[0]["content"])["projection"]
                budget, trigger = projection["projection_bytes"], projection["archive_trigger_bytes"]
            except (ValueError, KeyError, TypeError):
                pass
        if len(encode(context)) <= trigger:
            return None
        if not messages or messages[0].get("role") != "user":
            raise ValueError("kernel archive requires its initial goal message")
        groups = []
        for message in messages[1:]:
            if message.get("role") == "user" and str(message.get("content", "")).startswith(ARCHIVE_MARKER):
                continue
            if message.get("role") == "toolResult":
                if not groups or groups[-1][0].get("role") != "assistant":
                    raise ValueError("orphan tool result in kernel context")
                groups[-1].append(message)
            else:
                groups.append([message])
        for group in groups:
            calls = {part["id"] for part in group[0].get("content", [])
                     if isinstance(part, dict) and part.get("type") == "toolCall"}
            results = [message.get("toolCallId") for message in group[1:]]
            if calls != set(results) or len(results) != len(set(results)):
                raise ValueError("incomplete tool group in kernel context")
        if not groups:
            raise ValueError("kernel cannot archive an oversized goal alone")
        # Archive the whole original before returning any reduced view. Existing
        # pointers in that context make the complete history recursively readable.
        reference = save(self.surface, "native-context", context)
        pointer = {"role": "user", "content": ARCHIVE_MARKER + encode(reference).decode(),
                   "timestamp": messages[0].get("timestamp", 0)}
        output = copy.deepcopy(context)
        output["messages"] = [messages[0], pointer]
        retained = []
        for group in reversed(groups):
            proposed = [group] + retained
            output["messages"] = [messages[0], pointer] + [message for part in proposed for message in part]
            if len(encode(output)) > budget:
                if not retained:
                    raise ValueError("latest complete tool turn and goal exceed kernel archive budget")
                break
            retained = proposed
            if len(retained) >= self.config["retained_turns"]:
                break
        output["messages"] = [messages[0], pointer] + [message for part in retained for message in part]
        return {"context": output}
