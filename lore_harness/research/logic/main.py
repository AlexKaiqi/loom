"""Research action parsing and derived saturation/completion."""
import hashlib
import json
import os
from pathlib import Path

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def _config():
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return {}


def parse(text):
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
        return {"type": "final", "text": raw}
    action = value.get("action", value) if isinstance(value, dict) else None
    if not isinstance(action, dict) or "type" not in action:
        return {"type": "final", "text": raw}
    if action["type"] == "recall":
        if not isinstance(action.get("query"), str) or not action["query"].strip():
            return {"type": "final", "text": raw}
    if action["type"] == "shell" and not isinstance(action.get("script"), str):
        return {"type": "final", "text": raw}
    if action["type"] == "emit":
        payload = action.get("payload") or {}
        if action.get("kind") == "research.source.added" and not payload.get("source_ref"):
            return {"type": "final", "text": raw}
        if action.get("kind") == "research.finding.recorded" and not payload.get("finding_ref"):
            return {"type": "final", "text": raw}
    return action


def guard(*, state, action):
    """Stop open-ended exploration: after two shell reads, declare what was actually read.

    The observed failure mode is a model that keeps grepping and cating the corpus
    and never records a source or a finding — a Round that looks busy but makes no
    progress and burns the context budget.
    """
    if action.get("type") != "shell":
        return None
    facts = state.get("facts", [])
    started_at = state.get("started_at_seq", 0)
    reads = [f for f in facts if f["kind"] == "sys.tool.result" and f["seq"] > started_at]
    progressed = any(
        f["kind"] in ("research.source.added", "research.finding.recorded") and f["seq"] > started_at
        for f in facts
    )
    if len(reads) >= 2 and not progressed:
        return ("You have read enough this Round. Declare what you actually read: emit research.source.added "
                "for each real file (with its digest) and research.finding.recorded with evidence_refs.")
    return None


def _digest(path):
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def settle(state):
    """Derive source digests from real bytes, then decide completion.

    The model only names files; `research.source.verified` and
    `research.source.invalid` are computed here from the actual content, so a
    model cannot fabricate evidence by declaring a hash.
    """
    content = Path(state["content_dir"])
    facts = state.get("facts", [])
    if any(fact["kind"] == "task.completed" for fact in facts):
        return []
    out = []

    added = [f for f in facts if f["kind"] == "research.source.added"]
    verified = {f["payload"].get("source_ref"): f["seq"] for f in facts if f["kind"] == "research.source.verified"}
    invalid = {f["payload"].get("source_ref"): f["seq"] for f in facts if f["kind"] == "research.source.invalid"}
    retracted = {f["payload"].get("source_ref"): f["seq"] for f in facts if f["kind"] == "research.source.retracted"}
    for fact in added:
        ref = fact["payload"].get("source_ref")
        if verified.get(ref, 0) > fact["seq"] or invalid.get(ref, 0) > fact["seq"]:
            continue
        if retracted.get(ref, 0) > fact["seq"]:
            continue
        excluded = [pre for pre in (_config().get("exclude_source_prefixes") or []) if ref and ref.startswith(pre)]
        if excluded:
            out.append({"kind": "research.source.invalid",
                        "payload": {"source_ref": ref, "claimed": None, "actual": None,
                                    "reason": "self-produced output is not a source (%s)" % excluded[0]}})
            continue
        actual = _digest(content / ref) if ref else None
        if actual is None:
            out.append({"kind": "research.source.invalid",
                        "payload": {"source_ref": ref, "claimed": None, "actual": None,
                                    "reason": "source file is missing"}})
        else:
            out.append({"kind": "research.source.verified",
                        "payload": {"source_ref": ref, "digest": actual}})

    saturation = [f for f in facts if f["kind"] == "research.saturation.reached"]
    # this Round's freshly derived verifications count for completion
    verified_now = dict(verified)
    for item in out:
        if item["kind"] == "research.source.verified":
            verified_now[item["payload"]["source_ref"]] = 10 ** 9
    invalid_now = dict(invalid)
    for item in out:
        if item["kind"] == "research.source.invalid":
            invalid_now[item["payload"]["source_ref"]] = 10 ** 9

    # A source is PENDING while its latest registration has no outcome yet; an
    # invalid source is a recorded refusal and simply does not count as evidence
    # (the model gets no credit, and the task is not deadlocked forever).
    def outcome_of(ref):
        return max(verified_now.get(ref, 0), invalid_now.get(ref, 0), retracted.get(ref, 0))

    pending = any(outcome_of(f["payload"].get("source_ref")) < f["seq"] for f in added)
    verified_count = len({ref for ref, seq in verified_now.items() if seq > 0})

    # Saturation is DERIVED from verified evidence (harness policy in config.json),
    # not something the model must declare: the model should not be the judge of
    # its own terminal state.
    config = _config()
    findings = [f for f in facts if f["kind"] == "research.finding.recorded"]
    evidence_ready = (verified_count >= int(config.get("saturation_min_sources", 2))
                      and len(findings) >= int(config.get("saturation_min_findings", 1))
                      and not pending)
    # Completion is threshold-driven: a model-declared saturation is an early,
    # non-binding claim and never substitutes for verified evidence.
    if evidence_ready:
        if not saturation:
            out.append({"kind": "research.saturation.reached",
                        "payload": {"reason": "derived: %d verified sources and %d findings"
                                              % (verified_count, len(findings))}})
        refs = []
        for fact in findings[-3:]:
            refs.extend(fact["payload"].get("evidence_refs") or [])
        out.append({"kind": "task.completed",
                    "payload": {"evidence_refs": refs or sorted(
                        ref for ref, seq in verified_now.items() if seq > 0)}})
    return out
