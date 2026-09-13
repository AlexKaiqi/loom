# M01-004: conservative input reservation and ordinary text reduction

The second sample stopped before its fifth HTTP request, not from an observed token overrun. Four original responses report prompt tokens **897 + 1348 + 1831 + 2120 = 6196**. The fifth actual Node frame re-encodes to **10881 B**; admission computes 6196 + 10881 = **17077**, above the unchanged 15360 budget. There is no fifth HTTP or usage. The missing later-provider/event observation and final decision remain an actual M01 failure.

`analyze.py` reproduces all four sent bodies byte-identically with the production encoder and reconstructs the unsent fifth from original X stdout. `analysis.json` binds every source. The fifth body comprises 4054 B system message, five 619 B user objects (591 B text each), four assistant/tool pairs totaling 3322 B, array punctuation and **395 B** outside messages. Those 395 B include the 299 B tools value; excluding the entire outer structure would not resolve the 1717 B shortfall. There is no evidenced tokenizer rule authorizing such a subtraction. The 93274 B Pi payload is already reduced correctly: local metadata, usage and full publication/X refs in `details` do not enter HTTP. Keep ProviderOwner and reference/authority layers unchanged.

The smallest accepted change is ordinary external Harness text. Final prompt (270 B with its original 79-character path):

> New Step: input includes published changes. Workspace snapshot (runtime, read-only): PATH. Use it, not old paths. Continue; at most one tool. Final ends task: only when complete or truly blocked.

The explicit snapshot/domain/read-only wording was restored on root review to prevent the previous cwd ambiguity. The initial 240 B wording, source, calculations and author run are preserved under `revision-002/`. The projection's 196 B human paragraph points to the original full `history_views` immediately below; it retains current-Step, published-next-Step, older-input and not-yet-complete meaning without repeating the path. The exact goal/Surface text, event bytes, feedback, complete catalog/version refs, native messages, stdout/stderr, exit, tools and permissions remain untouched.

Counterfactual replay from the start, holding the four **observed old** usage values fixed (not predicting new-model usage):

| Step | Original body B | Final concise body B | Old prior usage + concise B |
|---|---:|---:|---:|
| 1 | 4226 | 3650 | 3650 |
| 2 | 5979 | 5082 | 5979 |
| 3 | 7714 | 6496 | 8741 |
| 4 | 9046 | 7507 | 11583 |
| 5, unsent | 10881 | 9021 | 15217 |

Five prompts save **1605 B**, explanation serialization saves **255 B**, total **1860 B**, giving 143 admission margin. `analysis-002/derived/` contains exact counterfactual bodies, expressly not transport evidence. Every other system block and non-user message remains identical.

For all six steps, prompt text contributes exactly 591n versus 270n B at step n: 3546 versus 1620 at step 6, a 1926 B saving; across calls 1–6, 12411 versus 5670 B, saving 6741. The explanation saves another 255 B per request with a catalog. This bounds the changed fixed strings only. It cannot guarantee six requests. If response 5 makes another tool call and system text is unchanged, `B6 = 9021 + encoded assistant5 + encoded tool5 + 301` (new user object plus three separators). Holding old usage 6196 leaves -158 before even counting fifth usage/new pair. Actual changed prior usage, fifth output and next system delta are unknown; historical token/byte ratios are not a safe bound. A final fifth answer needs no sixth request. Otherwise the original guard may still legitimately pause.

First HIN01–04 and PLOC01–02 author batches passed against the unchanged final projection; TF01–TF10 passed again after the final prefix correction, with real S callback and actual Pi. All source checks are unchanged. `delivery.json` indexes raw results and commands for root independent review. No Docker, proxy, model, budget, test criterion or goal changed. The limits remain 6 requests/steps, 15360 total input tokens, 15360 preflight body bytes, 2048 output tokens per request and 300 seconds; no M01 completion is claimed.
