# Kernel Harness contract

The included kernel is an external policy: ordinary Surface files hold its working memory, native Pi hooks bound its projection, and the existing remote shell reads and edits those files. It does not implement a model loop or a Runtime scheduler.

## Plan and working files

The manifest declares initial ordinary Surface files `plan.md`, `report.md` and `notes.md`. They are copied before the initial version snapshot; editing them never edits the fixed Harness templates. A Markdown plan projects its first unchecked step and the next unchecked step, with a reference to the full file. The policy instructs the model to record evidence paths and uncertainty before checking a step and to revise the plan when new user input or evidence warrants it. Large plan bodies remain readable by the Surface shell. Simple tasks do not require a plan.

These are progress and context helpers. There is no automatic stage acceptance, evidence-verification engine or business-completion event. Runtime does not interpret Markdown checkboxes. Surface archives are also ordinary editable content; authoritative event and execution custody remains in Runtime storage.

## Lossless context archive

Before discarding a visible fact or native message prefix, kernel persists the original facts/context as UTF-8 JSON in `surface/archive/<sha256>.json`, fsyncs the file and containing directory, and returns its relative path, digest and byte length in the next context. Originals are not deleted. Existing archive pointers remain reachable through the archived native context; a bounded current pointer replaces an unbounded in-context archive list. `archive/index.jsonl` is an append-only human/tool lookup aid, not the source of truth.

Surface files omitted from a new Round projection remain ordinary files and can be read by the existing Surface shell. Current objective, recent messages and the working files `plan.md`, `report.md`, and `notes.md` receive priority. The latest user correction is mandatory alongside the current objective. An oversized mandatory input fails explicitly instead of silently truncating the requirement. Facts omitted from the projection remain in the archive, as well as Runtime custody.

The fixed `policy.json` configures UTF-8 JSON byte budgets, recent fact/turn counts, and Round limits. These are measurable projection budgets, not claimed provider token measurements. The policy explicitly sets native `options.maxTokens`, capped by its configured output budget, the supported model output capacity and one quarter of the context window. Model capacity is not the same as requested output. The policy uses the portable model context bound and this actual requested output when supplied to reduce its maximum visible budget using the configured byte/token estimate and proportional protocol reserve. The actual mandatory prompt/input/pointer bytes determine whether the initial working set fits; a fixed overhead must not exclude a previously usable small model window. The estimate is not a provider context-limit guarantee. It does not change the declared model or host transport.

At a confirmed native turn boundary, `policy.prepare` may replace the visible context with its initial goal, an archive pointer, and recent complete assistant/tool-result groups. A tool call and its results cannot be split by clipping. If the mandatory goal, pointer and latest complete group cannot fit, it fails explicitly; it never deletes a partial group to manufacture a bounded request. An archive write/fsync failure prevents returning a reduced context. There is no LLM summary or second provider call.

A fixed Harness locates its Work Surface relative to its copied directory. Surface/archive ancestors must be real directories, never symlinks; archive targets and the index must be ordinary files with a single hard link. This is a trusted Harness's ordinary filesystem access during its single-owner Round, not a new host capability available to model commands. Runtime still performs final Surface version capture.

## Executable checks

Component tests must directly verify persisted JSON/digests, archive-chain retrieval, byte bounds, complete tool groups, non-mutation of source files, rejection of symlink destinations, and refusal to shrink on persistence failure. Integration acceptance must observe the actual next provider request, not just a policy return value. Ordinary plan-file advice is not a business-completion gate; no checked Markdown box or model assertion becomes Runtime completion evidence.
