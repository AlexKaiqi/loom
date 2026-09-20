# Kernel Harness

This is the smallest included general-purpose Harness. Runtime supplies durable work and isolated tools; Pi owns the model/tool loop. Kernel chooses the context, working-file conventions, archive policy and when that loop should stop.

New Works start with three ordinary Surface files:

- `report.md`: achieved results, evidence and unresolved limits.
- `notes.md`: working observations, decisions and next actions.
- `plan.md`: optional Markdown checkboxes for multi-step work. The first unchecked step and its successor receive explicit projection. Evidence can be ordinary relative file paths written beside each step. Checking a box is a progress note, not independently verified completion or a Runtime scheduling instruction.

The model uses the existing remote `shell` tool to edit these files. There is no separate plan database, content API or planning engine. A new Round projects the latest objective, recent messages and priority working files. The complete original facts are archived if the bounded view omits any. Other Surface files remain available through the same shell.

Long native histories are archived without an LLM summary. `policy.prepare` persists their exact JSON in `archive/<sha256>.json`, then returns the goal, a digest-bearing pointer and recent complete tool-call/result groups. `archive/index.jsonl` lists generated archives. A newer archive may contain pointers to earlier archives; follow these to retrieve older history. Originals remain ordinary Surface files and travel with Work exports. Archive bodies are never automatically nested into the next Round's initial projection.

The fixed `policy.json` defines UTF-8 JSON byte budgets and Round limits. Defaults are a 12 KiB initial context, a 48 KiB archive trigger and a 24 KiB retained context with at most two recent complete turns. Kernel explicitly requests an output limit of at most `max_output_tokens` (default 4096), additionally capped by the model output capacity and one quarter of its context window. A catalog model's maximum supported output is not assumed to be the current request budget. Model context bounds and this actual requested output budget can reduce the visible budgets. The configured byte/token estimate (default 2) and proportional protocol reserve (default 6%) avoid imposing an unrelated fixed minimum model window. The actual mandatory goal, prompt and archive-pointer size must fit the resulting initial budget. These are working-set estimates, not exact token accounting or a guarantee against provider context limits. An oversized mandatory goal or indivisible latest tool group fails explicitly instead of silently losing information; an archive-write failure never returns a pointer to unpersisted content.

Archive behavior and Markdown planning are minimal aids. This Harness does not validate arbitrary business acceptance criteria, automatically schedule waiting stages, call an LLM summarizer or implement a sophisticated retrieval strategy. Those remain external policy choices.

Run its component checks with:

```sh
python3 -m unittest discover -s tests/harness -v
```
