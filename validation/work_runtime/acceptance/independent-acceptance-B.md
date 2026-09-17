# Independent acceptance — lane B (adversarial re-run)

- Verifier role: independent, did not write the code under test. All conclusions below come from
  re-reading on-disk bytes and re-deriving digests, not from the CLI's own summary.
- Date of run: 2026-09-17 (local machine clock; round ids embed `1789602xxx` epoch).
- Interpreter: `/opt/homebrew/bin/python3.12` (all runtime and checker invocations).
- Repo: `/Users/kaiqidong/Desktop/loom`
- Evidence root (created fresh by this lane):
  `validation/task_runtime/acceptance/independent-B-evidence/`
- Scratch dirs: `/tmp/tamper-B/`, `/tmp/goal-lenient/`, `/tmp/indep_verify_B.py`
- Credential handling: the CLI read `ARC_PLAN_API_KEY` from `~/.env` itself. The key value was
  never printed, echoed, or written by any command in this lane; no `--api-key-env` override and
  no secret was placed on a command line.

Overall verdict: **PASS for the required checks; 1 minor checker-strictness finding (not a
runtime failure).**

---

## 1. Fresh end-to-end real-model run (new evidence, not the implementer's)

### 1.1 Exact commands

```sh
cd /Users/kaiqidong/Desktop/loom
ROOT=validation/task_runtime/acceptance/independent-B-evidence

/opt/homebrew/bin/python3.12 -m lore_task create --root "$ROOT" --task-id acc-goal-1 --harness lore_harness/goal

/opt/homebrew/bin/python3.12 -m lore_task ingest --root "$ROOT" --task-id acc-goal-1 --foreign-id o1 \
  --kind task.objective.set \
  --payload '{"objective":"In the content directory create numbers.json with [2,3,5] and report.md whose exact content is sum=10.","acceptance":["report.md contains exactly sum=10"]}'

/usr/bin/time -p /opt/homebrew/bin/python3.12 -m lore_task run --root "$ROOT" --task-id acc-goal-1 \
  --provider ark --max-tokens 8000 --max-steps 8 --timeout 280
```

Create returned `harness.digest = sha256:2cb618fbd2c996fe43aabc97c89b0aa0960cf59815b2792d03c4ae25a33499b1`
(recorded before the Round; used as the pre-run harness digest below).

### 1.2 Raw CLI observation (Round 1)

```json
{
  "status": "committed",
  "round_id": "round-0001-1789602260",
  "steps": 3,
  "emitted": ["sys.tool.result#2", "sys.tool.result#3", "task.completed#4"],
  "revision": "sha256:8f054c56cefca533b9124820188672e0c7388e22e5bc9a09ac1f6c07f7680308",
  "provider": "openai-compat",
  "model": "glm-5.3-flash"
}
```

Process wall time (`/usr/bin/time -p`): `real 8.68s`, exit code 0.
Round-internal wall time from the ledger record: `ended - started = 1789602269 - 1789602260 = 9s`.
Observed model name **from the session log** (authoritative, not the CLI echo): the session rows
carry `reply.model = "glm-5-3-flash"` (the model alias the CLI passes); the CLI prints the request
model `glm-5.3-flash`. Token usage recorded in the ledger: 491 + 833 + 498 = 1822 total.

Session log path: `acc-goal-1/session/rounds/round-0001-1789602260.jsonl`
(3 rows, one per step).

### 1.3 On-disk artifacts (raw, unabridged where short)

`surface/content/report.md` as bytes (`od -c`): `s u m = 1 0` — exactly 6 bytes, **no trailing
newline**, sha256 `0b51e4eadd7d77b9957088b20c0ec234a759fe8d5df2a6fa5f9192b1e7d40861`.

`surface/content/numbers.json` as bytes: `[2,3,5]` (sha256 `e6e93bacd7239f258d3af1018679149d2a9a3e0bfc41a91da7e684b4666dc8ce`).

`surface/facts.jsonl` (4 facts, 1 line each):

| seq | kind | source | digest (truncated) |
|----|------|--------|--------------------|
| 1 | task.objective.set | external | sha256:8e73827d1012… |
| 2 | sys.tool.result | runtime | sha256:8393b9c1ed0e… |
| 3 | sys.tool.result | runtime | sha256:7b9e149b3492… |
| 4 | task.completed | harness | sha256:4633cd7be84c… |

The model's own tool calls, verbatim from the facts:
- step 0: `printf '[2,3,5]' > numbers.json && printf 'sum=10' > report.md` → exit 0
- step 1: `[ "$(cat report.md)" = "sum=10" ] && echo VERIFY_OK || echo VERIFY_FAIL` → `VERIFY_OK`
- step 2: `emit task.completed {evidence_refs:[report.md, numbers.json]}`

`surface/head`:

```json
{
  "facts_end": { "digest": "sha256:4633cd7be84cce5487a4335cde7d2c636098d37f8a118995ba5b2ab5f881937d", "seq": 4 },
  "layout_version": 1,
  "ledger_seq": 1,
  "revision": "sha256:8f054c56cefca533b9124820188672e0c7388e22e5bc9a09ac1f6c07f7680308",
  "round_id": "round-0001-1789602260"
}
```

`ledger/rounds.jsonl` contains exactly two rows: a `phase:"start"` marker (`trigger_seq:1`) and a
`phase:"commit"` record for `round-0001-1789602260` whose `revision` equals the head revision and
whose `facts_end` equals the last fact. `ledger/admission.jsonl` has exactly one accepted row for
`foreign_id:"o1"`.

### 1.4 Independent verification (from bytes, not narration)

A standalone script (`/tmp/indep_verify_B.py`, does not import the runtime) recomputed everything:

| Check | Result |
|-------|--------|
| facts file ends with `\n` (not torn) | PASS |
| every fact `digest == sha256(canonical(body-without-digest))` | PASS |
| `seq` is 1..N contiguous with no gap | PASS |
| `head.facts_end.seq/digest` == last fact's seq/digest | PASS |
| `report.md` bytes are **exactly** `b"sum=10"` | PASS |
| `numbers.json` parses to `[2, 3, 5]` | PASS |
| harness tree digest == `task.json harness.digest` | PASS |
| harness tree digest == create-time recorded `2cb618fb…` (unchanged by the Round) | PASS |
| no `__pycache__` written under `harness/` | PASS |
| exactly one committed Round; one start; last ledger row is the commit (no uncommitted tail) | PASS |
| round `revision` == recomputed `tree_digest(surface/content)` | PASS |
| `head.round_id` and `head.ledger_seq` match the commit record | PASS |
| referenced session log exists | PASS |
| model name observed from session log | `glm-5-3-flash` |

Shipped checker cross-check: `verify_goal_task.py acc-goal-1` → all 13 checks PASS, `"ok": true`,
exit 0.

**Conclusion for step 1: PASS.** The task was genuinely completed by the real model, the artifacts
are internally consistent, the harness area is byte-identical to creation, and the ledger has one
committed Round.

---

## 2. Falsification of the checkers (one-byte tamper)

Method: copy two *currently passing* evidence task dirs from the implementer's own evidence tree to
`/tmp/tamper-B/`, confirm the baseline passes, then flip **exactly one byte** (verified: Hamming
distance 1, same length) in one frozen unit file / one verified corpus source file, and re-run the
shipped checker on the copy. Product files were never touched; only the `/tmp` copies.

Baselines (before tamper): design `ok:true` exit 0, research `ok:true` exit 0.

### 2(a) `verify_design_task.py` — frozen unit file

- Copy: `/tmp/tamper-B/design/root/design-005`
- Target: `surface/content/units/u1.md`, referenced by the `design.unit.frozen` fact
  (`file: units/u1.md`, `file_digest: sha256:34d61a60a8ff…`).
- Tamper: byte offset 0, `#` → `@`. File digest `34d61a60a8ff…` → `28e039438bad…`.

Result — **FAILS as required** (exit 1, `"ok": false`):

```
FAIL digest_matches_bytes:u1  :: sha256:28e039438badac7d1299… != sha256:34d61a60a8ff98fb7b40…
```

### 2(b) `verify_research_task.py` — verified corpus/source file

- Copy: `/tmp/tamper-B/research/root/research-1`
- Target: `surface/content/a-notes.md`, referenced by two `research.source.verified` facts
  (`source_ref: a-notes.md`, `digest: sha256:5e21582c4681…`).
- Tamper: byte offset 0, `#` → `@`. File digest `5e21582c4681…` → `c9db565093a3…`.

Result — **FAILS as required** (exit 1, `"ok": false`):

```
FAIL verified_digest_real:a-notes.md  :: sha256:c9db565093a3f268d23b… != sha256:5e21582c468168e888ea…
```

Both byte-level tampering attempts were caught. No tamper escaped detection in these two checkers.

### 2(c) Extra adversarial probe — a tamper that is **NOT** caught (finding)

`verify_goal_task.py` checks `report_content` with `.strip()`:

```python
expect = ("sum=%s" % args.expect_sum)
check("report_content", report.is_file() and report.read_text().strip() == expect, ...)
```

I took the passing `acc-goal-1` dir, wrote `report.md` = `b"sum=10\n\n\n"` (not the exact content the
ingested objective demanded: *"report.md whose exact content is sum=10"*), then restored the task's
internal self-consistency by recomputing `head.revision` and the round record's `revision`. The
shipped checker then reports:

```
PASS report_content
PASS round_revision_matches_content
{"task": "/tmp/goal-lenient", ..., "ok": true}
SHIPPED_EXIT=0
```

while a strict byte comparison shows `report bytes: b'sum=10\n\n\n'  exactly sum=10: False`.

**Finding (minor, strictness only):** `verify_goal_task.py`'s `report_content` is whitespace-
insensitive, so it does not enforce a byte-exact acceptance criterion of the form "exactly
`sum=10`". The padding must still be whitespace and the surrounding revision digests must be
consistent, so this is not a route to a wrong answer (`sum=11` fails), but a checker advertised as
an independent byte-level check should compare bytes, not stripped text. This is the one place where
a tamper was not caught by the check that appears to cover it.

---

## 3. Zero-residency check (ask-user)

### 3.1 Exact commands

```sh
/opt/homebrew/bin/python3.12 -m lore_task create --root "$ROOT" --task-id acc-ask-1 --harness lore_harness/ask_user

/opt/homebrew/bin/python3.12 -m lore_task ingest --root "$ROOT" --task-id acc-ask-1 --foreign-id a1 \
  --kind task.objective.set \
  --payload '{"objective":"Create answer.md containing the greeting the user chooses. Do NOT guess: you must ask the user which greeting to use and stop without writing any file until an answer arrives.","acceptance":["answer.md contains the greeting the user chose"]}'

# Round 1 (real model)
/usr/bin/time -p /opt/homebrew/bin/python3.12 -m lore_task run --root "$ROOT" --task-id acc-ask-1 \
  --provider ark --max-tokens 8000 --max-steps 8 --timeout 280

# Round 2 and 3 (no answer exists yet)
/opt/homebrew/bin/python3.12 -m lore_task run --root "$ROOT" --task-id acc-ask-1 --provider ark --max-tokens 8000 --max-steps 8 --timeout 280
/opt/homebrew/bin/python3.12 -m lore_task run --root "$ROOT" --task-id acc-ask-1 --provider ark --max-tokens 8000 --max-steps 8 --timeout 280
```

### 3.2 Raw observations

Round 1 (real model): `real 1.55s`, exit 0.

```json
{"status":"committed","round_id":"round-0001-1789602292","steps":1,
 "emitted":["ask.requested#2"],
 "revision":"sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
 "provider":"openai-compat","model":"glm-5.3-flash"}
```

The model asked instead of guessing (fact 2, source `harness`):

```json
{"kind":"ask.requested","payload":{"ask_id":"q1","options":["Hello, World!","Hi there!","Greetings!"],
 "question":"Which greeting should be written to answer.md?"}}
```

No answer was ingested. Runs 2 and 3 both returned:

```json
{"status":"no_trigger","pending":1,"trigger_watermark":1,"provider":"openai-compat","model":"glm-5.3-flash"}
```

exit code 0, wall time ≈ 0.05s — i.e. the trigger gate refused before any model call.

Supporting on-disk facts:
- `surface/content` is empty after Round 1 (`content_files: []`), so nothing was fabricated while waiting.
- `session/rounds/` contains exactly **one** file (`round-0001-1789602292.jsonl`). The two
  `no_trigger` runs appended no session row → no model round was opened.
- `ledger/rounds.jsonl` has exactly one start + one commit; the `no_trigger` runs wrote no ledger row.
- `acc-ask-1` revision equals the empty-tree digest
  `sha256:e3b0c44298fc…b855` (= `sha256("")`, the tree_digest of an empty dir).

### 3.3 Leftover-process check

Immediately after the three runs:

```
$ ps -Ao pid,ppid,etime,command | grep -E 'python3\.12 -m lore_task|lore_task/' | grep -v grep
(none)
$ ps -Ao pid,command | grep -F "validation/task_runtime/acceptance/independent-B-evidence" | grep -v grep
(none)
$ ps -Ao pid,ppid,etime,command | grep -E 'python3\.12' | grep -v grep
(none)
```

`lsof +D` on the task dir returned nothing. Source inspection of the runtime shows no daemon/fork
surface: no `os.fork`, `multiprocessing`, or long-lived `threading`; `subprocess` is used only for
one-shot tool shells with a timeout, and the single `threading.Timer` in
`lore_provider/transport.py` is a per-request timeout marked `daemon = True`. There is no listening
socket. **No lingering process can be attributed to the runtime.**

**Conclusion for step 3: PASS.** Waiting is data-only: with the question open and unanswered, `run`
returns `no_trigger` without a model call, the process exits, and nothing remains resident.

---

## 4. Reproducibility / model-output variability

I ran a second independent goal task (`acc-goal-2`) with the **same** ingest payload to sample
model variability directly:

| | acc-goal-1 | acc-goal-2 |
|---|---|---|
| steps | 3 | 2 |
| emitted facts | `sys.tool.result#2`, `sys.tool.result#3`, `task.completed#4` | `sys.tool.result#2`, `task.completed#3` |
| facts count | 4 | 3 |
| content tree revision | `sha256:8f054c56cefc…` | `sha256:8f054c56cefc…` (identical) |
| checker result | ok:true | ok:true, exit 0 |

`glm-5.3-flash` is **not** deterministic at the trajectory level: the two samples took different
step counts and produced different fact streams (sample 2 skipped the model's own re-verification
shell). Variability affected *how* the Round was executed, **not** the produced deliverable: both
samples wrote byte-identical `report.md`/`numbers.json` (same content-tree revision) and both
evidence sets are internally valid and independently verifiable. So the evidence produced by this
lane is valid; any downstream reader must key on artifacts/digests (as done here), not on step
counts or the shape of the fact stream, which are model-dependent.

---

## 5. PASS/FAIL summary

| # | Requirement | Verdict |
|---|-------------|---------|
| 1 | Fresh real-model goal Round (new task, new root, `--provider ark`) | PASS |
| 1 | Facts well-formed, self-consistent digests, contiguous seq | PASS |
| 1 | `head.facts_end` == last fact digest | PASS |
| 1 | `surface/content/report.md` exact bytes `sum=10` (and `numbers.json` == `[2,3,5]`) | PASS |
| 1 | Harness tree digest unchanged vs create-time | PASS |
| 1 | Ledger has a committed Round (and a start marker, no uncommitted tail) | PASS |
| 1 | Model name recorded from session log | PASS (`glm-5-3-flash`) |
| 2a | 1-byte tamper in a frozen unit file is caught by `verify_design_task.py` | PASS (checker FAILS) |
| 2b | 1-byte tamper in a verified corpus source is caught by `verify_research_task.py` | PASS (checker FAILS) |
| 2c | Goal checker rejects non-byte-exact `report.md` | **FAIL (finding, §2c)** |
| 3 | Ask-user asks instead of guessing; unwritten while waiting | PASS |
| 3 | Subsequent `run` with no answer returns `no_trigger` and exits | PASS |
| 3 | No daemon / lingering process attributable to the runtime | PASS (none found) |
| 4 | Reproducibility characterized | PASS (trajectory varies; artifacts stable) |

No runtime counterexample was found. The only counterexample is against a checker's *strictness*
(§2c): `verify_goal_task.py` would accept `report.md = "sum=10\n\n\n"` as satisfying an acceptance
criterion that says "exactly `sum=10`", provided the surrounding revision digests are made
self-consistent. → **See §7: this finding was fixed (byte-exact comparison in the three checkers)
and independently re-verified; the fix holds and clean evidence stays green.**

## 6. Limitations / scope of this verification

- Same machine, same workspace, and this lane was started by the implementing session. There is no
  OS-level isolation between the implementer and this verifier; the evidence dir is inside the
  repo the implementer can write. This is *role* separation, not *security* separation (AGENTS.md
  acknowledges the same limitation).
- The run used the real `ark` provider, but the model alias (`glm-5-3-flash`) and endpoint were
  taken from the CLI defaults; provider-side routing/version beyond the returned `model` field was
  not inspected.
- Only one provider and one model were exercised; no retry/error-path run was attempted.
- The step-2 tamper sweep covers exactly the two checkers and two file classes requested. It does
  not prove the checkers are sound in general (e.g. collusion between the fact stream and the
  content, for which no digest binds facts to content besides the round `revision`).
- I did not modify any product file. All tampering happened on `/tmp` copies.
- Fresh evidence from this lane lives under
  `validation/task_runtime/acceptance/independent-B-evidence/` (`acc-goal-1`, `acc-goal-2`,
  `acc-ask-1`).

---

## 7. Re-verification after the §2c fix (checker-only change)

The implementer reported fixing only three checkers so that the deliverable comparison is
byte-exact: `verify_goal_task.py`, `verify_plan_task.py`, `verify_delegation_tasks.py`. I verified
the claim from the files, not the narration. Confirmed in source:

- `verify_goal_task.py:54-56` — `expect = ("sum=%s" % args.expect_sum).encode("utf-8")`;
  `check("report_content_bytes_exact", report.is_file() and report.read_bytes() == expect, ...)`.
- `verify_plan_task.py:53` — `check("stage2_deliverable", report.is_file() and report.read_bytes() == b"sum=10", ...)`.
- `verify_delegation_tasks.py:42` — `check("child_deliverable_real", report.is_file() and report.read_bytes() == b"sum=10", ...)`.

The runtime (`lore_task/`) was not part of the change; `report.md` is still written byte-exact by
the model (already established in §1.3).

### 7.1 Step 1 — the padded-report tamper now FAILS

Exact commands (copy my fresh passing evidence, pad exactly as before, restore internal
self-consistency so only the byte check can catch it):

```sh
rm -rf /tmp/reverify-fix && mkdir -p /tmp/reverify-fix
cp -R validation/task_runtime/acceptance/independent-B-evidence/acc-goal-1 /tmp/reverify-fix/goal
# append \n\n\n to surface/content/report.md, then recompute head.revision and the commit
# record revision to tree_digest(surface/content)  (python3, /tmp only)
/opt/homebrew/bin/python3.12 validation/task_runtime/verify_goal_task.py /tmp/reverify-fix/goal
```

Raw result — **FAILS as required**, exit 1, `"ok": false`:

```
PASS numbers_content
FAIL report_content_bytes_exact  :: b'sum=10\n\n\n'
PASS head_points_at_last_fact
PASS one_round_record
PASS round_revision_matches_content
...
{"task": "/tmp/reverify-fix/goal", "facts": 4, "kinds": [...], "ok": false}
FIXED_EXIT=1
```

The tamper was `b"sum=10"` → `b"sum=10\n\n\n"` with the revision digests made self-consistent
(`sha256:63f23ee97c5b…`), i.e. the identical attack that previously passed. The fix holds.

**Byte-exactness matrix** on the fixed `verify_goal_task.py` (each row a fresh copy of `acc-goal-1`
with only `report.md` rewritten):

| `report.md` bytes | exit | `report_content_bytes_exact` |
|---|---|---|
| `b"sum=10"` | 0 | PASS |
| `b"sum=10\n"` | 1 | FAIL |
| `b"sum=10 "` | 1 | FAIL |
| `b" sum=10"` | 1 | FAIL |
| `b"sum=10\r\n"` | 1 | FAIL |
| `b"sum=11"` | 1 | FAIL |

Only the exact bytes pass; every whitespace variant is now rejected.

### 7.2 Step 2 — clean recorded evidence stays green

Untampered recorded evidence, run directly (no copies):

```sh
cd /Users/kaiqidong/Desktop/loom/validation/task_runtime
/opt/homebrew/bin/python3.12 verify_goal_task.py evidence/ark-goal-003/root/goal-003
/opt/homebrew/bin/python3.12 verify_plan_task.py evidence/ark-plan-001/root/plan-001
/opt/homebrew/bin/python3.12 verify_delegation_tasks.py evidence/ark-delegation-002/root parent-1 child-1
```

| Checker / evidence | Result |
|---|---|
| `verify_goal_task.py` `ark-goal-003/root/goal-003` | all 13 PASS, `"ok": true`, exit 0 |
| `verify_plan_task.py` `ark-plan-001/root/plan-001` | all 12 PASS, `"ok": true`, exit 0 |
| `verify_delegation_tasks.py` `ark-delegation-002/root parent-1 child-1` | all 16 PASS, `"ok": true`, exit 0 |

**Positive controls** (confirm the fix in plan/delegation is real and not just inert on clean data).
Fresh `/tmp` copies, then a single-byte append (`printf '\n' >>`, verified 6 → 7 bytes by `od -c`);
neither plan nor delegation re-derives the content revision, so no self-consistency step was needed
and only the byte comparison could catch it:

```sh
cp -R evidence/ark-plan-001/root/plan-001 /tmp/reverify-fix/pc/plan
cp -R evidence/ark-delegation-002/root /tmp/reverify-fix/pc/deleg
printf '\n' >> /tmp/reverify-fix/pc/plan/surface/content/report.md
printf '\n' >> /tmp/reverify-fix/pc/deleg/child-1/surface/content/report.md
```

```
FAIL stage2_deliverable     :: b'sum=10\n'   (plan, exit 1)
FAIL child_deliverable_real :: b'sum=10\n'   (delegation, exit 1)
```

Both previously-passing tasks now fail on a padded deliverable, so the byte comparison is live in
all three checkers. (Note: an earlier draft of this control appended the whole string by mistake
and I re-ran it with a single `\n`; the quoted output above is from the corrected run.)

### 7.3 Step 3 — remaining normalizing comparisons

Repo-wide sweep (`grep -rnE '\.strip\(\) *(==|!=|in )' --include='*.py'`, excluding `third_party/`
and `.git/`). Inside the six `validation/task_runtime/verify_*.py` checkers there is **no remaining
strip-based content comparison**. The only remaining non-byte comparisons are:

- `verify_goal_task.py:58` `numbers_content` and `verify_plan_task.py:51` `stage1_deliverable`:
  `json.loads(numbers.read_text()) == [2, 3, 5]`. This is semantic JSON equality, not text
  normalization. The criterion is "`numbers.json` with `[2,3,5]`" (a JSON value), so `[2, 3, 5]`
  or `[2,3,5]\n` passing is correct, and any value change (`[3,2,5]`, `[2,3,5,5]`) still fails.
  **Not exploitable** to a wrong value.
- `verify_research_task.py:30,40,90` `independent_recall` uses `.lower()` to reproduce the runtime's
  documented *case-insensitive literal* recall. The check re-derives the same semantic, so the
  normalization is the criterion itself. **Not a laxness finding.**
- `tree_digest()` uses `.replace(os.sep, "/")` on paths (cross-platform path normalization), not on
  evidence content.

**Residual finding (lower severity, outside the three fixed files):** three shipped offline
task-runtime case scripts still compare deliverable *text* through `.strip()`:

- `validation/task_runtime/offline_goal_round.py:46` —
  `check("content_written", report.is_file() and report.read_text().strip() == "sum=10")`
- `validation/task_runtime/offline_delegation.py:69` —
  `check("child_deliverable", (child / "surface" / "content" / "report.md").read_text().strip() == "sum=10")`
- `validation/task_runtime/offline_ask_user.py:59` —
  `check("answer_used", answer.is_file() and answer.read_text().strip() == "bonjour")`

Exploitability: **low**. These are faux-provider self-test drivers, and the deliverable is written
by a hard-coded `printf ... > report.md` script inside the test file, so no model can inject
padding; the risk is only if these scripts are ever reused as bare acceptance checks over
externally produced content. They are the same laxness class as the §2c finding and were not part
of the three-file fix. Other `.strip()` hits elsewhere (`validation/system/runtime_observer.py:267`
substring membership, `validation/components/s/context-selftest.py:25`,
`scripts/runtime-env/container-load-probe.py:93`, `validation/components/s/probe-container.py:43`)
are in other subsystems (version strings, substring probes) and are not byte-exactness criteria for
a task deliverable.

### 7.4 Re-verification verdict

| Item | Verdict |
|---|---|
| `verify_goal_task.py` now byte-exact; padded tamper caught | **PASS** (`report_content_bytes_exact`, exit 1) |
| `verify_plan_task.py` now byte-exact; padded tamper caught | **PASS** (`stage2_deliverable`, exit 1) |
| `verify_delegation_tasks.py` now byte-exact; padded tamper caught | **PASS** (`child_deliverable_real`, exit 1) |
| Clean recorded evidence still green on all three | **PASS** (goal/plan/delegation all `ok:true`) |
| Other task-runtime checkers with strip-based exactness claim | **none** |
| Residual lax comparisons in shipped offline drivers | 3 files (low exploitability, §7.3) |

**Residual doubts.** (a) The fix was verified only for the `report.md`/deliverable byte comparison
class; I did not exhaustively prove there is no other semantic gap in the checkers (e.g. nothing
binds the fact stream to the content bytes except the round `revision`, which a tamperer can
recompute, as §2c/§7.1 demonstrate). (b) The offline drivers in §7.3 keep the lax pattern; if the
intent was "no checker normalizes a claimed-exact deliverable", the sweep should extend to those
three lines. (c) Same-machine/role-separation limitation from §6 still applies to this
re-verification.
