"""Research projection: question, source index (pointers), findings, recent recall hits."""
import json

ACTION_PROTOCOL = (
    'Reply with exactly one JSON object and no prose. One of:\n'
    '{"action":{"type":"recall","query":"<literal text>","limit":20}}   search the corpus (runtime observation)\n'
    '{"action":{"type":"shell","script":"<sh script writing notes/findings in content>"}}\n'
    '{"action":{"type":"emit","kind":"research.source.added","payload":{"source_ref":"<relative file>","note":"..."}}}\n'
    '{"action":{"type":"emit","kind":"research.finding.recorded","payload":{"finding_ref":"<file>","evidence_refs":["<file>"]}}}\n'
    '{"action":{"type":"emit","kind":"research.saturation.reached","payload":{"reason":"..."}}}\n'
    '{"action":{"type":"final","text":"<reason>"}}'
)


def build(*, task, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          workspaces=None, revision=None):
    question, sources, findings, recall, saturated = None, [], [], [], False
    for fact in facts:
        kind = fact["kind"]
        if kind == "research.question.set":
            question = fact["payload"]
        elif kind == "research.source.added":
            sources.append(fact["payload"])
        elif kind == "research.finding.recorded":
            findings.append(fact["payload"])
        elif kind == "sys.recall.result":
            recall.append(fact["payload"])
        elif kind == "research.saturation.reached":
            saturated = True
    files = sorted(str(p.relative_to(content_dir)) for p in content_dir.rglob("*") if p.is_file())

    lines = [
        "# Research question",
        json.dumps(question, ensure_ascii=False),
        "saturated: %s" % saturated,
        "",
        "# Source index (pointers only; bodies stay in content)",
        json.dumps([{"ref": s.get("source_ref"), "digest": s.get("digest")} for s in sources[-8:]], ensure_ascii=False),
        "",
        "# Findings recorded",
        json.dumps([f.get("finding_ref") for f in findings[-5:]], ensure_ascii=False),
        "",
        "# Evidence progress (saturation is derived by the harness from DISTINCT verified sources)",
        "distinct verified sources: %d / %d required" % (
            len({f["payload"].get("source_ref") for f in facts if f["kind"] == "research.source.verified"}),
            2),
        "findings recorded: %d / %d required" % (len(findings), 1),
        "verified source paths: %s" % sorted(
            {f["payload"].get("source_ref") for f in facts if f["kind"] == "research.source.verified"}),
        "",
        "# Recent recall results (runtime observation, not re-run on recovery)",
        json.dumps([{"query": r.get("query"), "hits": len(r.get("matches") or []),
                     "files": sorted({m["file"] for m in r.get("matches") or []})} for r in recall[-3:]],
                   ensure_ascii=False),
        "",
        "# Corpus files (source_ref MUST be one of these relative paths; the harness derives the digest)",
        "Shell cwd IS this directory (use RELATIVE paths; never `cd` to an absolute path): %s" % content_dir,
        "files: %s" % (", ".join(files) if files else "(empty)"),
        "",
        "# Actions refused in this Round (do not repeat them)",
        json.dumps([f["payload"] for f in facts if f["kind"] == "sys.action.rejected"][-2:], ensure_ascii=False),
        "",
        "# Sources that did NOT verify (recorded, and they never count as evidence)",
        json.dumps([{"ref": f["payload"].get("source_ref"), "reason": f["payload"].get("reason")}
                    for f in facts if f["kind"] == "research.source.invalid"][-3:], ensure_ascii=False),
        "",
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
        "# Rules",
        "0. Your reply must be exactly ONE JSON object. The answer belongs in a recorded finding, never in the reply.",
        "1. Use the `recall` action to locate material, then read what you need with `cat <relative file>`. "
        "The shell already runs inside the corpus, so `cat a-notes.md` is correct and `cd <abs path>` is wrong.",
        "2. Register each CORPUS file you actually read as a source. Repeating the SAME path counts once: you need "
        "at least two DISTINCT corpus files (check \"distinct verified sources\" above). Your own notes/synthesis "
        "under findings/ are NOT sources.",
        "3. Write your synthesis under content and record a finding with evidence_refs.",
        "4. Emit research.saturation.reached only when the question is answered by the recorded findings.",
        "5. Do not invent sources or findings you did not actually read.",
        "6. If a source you registered cannot be verified (missing file), retract it with research.source.retracted; "
        "you cannot complete while an unretracted invalid source remains.",
    ]
    if rejected_final:
        lines += ["", "# Rejected final", rejected_final[:200]]
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": "You are the model inside one Round of a research task. Retrieve what you need, cite real "
                  "evidence, and stop when the question is answered.",
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
