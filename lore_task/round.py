"""Round engine: trigger -> projection -> model -> tools -> facts -> commit.

Commit ordering follows landing §6: facts land, content revision is computed,
the ledger round record is appended, then `surface/head` advances atomically.
Model interaction is observation (zone B, `session/rounds/`), never fact.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from . import facts as facts_mod
from . import ledger
from . import manifest as manifest_mod
from .layout import LAYOUT_VERSION, atomic_write, paths, read_json, tree_digest, write_json

TOOL_OUTPUT_INLINE = 4000

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object, no prose: '
    '{"action":{"type":"shell","script":"..."}} to run a shell command inside the task content directory, '
    '{"action":{"type":"emit","kind":"<declared kind>","payload":{...}}} to declare a state change, or '
    '{"action":{"type":"final","text":"..."}} to end this round.'
)


def _now() -> int:
    return int(time.time())


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _truncate(text: str, limit: int = TOOL_OUTPUT_INLINE) -> str:
    data = text.encode("utf-8", "replace")
    return text if len(data) <= limit else data[:limit].decode("utf-8", "ignore")


def _session_append(p, round_id: str, row: dict) -> None:
    directory = p["session"] / "rounds"
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / (round_id + ".jsonl"), "ab") as fh:
        fh.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())


def _run_shell(cwd, script: str, timeout: float) -> dict:
    proc = subprocess.run(["/bin/sh", "-c", script], cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return {"exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _default_projection(task, all_facts, new, head, content_dir) -> dict:
    body = ["# Task", json.dumps({"task_id": task.get("task_id"), "state": task.get("state")}, ensure_ascii=False)]
    body.append("\n# New facts since last round")
    for fact in new[-20:] or all_facts[-20:]:
        body.append("- [%s] %s %s" % (fact["seq"], fact["kind"], json.dumps(fact["payload"], ensure_ascii=False)[:400]))
    files = sorted(str(p.relative_to(content_dir)) for p in content_dir.rglob("*") if p.is_file())
    body.append("\n# content/ files: " + (", ".join(files) if files else "(empty)"))
    body.append("\n" + ACTION_PROTOCOL)
    return {
        "system": "You are the model inside one task Round. Work locally in the content directory. "
                  "Declare state changes as declared facts; do not invent event kinds.",
        "messages": [{"role": "user", "content": "\n".join(body)}],
    }


def _default_parse(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"type": "none"}
    raw = text
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"type": "final", "text": text}
    action = value.get("action", value) if isinstance(value, dict) else None
    if not isinstance(action, dict) or "type" not in action:
        return {"type": "final", "text": text}
    return action


def _assert_harness_readonly(base, task) -> None:
    """The harness area is registered read-only; a Round must never change it."""
    current = tree_digest(paths(base)["harness"])
    expected = (task.get("harness") or {}).get("digest")
    if expected and current != expected:
        raise RuntimeError(f"harness area changed during the Round: {expected} -> {current}")


def _resolve_target(task, content_dir, target):
    """Route an execution target to an authorized working directory.

    `content` is the task's own writable area; `workspace`/`workspace:<id>` must
    name a range declared in task.json. Unknown or unauthorized targets are
    refused; there is no fallback to the host (v5:190). This is routing and
    bookkeeping only — real isolation is X's job and is NOT implemented here.
    """
    if target in (None, "content", "surface"):
        return Path(content_dir)
    name = target.split(":", 1)[1] if isinstance(target, str) and target.startswith("workspace:") else None
    for workspace in task.get("workspaces", []) or []:
        if target == "workspace" or workspace.get("id") == name:
            return Path(workspace["path"])
    return None


def _require_supported_layout(task) -> None:
    """landing §10: an unknown higher layout_version is refused loudly."""
    version = int(task.get("layout_version") or 0)
    if version > LAYOUT_VERSION:
        raise ValueError("unsupported task layout_version %s (runtime supports <= %s)"
                         % (version, LAYOUT_VERSION))


def _recall(root, query: str, limit: int):
    """Deterministic content recall: literal, case-insensitive, bounded.

    This is a runtime observation over the task's own content (no model call and
    no embeddings). A model-assisted recall is NOT implemented; the result is
    recorded as a fact so replay restores it without re-running the search.
    """
    matches, scanned = [], 0
    needle = (query or "").lower()
    if not needle:
        return matches, scanned
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        for number, line in enumerate(text.split("\n"), 1):   # "\n" only, same rule as JSONL
            if needle in line.lower():
                matches.append({"file": str(path.relative_to(root)), "line": number,
                                "snippet": line.strip()[:200]})
                if len(matches) >= limit:
                    return matches, scanned
    return matches, scanned


def _should_continue(man, state) -> bool:
    """Round end condition belongs to the harness (`rounds` role), not the runtime."""
    module = man.module("rounds")
    hook = getattr(module, "should_continue", None) if module is not None else None
    return True if not callable(hook) else bool(hook(state=state))


def _should_start(man, task, all_facts, new, head, now=None) -> bool:
    module = man.module("rounds")
    hook = getattr(module, "should_start", None) if module is not None else None
    if callable(hook):
        return bool(hook(task=task, facts=all_facts, new=new, head=head, now=now))
    if not new:
        return False
    trigger_kinds = {kind for trig in man.triggers for kind in trig["on"]}
    if not trigger_kinds:
        return True
    return any(fact["kind"] in trigger_kinds for fact in new)


def recover(base, *, keep=None, reason="uncommitted tail from an interrupted Round") -> dict:
    """Resolve an interrupted Round without losing bytes or data.

    Two distinct interruptions are handled:
    1. a `phase=start` marker with no commit -> quarantine the uncommitted tail
       **byte-for-byte** under `session/crashed/`, truncate facts to that Round's
       `trigger_seq`, and record the repair;
    2. a `phase=commit` row whose `facts_end` was never published to `head`
       (crash between the two writes) -> **publish** the commit (advance `head`
       to what the ledger already recorded) instead of discarding committed facts.
    """
    p = paths(base)
    _require_supported_layout(read_json(p["task"]))
    head = read_json(p["head"])
    rows = ledger.read_jsonl(p["rounds"])
    commits = [r for r in rows if r.get("phase", "commit") == "commit"]

    if commits and head.get("facts_end", {}).get("seq", 0) < commits[-1].get("facts_end", {}).get("seq", 0):
        record = commits[-1]
        seq = record["facts_end"]["seq"]
        if len(facts_mod.read_facts(base)) < seq:
            raise ValueError("cannot publish commit %s: facts end at %d, commit needs %d"
                             % (record.get("round_id"), len(facts_mod.read_facts(base)), seq))
        row = {"kind": "repair", "action": "published_commit", "round_id": record.get("round_id"),
               "published_seq": seq, "at": _now()}
        # trace BEFORE publishing (a fault after the head write must not lose the
        # trace), but do not duplicate an identical trace on retry
        already = any(r.get("action") == "published_commit" and r.get("round_id") == record.get("round_id")
                      for r in ledger.read_jsonl(p["ledger"] / "repairs.jsonl"))
        if not already:
            ledger.append_jsonl(p["ledger"] / "repairs.jsonl", row)
        write_json(p["head"], {
            "layout_version": LAYOUT_VERSION,
            "revision": record.get("revision"),
            "facts_end": record["facts_end"],
            "round_id": record.get("round_id"),
            "ledger_seq": len(commits),
        })
        return {"status": "recovered", **row}

    # An interrupted Round is identified by a `start` marker with no later commit.
    # `recover` only ever acts on that shape: once an `abort` marker is the last
    # row, a repeated call MUST be a no-op — otherwise it would treat the commit
    # floor as 0 and delete admitted facts (independent acceptance A-N7).
    interrupted = rows[-1] if rows and rows[-1].get("phase") == "start" else None
    if interrupted is None:
        return {"status": "nothing_to_recover", "reason": "no interrupted round",
                "committed_seq": head.get("facts_end", {}).get("seq", 0)}
    if interrupted.get("trigger_seq") is None:
        # never guess the commit floor from a hand-edited/foreign directory
        raise ValueError("interrupted round %s has no trigger_seq; refusing to guess the commit floor"
                         % interrupted.get("round_id"))
    committed = interrupted["trigger_seq"]
    raw = p["facts"].read_bytes() if p["facts"].exists() else b""
    parts = raw.split(b"\n")
    if parts and parts[-1] == b"":
        parts = parts[:-1]

    def _finish_abort():
        """Write the abort marker unless it is already the last ledger row.

        Doing this even when there is nothing left to truncate makes `recover`
        resumable after a fault that happened between its own writes (A-N2/N3),
        and the marker carries the commit floor so repeat calls stay no-ops.
        """
        rows_now = ledger.read_jsonl(p["rounds"])
        if rows_now and rows_now[-1].get("phase") == "start":
            ledger.append_jsonl(p["rounds"], {
                "phase": "abort", "round_id": rows_now[-1].get("round_id"),
                "trigger_seq": rows_now[-1].get("trigger_seq"), "reason": reason, "at": _now()})

    if len(parts) <= committed:
        _finish_abort()
        return {"status": "nothing_to_recover", "committed_seq": committed, "aborted_start": True}
    keep_seq = committed if keep is None else int(keep)
    if keep_seq < committed or keep_seq > len(parts):
        raise ValueError("keep must stay between the commit point and the last fact")
    saved_dir = p["session"] / "crashed"
    saved_dir.mkdir(parents=True, exist_ok=True)
    saved = saved_dir / ("facts-after-%d-%d.jsonl" % (committed, _now()))
    # byte-for-byte: the discarded lines are copied verbatim, not re-serialized
    tail_lines = parts[keep_seq:]
    saved.write_bytes(b"".join(line + b"\n" for line in tail_lines))

    def _id(line):
        try:
            return json.loads(line).get("id", "<unparsable>")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "<torn:%d bytes>" % len(line)   # a torn tail must never abort recovery

    row = {"kind": "repair", "reason": reason, "committed_seq": committed, "kept_seq": keep_seq,
           "discarded": [_id(line) for line in tail_lines],
           "saved": str(saved.relative_to(base)), "at": _now(),
           "byte_identical": True}
    # trace BEFORE truncating: if we die mid-recover the trace already exists
    ledger.append_jsonl(p["ledger"] / "repairs.jsonl", row)
    atomic_write(p["facts"], b"".join(line + b"\n" for line in parts[:keep_seq]))
    _finish_abort()
    return {"status": "recovered", **row}


def ingest(base, foreign_id: str, kind: str, payload: dict, *, source=None, sender=None) -> dict:
    """External fact admission: single gate, idempotent by foreign id."""
    _require_supported_layout(read_json(paths(base)["task"]))
    man = manifest_mod.load(base)
    entry = man.require_kind(kind)
    if entry.get("requires_relation") and sender is None:
        # admission is not authorization: a cross-task kind must arrive through
        # `deliver`, which checks wants+grants and the host authority entry.
        raise ValueError("kind %s requires relation-mediated delivery (use deliver with wants+grants)" % kind)
    for row in ledger.read_jsonl(paths(base)["admission"]):
        if row.get("foreign_id") == foreign_id:
            if row.get("digest") != ledger.admission_digest(kind, payload):
                raise ValueError(f"admission conflict: {foreign_id!r} with different content")
            return {"admission": row, "created": False, "fact": None}
    admission = man.module("admission")
    accept_hook = getattr(admission, "accept", None) if admission is not None else None
    accepted = True if accept_hook is None else bool(accept_hook(kind=kind, payload=payload))
    fact = None
    if accepted:
        fact = facts_mod.append_fact(base, kind, payload, source=source or entry.get("producer", "external"))
    if sender is not None:
        ledger.append_jsonl(paths(base)["admission"], {
            "foreign_id": foreign_id, "kind": kind, "digest": ledger.admission_digest(kind, payload),
            "decision": "accepted" if accepted else "rejected", "fact_id": (fact or {}).get("id"),
            "from": sender})
        return {"admission": {"foreign_id": foreign_id, "kind": kind, "decision": "accepted" if accepted else "rejected",
                              "from": sender}, "created": True, "fact": fact}
    row, _ = ledger.admit(base, foreign_id, kind, payload, accepted=accepted, fact=fact)
    return {"admission": row, "created": True, "fact": fact}


def relate(base, *, want=None, grant=None) -> dict:
    """Declare a cross-task relation.

    `wants` is declared by the consumer (which peer/kinds it accepts); `grants`
    by the sender (which peer/kinds it allows itself to send). Both sides are
    required for a delivery — a copy of a task directory never inherits either.
    """
    p = paths(base)
    task = read_json(p["task"])
    relations = task.setdefault("relations", {"wants": [], "grants": []})
    if want:
        peer, kinds = want
        relations.setdefault("wants", []).append({"peer": peer, "kinds": list(kinds)})
    if grant:
        peer, kinds = grant
        relations.setdefault("grants", []).append({"peer": peer, "kinds": list(kinds)})
    write_json(p["task"], task)
    return {"task_id": task.get("task_id"), "relations": relations}


def deliver(from_base, to_base, foreign_id: str, kind: str, payload: dict) -> dict:
    """Deliver one event from one task's fact stream to another task's admission.

    Authorized only when (a) both tasks are registered in their root's host
    authority file at their current location, and (b) the receiver *wants* it and
    the sender *grants* it. A copied task directory keeps the relations text but
    has no authority entry, so **a copy never inherits authority** (landing §9-3,
    I8). Refusals are recorded on the receiver's admission ledger; there is no
    implicit authority and no fallback.
    """
    from .layout import authority_entry
    sender = read_json(paths(from_base)["task"])
    receiver = read_json(paths(to_base)["task"])
    _require_supported_layout(sender)
    _require_supported_layout(receiver)
    sender_id, receiver_id = sender.get("task_id"), receiver.get("task_id")
    for base_path, task_id, label in ((from_base, sender_id, "sender"), (to_base, receiver_id, "receiver")):
        root = Path(base_path).resolve().parent
        entry = authority_entry(root, task_id)
        if not entry or Path(entry.get("root", "")).resolve() != Path(base_path).resolve():
            row = ledger.append_jsonl(paths(to_base)["admission"], {
                "foreign_id": foreign_id, "kind": kind, "digest": ledger.admission_digest(kind, payload),
                "decision": "rejected", "from": sender_id,
                "reason": "%s task %s is not registered at this location (a copy has no authority)"
                          % (label, task_id)})
            return {"delivered": False, "reason": row["reason"], "admission": row}
    wants = [w for w in receiver.get("relations", {}).get("wants", [])
             if w.get("peer") == sender_id and kind in (w.get("kinds") or [])]
    grants = [g for g in sender.get("relations", {}).get("grants", [])
              if g.get("peer") == receiver_id and kind in (g.get("kinds") or [])]
    if not wants or not grants:
        row = ledger.append_jsonl(paths(to_base)["admission"], {
            "foreign_id": foreign_id, "kind": kind, "digest": ledger.admission_digest(kind, payload),
            "decision": "rejected", "from": sender_id,
            "reason": "missing %s" % ("wants" if not wants else "grants")})
        return {"delivered": False, "reason": row["reason"], "admission": row}
    result = ingest(to_base, foreign_id, kind, payload, source="relation", sender=sender_id)
    return {"delivered": result["admission"].get("decision") == "accepted", "from": sender_id, **result}


def run_round(base, provider, *, max_steps: int = 8, tool_timeout: float = 30.0) -> dict:
    p = paths(base)
    man = manifest_mod.load(base)
    task = read_json(p["task"])
    head = read_json(p["head"])
    _require_supported_layout(task)
    if task.get("state", {}).get("lifecycle") != "active":
        return {"status": "archived"}
    _assert_harness_readonly(base, task)
    repaired = facts_mod.repair_torn_tail(base)
    if repaired["discarded_bytes"]:
        state_warning = {"torn_tail_repaired": repaired}
    else:
        state_warning = None

    all_facts = facts_mod.read_facts(base)
    commits = ledger.round_records(base)
    if commits and head.get("facts_end", {}).get("seq", 0) < commits[-1].get("facts_end", {}).get("seq", 0):
        # A Round committed in the ledger but never published to `head` (crash
        # between the two writes). Never start a new Round on top of that.
        return {"status": "recovery_needed", "reason": "commit_not_published",
                "round_id": commits[-1].get("round_id"),
                "published_seq": head.get("facts_end", {}).get("seq", 0),
                "committed_seq": commits[-1]["facts_end"]["seq"]}
    last_row = ledger.last_row(base)
    if last_row is not None and last_row.get("phase") == "start":
        # An earlier Round started but never committed. Never continue on top of it.
        uncommitted = [fact for fact in all_facts if fact["seq"] > last_row.get("trigger_seq", 0)]
        return {"status": "recovery_needed", "round_id": last_row.get("round_id"),
                "uncommitted": len(uncommitted), "last_committed_seq": last_row.get("trigger_seq", 0)}
    trigger_watermark = max([row.get("trigger_seq", 0) for row in ledger.round_records(base)] or [0])
    new = [fact for fact in all_facts if fact["seq"] > trigger_watermark]
    if not _should_start(man, task, all_facts, new, head, now=int(time.time())):
        return {"status": "no_trigger", "pending": len(new), "trigger_watermark": trigger_watermark}
    trigger_seq = all_facts[-1]["seq"] if all_facts else 0

    projection = man.module("projection")
    logic = man.module("logic")
    round_id = "round-%04d-%d" % (ledger.round_count(base) + 1, _now())
    started = _now()
    steps, emitted = [], []
    state = {"task": task, "facts": all_facts, "new": new, "content_dir": str(p["content"]),
             "round_id": round_id, "started_at_seq": trigger_seq, "base_rev": head.get("revision")}
    ledger.append_jsonl(p["rounds"], {"phase": "start", "round_id": round_id,
                                      "trigger_seq": trigger_seq, "at": started})

    state["rejected_final"] = None
    for step in range(max_steps):
        build = getattr(projection, "build", None) if projection is not None else None
        if callable(build):
            view = build(task=task, facts=all_facts, new=new, head=head, content_dir=p["content"],
                         step=step, max_steps=max_steps, rejected_final=state.get("rejected_final"),
                         workspaces=task.get("workspaces", []), revision=head.get("revision"))
        else:
            view = _default_projection(task, all_facts, new, head, p["content"])
        messages = [{"role": "system", "content": view.get("system", "")}] + list(view.get("messages") or [])
        if "sys.context.usage" in man.kinds:
            # Canonical runtime observation (P7), opt-in by declaration. The
            # threshold that acts on it is harness configuration, not runtime.
            projection_bytes = len((view.get("system") or "").encode("utf-8")) + sum(
                len(m.get("content", "").encode("utf-8")) for m in messages if isinstance(m.get("content"), str))
            facts_mod.append_fact(base, "sys.context.usage", {
                "step": step, "projection_bytes": projection_bytes, "facts": len(all_facts),
                "content_files": len([x for x in p["content"].rglob("*") if x.is_file()]),
            }, source="runtime")
            all_facts = facts_mod.read_facts(base)
            state["facts"] = all_facts
        reply = provider.complete(messages)
        _session_append(p, round_id, {
            "step": step,
            "request": messages,
            "reply": {k: reply.get(k) for k in ("content", "reasoning", "model", "finish_reason", "usage")},
        })
        parse = getattr(logic, "parse", None) if logic is not None else None
        action = parse(reply.get("content") or "") if callable(parse) else _default_parse(reply.get("content") or "")
        action = action if isinstance(action, dict) else {"type": "none"}
        guard = getattr(logic, "guard", None) if logic is not None else None
        if callable(guard):
            # The harness may refuse an action before it runs (e.g. rewriting the
            # same deliverable instead of declaring progress). Refusals are facts.
            reason = guard(state=state, action=action)
            if reason:
                if "sys.action.rejected" not in man.kinds:
                    raise manifest_mod.ManifestError(
                        "logic.guard requires a declared sys.action.rejected kind")
                fact = facts_mod.append_fact(base, "sys.action.rejected",
                                             {"action": action.get("type"), "reason": reason},
                                             source="runtime")
                steps.append({"step": step, "action": "rejected", "reason": reason,
                              "finish_reason": reply.get("finish_reason"), "usage": reply.get("usage")})
                emitted.append(fact["id"])
                all_facts = facts_mod.read_facts(base)
                state["facts"] = all_facts
                if not _should_continue(man, state):
                    break
                continue
        steps.append({"step": step, "action": action.get("type"), "finish_reason": reply.get("finish_reason"),
                      "usage": reply.get("usage")})
        kind = action.get("type")

        if kind == "final":
            # `final` is a proposal to end the Round; the harness's `rounds`
            # role decides whether the Round may actually end (design §4.4 E3).
            state["final"] = action.get("text", "")
            if not _should_continue(man, state):
                break
            state["rejected_final"] = state["final"]
            all_facts = facts_mod.read_facts(base)
            state["facts"] = all_facts
            continue
        if kind == "shell":
            target = action.get("target", "content")
            cwd = _resolve_target(task, p["content"], target)
            if cwd is None:
                out = {"exit": 126, "stdout": "", "stderr": "unauthorized or unknown shell target: %s" % target}
            else:
                try:
                    out = _run_shell(cwd, action.get("script", ""), tool_timeout)
                except subprocess.TimeoutExpired:
                    out = {"exit": 124, "stdout": "", "stderr": "timeout"}
            fact = facts_mod.append_fact(base, "sys.tool.result", {
                "script": action.get("script", ""), "target": target,
                "cwd": str(cwd) if cwd is not None else None, "exit": out["exit"],
                "stdout_digest": _digest_text(out["stdout"]), "stdout": _truncate(out["stdout"]),
                "stderr": _truncate(out["stderr"]),
            }, source="runtime")
            emitted.append(fact["id"])
            all_facts = facts_mod.read_facts(base)
            state["facts"] = all_facts
            if not _should_continue(man, state):
                break
            continue
        if kind == "recall":
            if "sys.recall.result" not in man.kinds:
                raise manifest_mod.ManifestError("recall requires a declared sys.recall.result kind")
            query = action.get("query") or ""
            limit = int(action.get("limit") or 20)
            matches, scanned = _recall(p["content"], query, limit)
            fact = facts_mod.append_fact(base, "sys.recall.result", {
                "query": query, "matches": matches, "scanned_files": scanned,
                "truncated": len(matches) >= limit,
            }, source="runtime")
            emitted.append(fact["id"])
            all_facts = facts_mod.read_facts(base)
            state["facts"] = all_facts
            if not _should_continue(man, state):
                break
            continue
        if kind == "emit":
            declared = action.get("kind", "")
            man.require_kind(declared, producer="harness")
            base_rev = action.get("base_rev")
            if base_rev is not None:
                # Conditional declaration: the model asserts which committed
                # revision it based the declaration on. A stale or fabricated
                # base is refused and recorded, never silently applied.
                committed_rev = state.get("base_rev")
                if base_rev != committed_rev:
                    if "sys.declaration.rejected" not in man.kinds:
                        raise manifest_mod.ManifestError(
                            "conditional emit requires a declared sys.declaration.rejected kind")
                    fact = facts_mod.append_fact(base, "sys.declaration.rejected", {
                        "kind": declared, "base_rev": base_rev, "committed_rev": committed_rev,
                        "reason": "stale base revision",
                    }, source="runtime")
                    emitted.append(fact["id"])
                    all_facts = facts_mod.read_facts(base)
                    state["facts"] = all_facts
                    if not _should_continue(man, state):
                        break
                    continue
            fact = facts_mod.append_fact(base, declared, action.get("payload") or {}, source="harness")
            emitted.append(fact["id"])
            all_facts = facts_mod.read_facts(base)
            state["facts"] = all_facts
            if not _should_continue(man, state):
                break
            continue
        break

    settle = getattr(logic, "settle", None) if logic is not None else None
    if callable(settle):
        state["emitted"] = list(emitted)
        state["facts"] = all_facts
        for item in settle(state) or []:
            man.require_kind(item["kind"], producer="harness")
            fact = facts_mod.append_fact(base, item["kind"], item.get("payload") or {}, source="harness")
            emitted.append(fact["id"])
            all_facts = facts_mod.read_facts(base)

    _assert_harness_readonly(base, task)
    revision = tree_digest(p["content"])
    last = all_facts[-1] if all_facts else None
    record = {
        "phase": "commit",
        "round_id": round_id, "started": started, "ended": _now(), "steps": steps,
        "revision": revision, "emitted": emitted, "trigger_seq": trigger_seq,
        "facts_end": {"seq": last["seq"] if last else 0,
                      "digest": last["digest"] if last else head["facts_end"]["digest"]},
        "session": "session/rounds/%s.jsonl" % round_id,
    }
    ledger.record_round(base, record)
    write_json(p["head"], {
        "layout_version": LAYOUT_VERSION, "revision": revision, "facts_end": record["facts_end"],
        "round_id": round_id, "ledger_seq": ledger.round_count(base),
    })
    result = {"status": "committed", "round_id": round_id, "steps": len(steps), "emitted": emitted, "revision": revision}
    if state_warning:
        result.update(state_warning)
    return result


def status(base) -> dict:
    p = paths(base)
    task = read_json(p["task"])
    head = read_json(p["head"])
    all_facts = facts_mod.read_facts(base)
    return {
        "task_id": task.get("task_id"), "lifecycle": task.get("state", {}).get("lifecycle"),
        "layout_version": task.get("layout_version"), "harness": task.get("harness"),
        "facts": len(all_facts), "rounds": ledger.round_count(base),
        "head": head, "admission_rows": len(ledger.read_jsonl(p["admission"])),
        "content_files": sorted(str(x.relative_to(p["content"])) for x in p["content"].rglob("*") if x.is_file()),
    }
