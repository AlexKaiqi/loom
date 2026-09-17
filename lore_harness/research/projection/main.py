"""Research projection: question, source index (pointers), findings, recent recall hits."""
import json

import lore_harness_base as base

ACTION_PROTOCOL = base.action_protocol([
    '{"action":{"type":"recall","query":"<literal text>","limit":20}}   search the corpus (runtime observation)',
    '{"action":{"type":"shell","script":"<sh script writing notes/findings in content>"}}',
    '{"action":{"type":"emit","kind":"research.source.added","payload":{"source_ref":"<relative file>","note":"..."}}}',
    '{"action":{"type":"emit","kind":"research.finding.recorded","payload":{"finding_ref":"<file>","evidence_refs":["<file>"]}}}',
    '{"action":{"type":"emit","kind":"research.saturation.reached","payload":{"reason":"..."}}}',
    base.FINAL_EXAMPLE,
])


def build(*, work, facts, new, head, content_dir, step=0, max_steps=1, rejected_final=None,
          userspaces=None, revision=None):
    folded = base.fold(facts, latest=("research.question.set",),
                       collect=("research.source.added", "research.finding.recorded", "sys.recall.result"),
                       flags=("research.saturation.reached",))
    question = folded["research.question.set"]
    sources, findings, recall = (folded["research.source.added"], folded["research.finding.recorded"],
                                 folded["sys.recall.result"])
    saturated = folded["research.saturation.reached"]
    verified = base.facts_since(facts, "research.source.verified", 0)
    invalid = base.facts_since(facts, "research.source.invalid", 0)
    rejected = base.facts_since(facts, "sys.action.rejected", 0)

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
            len({f["payload"].get("source_ref") for f in verified}),
            2),
        "findings recorded: %d / %d required" % (len(findings), 1),
        "verified source paths: %s" % sorted({f["payload"].get("source_ref") for f in verified}),
        "",
        "# Recent recall results (runtime observation, not re-run on recovery)",
        json.dumps([{"query": r.get("query"), "hits": len(r.get("matches") or []),
                     "files": sorted({m["file"] for m in r.get("matches") or []})} for r in recall[-3:]],
                   ensure_ascii=False),
        "",
        "# Corpus files (source_ref MUST be one of these relative paths; the harness derives the digest)",
        "Shell cwd IS this directory (use RELATIVE paths; never `cd` to an absolute path): %s" % content_dir,
        "files: %s" % (", ".join(base.content_files(content_dir)) or "(empty)"),
        "",
        "# Actions refused in this Round (do not repeat them)",
        json.dumps([f["payload"] for f in rejected][-2:], ensure_ascii=False),
        "",
        "# Sources that did NOT verify (recorded, and they never count as evidence)",
        json.dumps([{"ref": f["payload"].get("source_ref"), "reason": f["payload"].get("reason")}
                    for f in invalid][-3:], ensure_ascii=False),
        "",
    ]
    lines += base.budget_lines(step, max_steps)
    lines += [
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
    lines += base.rejected_final_lines(rejected_final)
    lines += ["", ACTION_PROTOCOL]
    return {
        "system": "You are the model inside one Round of a research work. Retrieve what you need, cite real "
                  "evidence, and stop when the question is answered.",
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
