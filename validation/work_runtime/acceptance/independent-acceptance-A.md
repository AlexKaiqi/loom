# Independent acceptance — lane A (locked-contract conformance & raw evidence)

- Verifier role: independent agent; **did not write** `lore_task/`, `lore_harness/`, the
  offline cases, the checkers, or the recorded evidence. Every verdict below comes from
  re-reading bytes, re-deriving digests, running the shipped cases/checkers, and running my
  own adversarial probes. The implementer's process record
  (`validation/task_runtime/FINDINGS-2026-09-16.md`) was treated as a **claim**, not evidence.
- Date: 2026-09-17 (local clock; round ids embed `1789602xxx` epoch).
- Interpreter: `/opt/homebrew/bin/python3.12` for every runtime / checker invocation.
- Repo under test: `/Users/kaiqidong/Desktop/loom` (working tree; `lore_task/` and
  `lore_harness/` are untracked, so there is no commit hash pinning them — see Limitations).
- Locked contracts used: `design/g3/task-runtime-contract.md` (M1 runtime↔harness interface)
  and `design/g3/task-directory-landing.md` (§4–§11).
- Scratch: all my scratch is under `/tmp/ia-verify/` and `/tmp/ia-verify/adv/`. No product or
  evidence file was modified; the only file I wrote inside the repo is this report.

## Method

1. Read the two locked contracts in full, then read all of `lore_task/` (`layout.py`,
   `facts.py`, `ledger.py`, `manifest.py`, `round.py`, `cli.py`, `provider.py`) and the
   harness hooks referenced by the contract.
2. Ran every `validation/task_runtime/offline_*.py` **twice** (fresh `/tmp` each time) and
   diffed the PASS/FAIL check-lines.
3. Ran all six named checkers against the recorded evidence, plus known-failing evidence to
   confirm the checkers discriminate. Hand-recomputed frozen/source digests with
   `shasum -a 256`.
4. Built my own task root in `/tmp` and executed adversarial probes (a)–(e) plus extra
   falsification attempts.
5. Scanned all 1753 non-`.git` repo files for the live credential value (in-process compare;
   the value is never printed).
6. Inventoried the 9 scenarios and validated every harness `manifest.json` through the real
   loader.

---

## 1. Contract conformance by code reading (raw evidence)

Each row: claim from the locked contract → verdict → what I actually observed.

| # | Claim (source) | Verdict | Raw evidence |
|---|---|---|---|
| 1 | **Base tree** = `task.json`, `harness/manifest.json`, `surface/{content,head,facts.jsonl}`, `ledger/` (contract §Runtime; landing §4.2) | **PASS** | `ls -A /tmp/ia-verify/adv/root/sender-a` → `harness ledger surface task.json`. `layout.create_task` (`layout.py:106-140`) creates exactly those; `session/`/`derived/` only appear on demand. `paths()` (`layout.py:88-103`) points `facts` at `surface/facts.jsonl` and `head` at `surface/head`. |
| 2 | **Facts single writer** — only runtime appends `facts.jsonl` (append + fsync) (contract §Runtime) | **PASS** | `append_fact` (`facts.py:57-74`) is the only appender (`open(p,"ab")` + `os.fsync`). Grep of `lore_task/*.py` shows every append goes through `facts_mod.append_fact`; the only other writer is `round.recover`'s atomic truncate (`round.py:198`), still runtime. No harness module writes facts — harnesses only return `{kind,payload}` from `emit`/`settle`, which the runtime writes. |
| 3 | **`head` is the unique commit point** (atomic replace; holds `revision`+`facts_end`+`round_id`+`ledger_seq`) (contract §Runtime) | **PASS (with §4 finding)** | `write_json(p["head"], …)` occurs only in `layout.py:134` (create) and `round.py:468` (commit); `atomic_write` = tmp + `fsync` + `os.replace` + dir `fsync` (`layout.py:24-44`). Evidence `ark-plan-001/root/plan-001/surface/head` = `{"facts_end":{"seq":6,…},"revision":"sha256:8f054c…","round_id":"round-0002-…","ledger_seq":2}`, matching the last commit record. **Caveat:** see §4.2 for the crash window between the ledger commit row and the head write. |
| 4 | **Trigger watermark separate from commit watermark**: `rounds.jsonl.trigger_seq` governs "already evaluated", `head.facts_end` is the commit watermark (contract §Runtime) | **PASS** | `round.py:296-300`: `trigger_watermark = max(trigger_seq over committed round records)`; `new = facts with seq > watermark`. Evidence `ark-plan-001`: R1 `trigger_seq=1`, `facts_end.seq=3`; R2 `trigger_seq=3`, `facts_end.seq=6` → R2 saw R1's own emitted facts (seq 2–3). Same in `ark-research-009`: R1 `trigger=1→facts_end=5`, R2 `trigger=5→facts_end=10`, R3 `trigger=10→facts_end=19`. |
| 5 | **`final` is only a proposal**; ending is decided by `rounds.should_continue(state)` (contract §Harness) | **PASS** | `round.py:366-375`: on `final` it sets `state["final"]`, calls `_should_continue`, and if the harness says continue it stores `rejected_final` and loops. Direct probe (archive harness, whose `should_continue` only accepts `archive.performed`): two `final` replies with `--max-steps 2` → `{"status":"committed","steps":2,"emitted":[]}` and ledger `steps=['final','final']`. The proposals did **not** end the round. |
| 6 | **Conditional `emit`**: `base_rev` must equal the round-start committed revision, else `sys.declaration.rejected` and no declaration (contract §Harness) | **PASS** | `round.py:414-436`; `state["base_rev"] = head["revision"]` at round start (`round.py:308`). Probe (c): stale `base_rev` → facts = `['design.objective.set','sys.declaration.rejected']`, **no** `design.unit.accepted` fact; rejected payload `{"base_rev":"sha256:000…","committed_rev":"sha256:e3b0…","reason":"stale base revision"}`. Control with the correct revision → `design.unit.accepted` appended. |
| 7 | **`logic.guard` refusal path**: returns reason → `sys.action.rejected`, no side effect (contract §Harness) | **PASS** | `round.py:342-361` calls `guard(state=state, action=action)` before executing; a truthy reason appends `sys.action.rejected` and `continue`s. Real evidence `ark-research-009` fact #4: `{"action":"shell","reason":"You have read enough this Round…"}`. Guard requires the kind to be declared or raises `ManifestError` (`round.py:348-350`); the research manifest declares it. |
| 8 | **`recover` quarantine**: interrupted round → `recovery_needed`; recover quarantines the uncommitted tail under `session/crashed/`, truncates facts, records a repair (contract §崩溃与恢复) | **PARTIAL** | Probe (d) + extra run: crash leaves `{"phase":"start",…,"trigger_seq":1}`; next `run` → `{"status":"recovery_needed","uncommitted":1,"last_committed_seq":1}`; `recover` → `{"status":"recovered","discarded":["sys.tool.result#2"],"saved":"session/crashed/facts-after-1-…jsonl"}`, facts truncated to seq 1, `ledger/repairs.jsonl` written, `abort` row appended, pre-crash `content/partial.txt` preserved, and a later round commits cleanly. **But the quarantined file is not the original bytes** — see §4.1. |
| 9 | **Workspace target routing refusal**: unregistered/unknown target → exit 126, no fallback to host (contract §Harness) | **PASS** | `_resolve_target` (`round.py:100-114`) returns `None`; `round.py:376-391` records `{"exit":126,"cwd":null,"stderr":"unauthorized or unknown shell target: workspace:nope"}` and never runs the script. Probe (b): side-effect file `/tmp/ia-verify/adv/SIDE_EFFECT_B` absent. Control: a registered `--workspace` target runs with `cwd=/tmp/ia-verify/adv/ws1`, `exit=0`, and the file appears. |
| 10 | **`deliver` requires `wants` + `grants` on both sides** (contract §Harness; landing §4.6/§9-3) | **PASS for the mechanism (FAIL for copy rule — §4.3)** | `round.py:256-277` checks receiver `wants` **and** sender `grants` on stable task ids. Probe (a): no relations → `{"delivered":false,"reason":"missing wants"}` + `admission` row `decision:"rejected"`. Probe (a2): wants only → `"missing grants"`. Probe (a3): adds grants, kind `user.message` (which goal's admission accepts) → `{"delivered":true,"decision":"accepted"}` and the fact lands. |
| 11 | **`recall` determinism and boundedness** (FINDINGS claims literal, case-insensitive, bounded) | **PASS** | `_recall` (`round.py:117-148`) sorts paths, skips binaries, returns at `limit`. Repeated runs on `ark-research-009/…/content`: `("cache",5)→5`, `("cache",100)→7`, `("CACHE",100)→7`, `("",100)→0`, `("zzz",100)→0`; `deterministic=True` and `bounded=True` for all. `recall` requires a declared `sys.recall.result` (`round.py:399`). |

### 1b. Other contract clauses I checked

| Claim | Verdict | Evidence |
|---|---|---|
| **Registration strict** (landing §4.5 R2): refs exist, `sys.*` only runtime, producers valid, triggers reference declared kinds, schema checked | **PASS** | `manifest.load` (`manifest.py:110-167`). Six malformed variants all refused loudly: `sys.evil` claimed by `harness` → `ManifestError: reserved prefix must not be claimed`; `acme.x` by `runtime` → `runtime-produced kind must use reserved prefix`; undeclared trigger kind; role entry missing `id`; `schema:"lore-harness/v2"`; producer `"wizard"`. A role ref that does not exist → `FileNotFoundError: missing declared ref`. CLI `ingest` on the bad harness exits 1 with the traceback. |
| **Declared role `digest` is compared to content** (landing §4.5 R2) | **NOT IMPLEMENTED (disclosed gap)** | A manifest declaring `roles.logic[0].digest = sha256:dede…` for a file whose real digest differs **loads fine**. `manifest.load` calls `ref_digest(...)` only for existence; it never compares. This matches the M1 contract's own disclosure (`task-runtime-contract.md:55`), so it is not a hidden M1 violation, but it is a deviation from landing R2. |
| **Harness read-only**: no bytecode into `harness/`; digest recomputed start+end, change = loud failure | **PASS** | `manifest._load` sets `sys.dont_write_bytecode` (`manifest.py:84-89`); `_assert_harness_readonly` (`round.py:92-97`) called at `run_round:287` and `:456`. Probe: a provider that rewrites `harness/logic/main.py` mid-round → `RuntimeError: harness area changed during the Round: sha256:2cb618fb… -> sha256:0e9bfbff…`. Checkers also assert no `__pycache__` under `harness/`. |
| **Unknown/higher `layout_version` is refused loudly** (landing §10) | **FAIL** | Setting `task.json.layout_version = 99` then running a round → `{"status":"committed",…}`; `status()` reports `layout_version: 99`. No version gate exists in `run_round`/`ingest`/`status`. |
| **Torn trailing line is truncated and explicitly traced** (landing §6) | **FAIL — data-loss counterexample** | See §4.4. `facts.torn_tail()` exists but is **never called** (`grep -rn torn_tail lore_task/` → only the definition). |

---

## 2. Offline suite re-run (`offline_*.py`)

Commands (run from repo root, fresh `/tmp` per case, twice):

```
for f in validation/task_runtime/offline_*.py; do /opt/homebrew/bin/python3.12 "$f"; done   # run 1
for f in validation/task_runtime/offline_*.py; do /opt/homebrew/bin/python3.12 "$f"; done   # run 2
```

| Case | run 1 | run 2 | check-lines identical |
|---|---|---|---|
| offline_archive_round.py | 14 PASS / 0 FAIL, rc 0 | 14 / 0, rc 0 | yes |
| offline_ask_user.py | 13 / 0 | 13 / 0 | yes |
| offline_coding_round.py | 15 / 0 | 15 / 0 | yes |
| offline_crash_recovery.py | 11 / 0 | 11 / 0 | yes |
| offline_delegation.py | 14 / 0 | 14 / 0 | yes |
| offline_goal_round.py | 9 / 0 | 9 / 0 | yes |
| offline_monitoring_round.py | 9 / 0 | 9 / 0 | yes |
| offline_plan_rounds.py | 11 / 0 | 11 / 0 | yes |
| offline_research.py | 20 / 0 | 20 / 0 | yes |
| offline_system_design.py | 19 / 0 | 19 / 0 | yes |
| **TOTAL** | **135 PASS / 0 FAIL** | **135 PASS / 0 FAIL** | **all identical** |

- **Deterministic**: the full PASS/FAIL check-line sets are byte-identical between run 1 and
  run 2 for all 10 cases (`diff` clean). No `SKIP`/`skip`/`xfail` markers anywhere.
- **Documentation discrepancy**: `FINDINGS-2026-09-16.md:189` claims *"132 断言 / 10 个用例，0
  失败"*. The real count is **135**; the record's own per-case numbers also sum to 134, and it
  states `offline_system_design.py 18/18` (lines 135, 158) while the case actually emits
  **19** PASS lines. So the process record undercounts by 3 and is internally inconsistent.
  This is a claim/record defect, not a product failure.

---

## 3. Checkers on recorded evidence

Exact task dirs under `validation/task_runtime/evidence/` and results (all run from
`validation/task_runtime/`):

| Checker | Task dir | Result |
|---|---|---|
| `verify_goal_task.py` | `ark-goal-003/root/goal-003` | **13/13 PASS**, `"ok": true`, rc 0 |
| `verify_plan_task.py` | `ark-plan-001/root/plan-001` | **12/12 PASS**, `ok: true`, rc 0 |
| `verify_coding_task.py` | `ark-coding-001/root/code-001` | **14/14 PASS**, `ok: true`, rc 0 (includes an independent re-run of the workspace test) |
| `verify_design_task.py` | `ark-design-005/root/design-005` | **14/14 PASS**, `ok: true`, rc 0 |
| `verify_delegation_tasks.py` | `ark-delegation-002/root parent-1 child-1` | **16/16 PASS**, `ok: true`, rc 0 |
| `verify_research_task.py` | `ark-research-009/root/research-1` | **17/17 PASS**, `ok: true`, rc 0 |

**Falsifiability (the checkers reject when they should)** — the same binaries on known-bad evidence:

- `verify_goal_task.py ark-goal-001/root/goal-001` → `FAIL single_completion` (no `task.completed`), rc 1. Matches FINDINGS.
- `verify_goal_task.py ark-goal-002/root/goal-002` → `FAIL single_completion` (6× `task.completed`). Matches FINDINGS.
- `verify_research_task.py ark-research-005/root/research-1` → `FAIL saturation_before_completion`, `FAIL completed_once`, `FAIL completed_is_last`. Matches FINDINGS.
- `verify_design_task.py ark-design-002/root/design-002` → 6 FAIL lines (interrupted/recovered task).

**Independence**: `grep -ln 'lore_task' validation/task_runtime/verify_*.py` → **NONE** import the
runtime; they re-derive `tree_digest`, fact digests and head linkage from bytes.

**Hand-recomputed digest** (`shasum -a 256`, compared to the fact payload):

| Artifact | Recorded in fact | `shasum -a 256` | Match |
|---|---|---|---|
| `ark-design-005/…/units/u1.md` | `design.unit.frozen.file_digest = sha256:34d61a60…1297` | `34d61a60…1297` | ✔ |
| `ark-design-005/…/units/u2.md` | `sha256:433c9f33…c89a` | `433c9f33…c89a` | ✔ |
| `ark-research-009/…/a-notes.md` | `research.source.verified.digest = sha256:5e21582c…3f24` | `5e21582c…3f24` | ✔ |
| `ark-research-009/…/b-design.md` | `sha256:ef159855…0f22` | `ef159855…0f22` | ✔ |

---

## 4. Adversarial probes (my own temp task root)

All probes ran against tasks created with `python3.12 -m lore_task create` under
`/tmp/ia-verify/adv/`.

### 4.1 (d) Interrupted Round → `recovery_needed` → `recover` — quarantine works, **original bytes do not**

Commands: a `CrashProvider` returns one `shell` action then raises mid-Round; then `run` again;
then `recover`.

Raw result: `recovery_needed` on the second run, `recovered` from `recover`, facts truncated to
seq 1, `session/crashed/facts-after-1-<epoch>.jsonl` written, `ledger/repairs.jsonl` written,
`phase:"abort"` row appended, `content/partial.txt` preserved, later round commits cleanly.

**Counterexample (byte preservation):** the contract (`task-runtime-contract.md:39`,
FINDINGS:89) says the tail's **原字节 / original bytes** are saved. The implementation parses
and **re-serializes** (`round.py:195-196`, `json.dumps(f, sort_keys=True)` with default
separators), while facts are written by `_canonical` with `separators=(",",":")`. Observed:

```
original uncommitted line bytes : b'{"digest":"sha256:2571…","id":"sys.tool.result#2",…}'
quarantined file bytes          : b'{"digest": "sha256:2571…", "id": "sys.tool.result#2", …}'
BYTE-IDENTICAL                  : False
JSON-EQUAL (parse)              : True
```

The data survives (JSON-equal) but the "original bytes" requirement is **not met**. The shipped
`offline_crash_recovery.py` check `quarantine_has_original_bytes` only asserts the saved row
parses to a `sys.tool.result`, so it does not test byte identity. → **FAIL (data preserved,
byte-fidelity requirement not met).**

### 4.2 Extra: crash *after* ledger commit, *before* head advance

FINDINGS:93 says this window is "exposed by the head/ledger mismatch, no automatic check yet".
I simulated the exact window (patched `round.write_json` to raise only for `head`):

```
rounds.jsonl last row : {"phase":"commit","trigger_seq":1,"facts_end":{"seq":1,…},"emitted":[]}
head                  : {"facts_end":{"seq":0,…},"round_id":null,"ledger_seq":0}
next run              : {"status":"no_trigger","pending":0,"trigger_watermark":1}
recover()             : {"status":"recovered","committed_seq":0,"kept_seq":0,
                         "discarded":["task.objective.set#1"]}
facts after recover   : b''   (empty)
rounds.jsonl          : still contains the phase:commit row (trigger_seq=1, facts_end.seq=1)
```

So in this window the documented recovery command **deletes a fact that the ledger already
recorded as committed**, leaves the commit row in place, and future rounds return `no_trigger`.
Nothing surfaces the inconsistency to `run`/`status`. This is worse than "no automatic check".
→ **FAIL for crash consistency in that window (pre-acknowledged as a gap, but the concrete
consequence is silent data loss + a stuck task).**

### 4.3 Extra: copying a task directory inherits cross-task authorization

Landing §9-3 / invariant I8 say "副本不继承授权 / a copy does not inherit authority"; the
`deliver` docstring says "a copy of a task directory never inherits either". I copied two
related tasks to a fresh root with no re-registration:

```
copied sender grants: [{'kinds': ['user.message'], 'peer': 'recv-b'}]
copied recv   wants : [{'kinds': ['user.message'], 'peer': 'sender-a'}]
deliver between copies -> delivered=True decision=accepted
```

Because `wants`/`grants` live in the copied `task.json` and there is no host-side grant
registry, **copies carry their authorization**. → **FAIL vs landing §9-3/I8 and the code's own
docstring.** (The M1 contract does not claim the host registry; landing §12.3 lists "是否只在
host" as unresolved. Still, the documented invariant is not met.)

### 4.4 Extra: torn trailing line is neither truncated nor traced — and causes loss of the *next* fact

Landing §6: a torn tail line must be truncated and explicitly recorded, never parsed as a fact.
`facts.torn_tail()` exists but is dead code. Probe: append `{"seq":2,"kind":"task.comple`
(no newline) to a good `facts.jsonl`, then run a Round that emits a `shell` fact:

```
emitted (runtime return) : ['sys.tool.result#2']
raw facts.jsonl line 2   : {"seq":2,"kind":"task.comple{"digest":"sha256:391a…","id":"sys.tool.result#2",…}
read_facts() now sees    : [1]          # the torn line AND the new fact are both dropped
```

`append_fact` (`facts.py:70-71`) opens in append mode without ensuring the file ends in `\n`,
so the new fact is concatenated onto the torn half-line; `read_facts` then aborts at that
unparseable line and never sees the new fact. The Round still reports `committed`, `head`
advances, and `emitted` lists a fact that no reader can recover. → **FAIL (§6 torn-tail
discipline; also breaks head↔facts consistency for that fact).**

### 4.5 (a) `deliver` with no relations declared

```
$ python3.12 -m lore_task deliver --from-root … --from-task sender-a --to-root … --to-task recv-b \
    --foreign-id f-unauth --kind task.completed --payload '{"x":1}'
{"delivered": false, "reason": "missing wants",
 "admission": {"foreign_id":"f-unauth","kind":"task.completed","digest":"sha256:b759…",
               "decision":"rejected","from":"sender-a","reason":"missing wants"}}
```

Receiver admission ledger contains the rejected row; `facts.jsonl` stays 0 bytes; no round runs.
→ **PASS.** (Extra: wants-only → `"missing grants"`; authorized-but-admission-rejected rows —
e.g. delivering `task.completed` to a `goal` task — are recorded `decision:"rejected"` but with
**no `reason` field**, a minor observability gap.)

### 4.6 (b) Shell with unregistered target

```
$ python3.12 -m lore_task run --root … --task-id probe-b --provider faux \
  --faux-response '{"action":{"type":"shell","script":"touch /tmp/ia-verify/adv/SIDE_EFFECT_B","target":"workspace:nope"}}' \
  --max-steps 1
sys.tool.result payload: {"cwd":null,"exit":126,"script":"touch …SIDE_EFFECT_B",
                          "stderr":"unauthorized or unknown shell target: workspace:nope","target":"workspace:nope"}
$ ls /tmp/ia-verify/adv/SIDE_EFFECT_B  →  No such file or directory
```

→ **PASS.** Control: `--workspace /tmp/ia-verify/adv/ws1` + `target:"workspace:ws1"` runs with
`cwd=/tmp/ia-verify/adv/ws1`, `exit=0`, and creates the file.

### 4.7 (c) `emit` with a stale `base_rev`

Round-1 committed revision `sha256:e3b0c442…`. Faux reply:
`{"action":{"type":"emit","kind":"design.unit.accepted","payload":{"unit_id":"u1"},"base_rev":"sha256:000…"}}`.

```
facts kinds: ['design.objective.set', 'sys.declaration.rejected']
has real design.unit.accepted fact: False
sys.declaration.rejected payload: {"base_rev":"sha256:000…","committed_rev":"sha256:e3b0c442…",
                                   "kind":"design.unit.accepted","reason":"stale base revision"}
```

→ **PASS.** Control with the correct revision → `design.unit.accepted` is appended.

### 4.8 (e) Malformed harness manifests

| Variant | Result |
|---|---|
| `{"kind":"sys.evil","producer":"harness"}` | `ManifestError: reserved prefix must not be claimed: sys.evil` (CLI ingest rc 1, traceback) |
| `{"kind":"acme.x","producer":"runtime"}` | `ManifestError: runtime-produced kind must use reserved prefix: acme.x` |
| trigger on undeclared kind | `ManifestError: trigger t references undeclared kind nope.kind` |
| role entry missing `id` | `ManifestError: malformed role entry in logic: {'ref': …}` |
| `schema:"lore-harness/v2"` | `ManifestError: unsupported harness schema: 'lore-harness/v2'` |
| producer `"wizard"` | `ManifestError: unknown producer for acme.x: 'wizard'` |
| role `ref` pointing at a missing file | `FileNotFoundError: missing declared ref: logic/does-not-exist.py` |

→ **PASS** (loud refusal, no degradation). Note the missing-ref case raises `FileNotFoundError`
rather than `ManifestError`; still loud and non-zero.

---

## 5. Credential hygiene

Command: in-process `provider.load_env_file('~/.env')` then a byte scan of all 1753 non-`.git`
regular files under the repo for the literal value (the value was never printed).

```
ARC_PLAN_API_KEY present in ~/.env: True | in env var: False
files scanned (excl .git): 1753
files containing the literal key value: NONE
files mentioning the VARIABLE NAME: lore_task/cli.py,
  design/g3/provider/amendment-model-baseline-2026-09-16-ark.md,
  design/g3/voice-assistant/{architecture,providers,research-notes,README}.md,
  design/g3/voice-assistant/probe_plan_endpoints.py,
  lore_task/__pycache__/cli.cpython-312.pyc,
  validation/task_runtime/FINDINGS-2026-09-16.md,
  validation/task_runtime/acceptance/independent-acceptance-B.md
```

- No repo file contains the credential **value**.
- The evidence/task directories (`evidence/ark-*/root/*`) contain **neither the value nor even
  the variable name** — they carry no credential material at all. The name appears only in
  source, design docs and process records.
- The CLI keeps the key in process memory only (`cli.py:156-163`); `session/rounds/*.jsonl`
  store request/reply/usage but no Authorization header (confirmed by the repo-wide scan).
- → **PASS.**

---

## 6. Scenario inventory

Nine scenarios (landing §4.2 table). `find lore_harness -name manifest.json` yields **10**
harness directories because `delegation` is implemented by a parent + child pair. Every
manifest was loaded through the real `manifest.load` (verify=True):

| # | Scenario | Harness dir(s) | `manifest.json` | Offline case | Evidence |
|---|---|---|---|---|---|
| 1 | goal | `lore_harness/goal` | valid, load PASS | `offline_goal_round.py` | `ark-goal-001…003` |
| 2 | plan | `lore_harness/plan` | valid, load PASS | `offline_plan_rounds.py` | `ark-plan-001` |
| 3 | archive | `lore_harness/archive` | valid, load PASS | `offline_archive_round.py` | `ark-archive-001…003` |
| 4 | ask-user | `lore_harness/ask_user` | valid, load PASS | `offline_ask_user.py` | `ark-ask-001` |
| 5 | coding | `lore_harness/coding` | valid, load PASS | `offline_coding_round.py` | `ark-coding-001` |
| 6 | research | `lore_harness/research` | valid, load PASS | `offline_research.py` | `ark-research-001…009` |
| 7 | delegation | `lore_harness/delegation_parent` + `delegation_child` | both valid, load PASS | `offline_delegation.py` | `ark-delegation-001…002` |
| 8 | monitoring | `lore_harness/monitoring` | valid, load PASS | `offline_monitoring_round.py` | `ark-monitor-001` |
| 9 | system-design | `lore_harness/system_design` | valid, load PASS | `offline_system_design.py` | `ark-design-001…005` |

→ **PASS: 9/9 scenarios, 10/10 manifests valid and loadable.**

---

## 7. Summary of PASS/FAIL

**Required checks (task items 1–6)**

| Item | Verdict |
|---|---|
| 1. Code-level contract conformance (11 sub-claims) | **PASS** on all 11, with the explicit caveat in §4.1 that `recover` does not preserve original bytes → that sub-claim is **FAIL** |
| 2. Offline cases: 135 PASS / 0 FAIL, deterministic across two runs | **PASS** (record claims 132 — discrepancy noted) |
| 3. Six checkers on recorded evidence, all green; falsifiability confirmed; digest recomputed by hand | **PASS** |
| 4a. Unauthorized `deliver` refused + recorded rejected | **PASS** |
| 4b. Unregistered target → exit 126, no side effect | **PASS** |
| 4c. Stale `base_rev` → `sys.declaration.rejected`, no declaration | **PASS** |
| 4d. Interrupt → `recovery_needed` → `recover` quarantines + truncates + traces + preserves content | **PARTIAL** — semantics PASS, **byte preservation FAIL** |
| 4e. Malformed manifest (sys.\* claim / missing ref) refused loudly | **PASS** |
| 5. Credential hygiene | **PASS** |
| 6. 9 scenarios / 10 harness manifests | **PASS** |

**Additional counterexamples found (not in the required list)**

1. **§4.4 torn tail** — torn trailing line is never truncated/traced (`torn_tail` is dead code);
   `append_fact` concatenates the next fact onto the torn line, and `read_facts` then silently
   drops **both**, while the Round reports `committed` and lists the lost fact in `emitted`.
   Violates landing §6. **FAIL.**
2. **§4.2 commit→head crash window** — `recover` deletes a fact the ledger recorded as
   committed, leaves the `phase:commit` row, and future runs return `no_trigger`. Pre-acknowledged
   in FINDINGS as "no automatic check", but the concrete behavior is silent loss + stuck task.
   **FAIL.**
3. **§4.3 copy inherits authorization** — contradicts landing §9-3 / I8 and the `deliver`
   docstring. **FAIL.**
4. **§1b unknown `layout_version`** — `layout_version=99` runs normally; landing §10 requires a
   loud refusal. **FAIL.**
5. **§1b declared role digest** — never compared to content (landing §4.5 R2). Disclosed M1 gap;
   **FAIL vs landing**, PASS vs the M1 contract's own gap list.
6. **FINDINGS assertion count** — says 132 (its own parts sum to 134); actual **135**, and
   system-design is 18-vs-19. Record defect, not a product failure.

**Nothing above is softened.** The runtime's core M1 mechanisms (single-writer facts,
trigger-vs-commit watermark separation, head-as-commit-point, `final` as proposal, guard,
conditional emit, targeted shell routing, wants+grants delivery, deterministic recall,
quarantine-on-start-marker) are genuinely implemented and reproducible. The failures are all in
edge/durability territory: torn-tail handling, the commit→head crash window, `layout_version`
gating, and the copy-does-not-inherit-authority invariant.

### What I could NOT verify / limitations

- **Provenance of the recorded real-model evidence.** I re-ran the checkers against the bytes,
  but bytes alone cannot prove the replies came from the ARC model rather than a fixture. I did
  not re-issue network calls. The real-model runs are therefore *re-validated as artifacts*, not
  *independently reproduced*.
- **Role separation is partial.** I am a separate agent context, but I run on the same machine,
  in the same workspace, started by the implementing session; I share its credentials and can
  read its files. I am not a third-party institution and this is not security isolation. A second
  lane (`independent-acceptance-B.md`) exists in the same workspace and is subject to the same
  limitation.
- **Source pinning.** `lore_task/` and `lore_harness/` are untracked in git (`git status` shows
  `?? lore_task/`, `?? lore_harness/`), so there is no commit hash tying this report to an exact
  source revision; digests were recomputed at run time only.
- **Not exercised:** concurrency / single-writer lease (landing §6, I2/I8 host side);
  arbitrary-cut-point crash injection (I ran two cut points only); `derived/` delete-and-rebuild
  determinism (I5/VD06); L2 unknown-entry preservation (VD14/VE06); real sandbox isolation — the
  Workspace domain is routing/bookkeeping only and a model script can `cd` out (acknowledged in
  FINDINGS:97); long tasks, time/timer triggers beyond the monitoring evidence.
- **`recover` byte-fidelity** and the three extra counterexamples were reproduced only in my
  `/tmp` task roots, not against the shipped evidence (I did not run `recover` against
  `validation/task_runtime/evidence/**`, per the read-only constraint). The mechanisms are
  identical for shipped tasks, but the counterexamples are my own constructions.

---

# Re-verification after fix (second pass, 2026-09-17)

The implementer reported 5 product fixes + record corrections. I did **not** trust that
message: I re-read the changed source (`lore_task/{facts,layout,manifest,round}.py`), re-ran my
exact five reproductions against fresh `/tmp/ia2` task roots, re-ran the whole offline suite
twice, re-ran all six checkers, and hunted for new bypasses/regressions. All scratch is under
`/tmp/ia2/`; no product or evidence file was modified.

## Per-finding verdict after the fix

| Original finding | Verdict after fix | Raw evidence |
|---|---|---|
| **F1. `recover` must preserve original bytes** | **PASS** | Mid-Round crash (provider raises after a shell fact) → `recovery_needed` → `recover`. `raw_before.split(b"\n",1)[1]` (the discarded tail verbatim, incl. trailing `\n`) `==` the `session/crashed/facts-after-…jsonl` bytes → **True**; kept prefix `==` pre-crash first line + `\n` → **True**. `round.py:231-233` now copies/truncates raw lines; no `json.dumps` re-serialization. |
| **F2. commit-not-published window** | **PASS** | Simulated SIGKILL after `ledger.record_round`, before `write_json(head)`. `run` → `{"status":"recovery_needed","reason":"commit_not_published","published_seq":0,"committed_seq":1}`. `recover` → `{"status":"recovered","action":"published_commit","published_seq":1}`. Head afterwards `==` the last commit row on `facts_end`, `revision` and `round_id` (**True**); the objective fact is **not** discarded; `repairs.jsonl` has the `published_commit` row; a later `run` returns `no_trigger` (not stuck) and after a fresh objective it commits (`round-0002`). `recover` is idempotent (second call → `nothing_to_recover`). |
| **F3. copy must not inherit cross-task authorization** | **PASS for passive copies** (1 residual — see N4) | Original registered pair → `delivered=true`. Copied task dirs to a fresh root → `{"delivered":false,"reason":"sender task snd is not registered at this location (a copy has no authority)"}` + a `decision:"rejected"` admission row. Copying the **whole root incl. `.lore-authority.json`** → still refused (stored absolute paths no longer match). Copy inside the **same** root under a new name → refused. |
| **F4. torn trailing line must not corrupt the next append** | **PARTIAL → 2 new counterexamples (N1, N2)** | The mid-line shape now works: `repair_torn_tail` truncates and records `discarded_b64` (base64 decodes to the exact torn bytes → True); the next shell fact is readable and existing facts survive. But two other torn shapes still fail hard — see N1/N2. |
| **F5. `layout_version > 1` refused loudly** | **PASS** | `run_round`, `ingest`, `deliver`, `recover` all raise `ValueError: unsupported task layout_version 99 (runtime supports <= 1)`. |
| **F6. declared role/contract/view digests compared** | **PASS** | Wrong role digest → `ManifestError: role logic entry goal digest mismatch: declared sha256:000…, actual sha256:cdc6…`; wrong contract digest → `ManifestError: kind task.objective.set contract digest mismatch…`; wrong view resolver digest → `ManifestError: view v resolver digest mismatch…`; correct digests load. `manifest.load` is only ever called with `verify=True` (grep). No shipped harness manifest declares a digest, so no template breaks. |
| **F7. record defect: offline assertion count** | **FIXED** | New suite: **11 cases / 149 PASS / 0 FAIL**, identical check-lines on two runs (the old claim was 132; the old 10 cases now total 141, and the new `offline_invariants.py` adds 6, plus `offline_crash_recovery.py` grew 11→19). |

**Regression checks (all clean):** the six checkers on the recorded evidence are still green
(goal 13, plan 12, coding 14, design 14, research 17, delegation 16; all `"ok": true`); my
original probes (a) unauthorized deliver → `missing wants`, (b) `workspace:nope` → `exit 126`,
`cwd=null`, no side-effect file, (c) stale `base_rev` → `sys.declaration.rejected` with no real
`design.unit.accepted` fact, (e) malformed manifests refused — all still behave correctly.

## New counterexamples / residuals (not softened)

**N1 — torn shape "complete JSON object, missing only the trailing newline" still corrupts the
next append and bricks the task (F4 incomplete).**
A single `open(...,"ab")` write of `_canonical(body)+b"\n"` that is cut one byte short leaves a
valid JSON line with no newline. `repair_torn_tail` (`facts.py:78-83`) does `json.loads(tail)`,
succeeds, and returns without adding the newline; the next `append_fact` then concatenates two
JSON objects onto one physical line:

```
raw facts after the shell step:
b'{…"seq":1…}{"digest":"sha256:f6ca…","id":"sys.tool.result#2",…}\n'
run_round      -> RAISED json.decoder.JSONDecodeError: Extra data: line 1 column 197
repairs.jsonl  -> does not exist (no trace)
recover()      -> {"status":"nothing_to_recover","committed_seq":1}   # leaves corruption
read_facts()   -> still raises; every later run() raises
```

So this shape does **not** "never corrupt the next append": the Round crashes, no repair trace
is written, and `recover` refuses to act — the task is stuck until manual byte surgery.

**N2 — `recover` raises on an interrupted Round whose uncommitted tail is torn, leaving a
permanently stuck task with no repair/inspection trace.**
With a `phase:start` marker and a torn uncommitted line, `recover` writes the quarantined bytes
verbatim and truncates `facts.jsonl` (good), then builds the repair row with
`discarded: [json.loads(line)["id"] for line in parts[keep_seq:]]` (`round.py:235`) — which
raises on the torn line **after** the truncation, so the repair row and the `abort` marker are
never written:

```
recover()            -> RAISED JSONDecodeError: Expecting property name enclosed in double quotes
facts after attempt  -> truncated to the objective line only
crashed/             -> facts-after-1-….jsonl saved (bytes intact)
repairs.jsonl        -> does not exist
run()  (x3)          -> {"status":"recovery_needed", …}   forever
recover() (x3)       -> {"status":"nothing_to_recover", …} forever
rounds.jsonl last    -> still phase:"start" (no abort row)
```

The crash is untraced and the task can never proceed. (The tail bytes themselves are not lost,
but the recovery is.)

**N3 — a fault *during* `recover` (after truncation, before the repair/abort rows) produces the
same permanent stuck state, untraced.** Recover is a multi-step, non-atomic sequence; if it is
interrupted after `atomic_write(facts)` and before `ledger.append_jsonl(repairs/abort)`, a
second `recover` sees `len(parts) <= committed` and returns `nothing_to_recover` while the
`start` marker still dangles: `run` → `recovery_needed` forever, `recover` →
`nothing_to_recover` forever, no `repairs.jsonl`. `recover` is not resumable/idempotent across
its own writes.

**N4 — residual (scope, not a regression): the authority file is unauthenticated.** A **passive**
copy is correctly refused, but placing a hand-written `<new-root>/.lore-authority.json` that maps
`snd`/`rcv` to the copies' absolute paths makes `deliver` succeed:
`copy + FORGED authority file -> {"delivered": true, decision:"accepted"}`. The registry is a
plain JSON file adjacent to the task dirs, so anyone who can write the new root can self-authorize.
This is outside the "a copy must not passively inherit authority" threat model, but it means the
fix is not a security boundary.

**N5 — residual (scope): `deliver` authority is only enforced on the `deliver` path.** A local
actor can still inject a cross-task fact with `lore_task ingest` (the E1 external-admission gate)
without any `wants`/`grants`; e.g. a copied `delegation_child` with **no** authority file accepts
`ingest --kind task.delegated` (`decision: accepted`, fact lands). Correct by the contract
(admission ≠ authorization) but worth stating so `deliver`'s check is not mistaken for a
cross-task enforcement boundary.

**N6 — residual: no CLI path to re-authorize an imported task.** `.lore-authority.json` stores
absolute host paths in the tasks-root (host-side by design), but `cli.py` has no `register`
command; after moving a root to a new host, `deliver` is refused with no CLI remedy short of
recreating the task directories.

## Re-verification limitations

- Same-machine / same-workspace / same implementing session; `lore_task/` and `lore_harness/`
  remain untracked, so there is still no commit hash pinning the re-verified source. The source
  mtimes at re-verification were `facts.py`/`layout.py` 07:49 and `manifest.py`/`round.py` 07:50.
- N1–N3 were reproduced in my own `/tmp` roots, not against shipped evidence. N1/N2 require a
  crash (or byte truncation) at exact offsets; they are realistic partial-write shapes, not
  arbitrary corruption.
- I did not re-run real-model network calls; recorded evidence was re-validated as bytes only.

---

# Re-verification #2 (after the N1/N2/N3/N5/N6 fixes, 2026-09-17)

Again read the changed source myself (`lore_task/{facts,round,manifest,cli,layout}.py`,
`lore_harness/delegation_child/manifest.json`), reproduced my own shapes under `/tmp/ia3/`,
re-ran the suite twice and all nine checkers, and looked for further partial-write /
recovery-fault shapes. Source mtimes: `facts.py` 07:55, `round.py`/`manifest.py`/`cli.py` 07:54.

## Per-fix verdict

| Fix | Verdict | Raw observation |
|---|---|---|
| **N1 — complete JSON missing only the trailing newline** | **PASS** | Injected `_canonical(fact)` (exactly 1 byte short of `_canonical(fact)+b"\n"`) as the last line. `run_round` → `{"status":"committed","emitted":["sys.tool.result#3"]}`; `read_facts` → seq 1,2,3; every physical line parses as JSON; `repairs.jsonl` has `{"action":"restore_missing_newline","discarded_len":0}`. The invalid-JSON (mid-line) shape still takes the `truncate_torn_tail` path with `discarded_b64` decoding to the exact torn bytes. |
| **N2 — interrupted Round with a torn uncommitted tail** | **PASS for one call** | `recover` → `{"status":"recovered","discarded":["<torn:366 bytes>"],"kept_seq":1,...,"byte_identical":true}`; quarantined bytes intact; `repairs.jsonl` written; last ledger row `abort`; a following `run` with a provider commits (not stuck). |
| **N3 — fault inside recover** | **PARTIAL → the convergence claim is FALSE (new counterexample N7)** | Fault before the repair row: a later `recover` completes; fault after truncation/before abort: first call returns `{"status":"nothing_to_recover","aborted_start":true}` and the start marker is aborted, so the task is **not permanently stuck**. But a **second** `recover` call does not return `nothing_to_recover` — it performs another recovery that **deletes the admitted objective fact**. See N7. |
| **N5 — `requires_relation`** | **PASS for the named kind, class not closed** | Direct `ingest --kind task.delegated` on `delegation_child` → `ValueError: kind task.delegated requires relation-mediated delivery (use deliver with wants+grants)`, facts file stays empty, no admission row; `deliver` (wants+grants+authority) → `accepted`. **Residual N9:** other cross-task kinds are unmarked — direct `ingest --kind task.reported` on `delegation_parent` and `user.message` on `goal` are both `accepted`. |
| **N6 — `register` CLI** | **PASS** | Copy refused (`"sender task snd is not registered at this location (a copy has no authority)"`); `lore_task register --root <newroot> --task-id {snd,rcv}` writes the authority entries; `deliver` then → `{"delivered":true,"decision":"accepted"}`. **Minor:** `register` on a task that does not exist still writes an authority entry (`{"ghost": {root: …/ghost}}`); harmless for `deliver` (it reads `task.json` first) but sloppy. |
| **N4 — forged authority file** | **Agree: not fixable here without inventing a trust root** | With same-UID write access to the target root, any plain-file registry can be written. I confirmed the forgery still works (`copy + forged .lore-authority.json → delivered=true`). Cheap honest mitigations, none of which are security: (a) state in the contract/docstring that the authority file is an authorization-of-location record, **not** a security boundary; (b) exclude `.lore-authority.json` from exports/imports and require `register` after import; (c) keep the file outside the task root (still forgeable by the same UID). Any real protection needs a key/identity the copier does not have — i.e. PKI or a host secret — which is out of scope. I do **not** consider this a fixable defect for the stated threat model. |

**Regression checks (all clean):** full offline suite **11 cases / 160 PASS / 0 FAIL**, run twice,
check-lines identical (note: the message said `offline_crash_recovery.py` has 27 checks; it
actually emits **28**). Nine checkers now exist (`verify_{goal,plan,archive,ask_user,coding,
research,delegation,monitoring,design}…`); I re-ran all nine on the recorded evidence and every
fresh PASS/FAIL line set is **byte-identical to the saved `verify.txt` artifacts** (goal 13, plan
12, archive 11, ask_user 9, coding 14, research 17, delegation 16, monitoring 8, design 14 — all
green). None of the checkers import `lore_task`.

## New counterexamples

**N7 (high) — calling `recover()` twice after a successful recovery destroys admitted facts.**
Clean minimal reproduction, and the same via the CLI:

```
facts before recover : [task.objective.set(1), sys.tool.result(2)]   head.facts_end.seq = 0
recover #1 -> recovered, committed_seq=1, discarded ["sys.tool.result#2"]   rounds: [start, abort]
facts after #1       : [task.objective.set(1)]
recover #2 -> recovered, committed_seq=0, discarded ["task.objective.set#1"]
facts after #2       : []            <-- the admitted objective is gone
recover #3 -> nothing_to_recover, committed_seq=0, aborted_start=false
```

CLI form: `lore_task recover --root R --task-id t` twice gives exactly the same result
(`discarded ['sys.tool.result#2']` then `discarded ['task.objective.set#1']`, `facts` → empty).

Root cause: after the `abort` row is appended, `interrupted` is `None` (the last row is no longer
`start`), so `committed` falls back to `head.facts_end.seq` (0 for a first interrupted round) and
everything above head is treated as crash tail. The `abort` row does not carry `trigger_seq`, so
the commit floor is lost. This falsifies the claimed "repeated recover calls converge
(`nothing_to_recover` with `aborted_start: true`)": the second call converges only after deleting
the protected facts. It is a **pre-existing** fallback flaw (the same `interrupted/committed`
logic existed before this round) but it is now easier to hit because `_finish_abort()` writes the
`abort` row on the `nothing_to_recover` path, so the first call can return "nothing to recover"
and invite a retry that then destroys data. Cheap fix: store `trigger_seq`/`committed_seq` in the
`abort` row and use it as the floor when the last row is `abort`; or return `nothing_to_recover`
immediately whenever the last round row is already `abort` (only a new `start` re-arms recovery).

**N8 (boundary) — a malformed last line that *is* newline-terminated is not inspected and
silently hides the next fact.** With `facts.jsonl` ending in `{"seq":2,"kind":"torn\n` (bad line
but terminated), `repair_torn_tail` no-ops (last byte is `\n`) and `torn_tail()` returns False;
the next `run` appends `sys.tool.result#2` but `read_facts` still sees only seq 1, while the round
reports `committed` and `emitted:["sys.tool.result#2"]` and `head.facts_end.seq=1`. Not producible
by the runtime's own writer (`_canonical(body)+b"\n"` is one write, so a short write lacks the
`\n`), i.e. it requires external corruption of the stream — but the silent loss of the appended
fact is worth recording. A truncate-and-trace on "last non-empty line fails to parse", regardless
of trailing newline, would close it.

**N9 (residual, class not closed) — `requires_relation` is per-kind and only one kind is marked.**
`delegation_parent`'s `task.reported` and `goal`'s `user.message` are still directly ingestable
without `wants`/`grants`; a local actor can inject a "child report" into a parent or a user
message into a goal. If the intent is "cross-task kinds must be relation-mediated", mark every
such kind (or default to requiring a relation for kinds whose producer is `external` and that
appear in a delegation/user-facing contract).

**N10 (minor) — publish-branch fault loses only the trace.** If a fault hits between the
`write_json(head)` and the `published_commit` repair row, `head` is already correct and the task
is not stuck (`recover` → `nothing_to_recover`), but no `published_commit` trace exists. Minor
inspection gap, no data loss.

## Re-verification #2 limitations

- Same partial role separation: same machine/workspace, started by the implementing session;
  `lore_task/` remains untracked (no commit pin).
- N7/N8/N9 were reproduced in my own `/tmp/ia3` roots; N8 requires external stream corruption.
- I did not re-run real-model network calls; the nine saved `verify.txt` artifacts were
  re-derived and matched, which validates the artifacts, not the model provenance.

---

# Re-verification #3 (after the N7/N8/N9/N10 fixes, 2026-09-17)

Read the changed source myself (`lore_task/facts.py` `repair_torn_tail`, `round.py` `recover`
+ publish branch, `manifest.py`, `delegation_parent/manifest.json`), reproduced every shape in
my own `/tmp/ia4` roots, ran the suite twice and all nine checkers, and fuzzed additional
partial-write / recovery / concurrency shapes. Source mtimes: `facts.py`/`round.py` 07:59.

## Per-fix verdict

| Fix | Verdict | Raw observation |
|---|---|---|
| **N7 — double recover destroys admitted facts** | **PASS** | `recover` now only acts when the last `rounds.jsonl` row is `start`; the `abort` row carries `trigger_seq`. Python: after `recover#1` (recovered, kept objective), `recover#2/#3/#4` → `{"status":"nothing_to_recover","reason":"no interrupted round","committed_seq":0}`, facts bytes and rounds rows **unchanged** each time, kinds stay `['task.objective.set']`, exactly one `abort` row and one repair row. CLI: `lore_task recover` three times → `recovered`, then `nothing_to_recover` twice, objective intact. |
| **N8 — newline-terminated malformed last line** | **PASS** | With `facts.jsonl` = good line + `b'{"seq":2,"kind":"torn-with-newline\n'`: `repair_torn_tail` → `truncate_torn_tail`, `discarded_len=35`, `base64.b64decode(trace.discarded_b64) == the exact bad bytes` (**True**); the next `run` appends `sys.tool.result#2`, `read_facts` sees seq 1 and 2, existing fact survived. Also verified with a true mid-UTF-8 cut (`b'\xc3'` without `b'\xa9'`): `UnicodeDecodeError` → truncate, trace bytes exact. |
| **N9 — `task.reported` marking** | **PASS (and I agree on `user.message`)** | Direct `ingest task.reported` on `delegation_parent` → `ValueError: kind task.reported requires relation-mediated delivery (use deliver with wants+grants)`; `deliver` with wants+grants+authority → `{"delivered":true,"decision":"accepted"}`. `user.message` stays directly ingestable. **I agree with that boundary:** `user.message` models an external human (the authority), who has no `task.json`/grants; forcing a relation would break the ask-user/goal flows, and a local operator running `lore_task ingest` already has the same trust level as someone editing `task.json`/the authority file, so it buys no security. The general "cross-task kind" class is still marked by hand (see R3). |
| **N10 — publish trace order** | **PASS** | Fault injected at `recover`'s `write_json(head)`: `published_commit` trace already exists while `head.facts_end.seq` is still 0; a second `recover` publishes and advances head to 1. Minor cosmetic: the retry writes a **second, identical** `published_commit` row (duplicate trace, no data loss). |

**Suite / checkers (regression):** offline suite **11 cases / 164 PASS / 0 FAIL**, run twice,
check-lines identical. Note the message said `offline_crash_recovery.py` is 33 checks; it emits
**32** (the four new N7/N8 checks are `second_recover_is_noop`,
`double_recover_keeps_admitted_facts`, `terminated_malformed_line_repaired`,
`terminated_malformed_traced`). All nine checkers still exist and every fresh PASS/FAIL set is
**byte-identical to the saved `verify.txt`** (goal 13, plan 12, archive 11, ask_user 9, coding 14,
research 17, delegation 16, monitoring 8, design 14; all `ok:true`).

## Additional shapes fuzzed (parent's list + my own)

**Partial-write matrix (all with a real valid fact prefix).** clean → no-op; clean-without-final-
newline → `restore_missing_newline`; blank/whitespace-only lines → no-op; valid line + partial line
(with or without trailing newline) → `truncate_torn_tail` with the exact discarded bytes; a second
complete fact line missing only its newline → `restore_missing_newline` and the append lands as
seq 3. In every case the next appended fact was visible via `read_facts`. ✔

**R1 (minor robustness) — a `start` row *without* `trigger_seq` raises `KeyError`.**
`round.py:223` does `committed = interrupted["trigger_seq"]`. A hand-edited/foreign directory whose
last row is `start` but has no `trigger_seq` → `recover` RAISES `KeyError: 'trigger_seq'` rather
than refusing or deriving. The runtime always writes `trigger_seq` on `start` rows, so this needs a
foreign writer; `abort` rows without `trigger_seq` are safe (the last-row check returns
`nothing_to_recover` before that line). Cheap hardening: `interrupted.get("trigger_seq")` + an
explicit refusal/fallback.

**R2 (boundary) — corruption in the *middle* of the stream is still silent.** `repair_torn_tail`
inspects only the last non-empty line. With `good\n{broken\n{valid}\n`, `read_facts` stops at the
broken line and everything after it is invisible, while the next append is concatenated after the
already-present later lines. This is not producible by the runtime's own writer (append-only, one
write per line) and is outside landing §6 (tail discipline), but it silently drops facts under
external corruption; a whole-file parse-and-truncate would close it.

**R3 (residual, policy completeness) — `requires_relation` is manual per kind.** The N9 class is
only closed for the two kinds that were marked; a harness can still declare a cross-task kind
without it, and nothing checks that an `external` kind appearing in a delegation contract is
marked. This is a policy-audit gap, not a mechanism bug.

**R4 (known gap) — concurrent `recover` is not serialized.** Two threads with a barrier on a
crashed task: both returned `recovered`, both wrote the same `session/crashed/…` file, and in
**1 of 8** runs **two `abort` rows** were appended (`phases: [start, abort, abort]`); duplicate
`repairs` rows occurred every run. No fact loss or corruption in 8 runs, but there is no lease —
exactly the concurrency gap the landing contract already lists as unimplemented. Not a regression;
reported because the parent asked.

**R5 (minor) — repeat publish writes a duplicate trace row** (see N10 above).

## Re-verification #3 limitations

- Same partial role separation (same machine/workspace, started by the implementing session);
  `lore_task/` remains untracked, so still no commit hash pinning the re-verified source.
- R1–R5 were reproduced in my own `/tmp/ia4` roots; R2/R3 require foreign input or manual marking;
  R4 is inherently racy (8 runs is a smoke test, not a proof).
- Recorded evidence was re-validated as bytes/artifacts only; I made no real-model network calls.
- Credential hygiene unchanged: a fresh in-process scan still found no file containing the key value.

---

# Re-verification #4 (after R1/R2/R5 fixes, 2026-09-17) and overall verdict

Read the changed source myself (`facts.py read_facts`, `round.py recover` R1/R5), reproduced the
shapes under `/tmp/ia5`, stress-tested the new strictness for false positives, re-ran the suite
twice and all nine checkers. Source mtimes: `facts.py`/`round.py` 08:02.

## Per-item verdict

| Item | Verdict | Raw observation |
|---|---|---|
| **R1 — `start` row without `trigger_seq`** | **PASS** | `recover` → `ValueError: interrupted round r-old has no trigger_seq; refusing to guess the commit floor`; `facts.jsonl` byte-unchanged; no `repairs.jsonl`, no `abort` row appended (rounds rows unchanged). |
| **R2 — mid-stream corruption is loud** | **PASS on the asked criteria** | `good\n{broken\n{valid}\n`: `read_facts` → `ValueError: corrupt fact stream at physical line 2: Unterminated string…`; `run_round` raises the same; `facts.jsonl` bytes **unmodified**; no repair row. Tail shapes still repaired (full matrix below). |
| **R5 — no duplicate publish trace** | **PASS** | Two faults at `recover`'s head write then a successful publish → exactly **1** `published_commit` row; `head.facts_end.seq = 1`. |
| **R3 — manual `requires_relation`** | **accept the characterization** | Auto-inferring which kinds are cross-task would be guessing at policy; a manual manifest flag plus a policy note is the honest boundary. It stays a completeness/audit gap, not a mechanism defect. |
| **R4 — no concurrency lease** | **accept the characterization** | The landing contract itself lists the single-writer lease as unimplemented; my 8-run smoke test showed duplicate abort/repair rows but no fact loss. Not a regression and not fixable inside this scope. |

**Tail matrix still behaves under the strict reader:** clean → no-op; missing final newline →
`restore_missing_newline`; blank/whitespace lines → no-op; valid + partial (with/without newline) →
`truncate_torn_tail`; second complete fact missing its newline → `restore_missing_newline` and the
append lands as seq 3. Next append visible in every case. ✔

## NEW counterexample — R6 (high): the strict reader has a legitimate-stream FALSE POSITIVE

`read_facts` iterates `p.read_text().splitlines()`, but `str.splitlines()` also breaks on
**U+2028 (LINE SEPARATOR), U+2029 (PARAGRAPH SEPARATOR) and U+0085 (NEL)** — and
`json.dumps(..., ensure_ascii=False)` emits those characters **literally**, unescaped. So a
perfectly legitimate fact written by the runtime's own `append_fact` splits into two physical
"lines", the first of which is truncated JSON:

```
payload {"note": "before\u2028after"}  (also U+2029, U+0085)
append_fact -> writes the fact, returns it          (runtime wrote a valid record)
read_facts  -> ValueError: corrupt fact stream at physical line 1: Unterminated string ...
str.splitlines() pieces = 2 ;  raw.split("\n") pieces = 1 ; json.loads on the \n-split line = OK
```

End-to-end via the CLI: `lore_task ingest --kind task.objective.set` with an objective containing
U+2028 returns **rc 0 / decision accepted** and writes the fact; immediately afterwards
`lore_task status` and `lore_task run` both exit 1 with
`ValueError: corrupt fact stream at physical line 1`. The task is bricked — the runtime accepts
and persists a record it can no longer read. U+2028/U+2029 are common in text pasted from word
processors, PDFs and web pages, so this is reachable without any hand-corruption.

The offline suite does not catch it (171 PASS) because no fixture payload contains those
characters. **Fix is one line:** split on `\n` only (as `repair_torn_tail` already correctly does
with `raw.split(b"\n")`) instead of `str.splitlines()`. Nuance for fairness: before R2 this payload
already broke reads (silently dropped everything after it when it was not the first line, raised
when it was); R2 turns that into an unconditional, loud failure but does not introduce the
splitting bug.

**Minor R7 — the error's "physical line N" is not the physical line number.** The message uses
`len(rows)+1` (parsed non-empty rows), so with blank lines it is wrong: a file whose lines are
`good, <blank>, <blank>, broken` reports "physical line 2". Cosmetic, but the parent explicitly
asked for the right physical line.

**Suite / checkers:** offline suite **11 cases / 171 PASS / 0 FAIL**, run twice, check-lines
identical, `offline_crash_recovery.py` = **39** checks (matches the message). All nine checkers
`ok:true` and every fresh PASS/FAIL set is **byte-identical to the refreshed `verify.txt`**
(goal 13, plan 12, archive 11, ask_user 9, coding 14, research 17, delegation 16, monitoring 8,
design 14).

## Overall verdict: NOT YET CONVERGED (one blocking false positive)

Since re-verification #1 the durable-recovery path has improved substantially and every
previously reported failure has been addressed: N1–N10, R1/R2/R5, and the A-series findings are
either fixed and reproduced green, or explicitly accepted as policy/known-gap (R3/R4). The suite
is deterministic at 171/0 and the nine evidence checkers are stable. The M1 mechanisms themselves
remain sound.

But I cannot call this converged while **R6** stands: the new strict `read_facts` (a) bricks a task
on a legitimate, runtime-written payload containing U+2028/U+2029/U+0085, and (b) is not covered by
any test. That is a data-integrity/availability defect introduced into the read path in this round,
and it is exactly the kind of false positive the new strictness was asked to be checked for. If
`read_facts` splits on `\n` only, I would expect to close this out — subject to the standing
limitations below, which no amount of fixing removes.

## Residual doubts / limitations (final)

- **Role separation is partial**: same machine, same workspace, started by the implementing
  session; `lore_task/` and `lore_harness/` are untracked, so no commit hash pins the verified
  source. This is not third-party acceptance and not security isolation.
- **Recorded real-model evidence** was re-validated as on-disk artifacts (bytes/digests), not
  independently reproduced over the network.
- **Accepted, unresolved by design**: R3 (manual `requires_relation` marking), R4 (no
  single-writer/concurrency lease — duplicate abort/repair rows under concurrent `recover`),
  N4 (authority file is not a security boundary), plus the previously noted un-exercised areas
  (`derived/` rebuild, real sandbox isolation, L2 unknown-entry preservation).
- **R2 boundary**: mid-stream corruption is now loud, but the reader still cannot distinguish a
  torn tail (repaired) from mid-stream damage except by position; a whole-file digest chain would
  be the durable answer.

---

# Re-verification #5 (final, 2026-09-17) and closing verdict

Read the changed readers myself (`lore_task/facts.py`, `ledger.py`, `round.py:_recall`, the nine
checkers), reproduced the CLI R6 case for all three separators, produced the characters *during* a
Round, re-ran the matrix/mid-stream shapes, and swept for remaining `splitlines()` sites and other
payload classes. Source mtimes: `facts.py`/`round.py` 08:0x.

## Per-item verdict

| Item | Verdict | Raw observation |
|---|---|---|
| **R6 — U+2028/U+2029/U+0085 round-trip (runtime)** | **PASS** | CLI, all three code points: `ingest rc=0`, `status rc=0`, `run rc=0`, `facts rc=0`, and the objective's payload round-trips **byte-exactly** (`payload_roundtrip=True`). Round-produced payloads too: a shell whose stdout contains U+2028 and an `emit` payload containing U+2028 both survive `read_facts`; the subsequent `run` returns `no_trigger`. No remaining runtime task-bricking payload found. |
| **R7 — physical line number** | **PASS** | File `good`, blank, blank, `{broken` → `corrupt fact stream at physical line 4` (was "line 2"). `read_facts` now uses `enumerate(split("\n"))`; `ledger.read_jsonl` and `round._recall` also split on `"\n"`. |
| **Matrix + mid-stream not regressed** | **PASS** | clean no-op; missing newline → `restore_missing_newline`; blank → no-op; valid+partial → `truncate_torn_tail`; complete-no-newline → restore + append seq 3. Mid-stream: loud `ValueError`, file bytes unmodified. |
| **Other payload classes** | **PASS** | C0 controls (`\x0b`,`\x1c`,`\x1f`), CR/TAB, NUL all round-trip and are JSON-escaped (no literal control bytes in the file); U+2028/9/85 round-trip; a 2 MB single-line payload round-trips. A lone surrogate (`"\ud800"`) raises `UnicodeEncodeError` **before** anything is written (facts unchanged); in a Round it aborts the round, leaves a `start` marker, and `recover` clears it (`nothing_to_recover aborted_start:true`) — recoverable, not a brick. |

**Suite / checkers:** offline **11 cases / 178 PASS / 0 FAIL**, run twice, check-lines identical
(`offline_crash_recovery.py` now emits **46** checks, incl. the six U+2028/U+2029/U+0085 round-trip
checks and `physical_line_number_reported`). All nine checkers `ok:true` and byte-identical to the
refreshed `verify.txt` (13/12/11/9/14/17/16/8/14). Credential scan: 1771 files, key value **none**.

## Remaining counterexample — R8 (verification asset, not the runtime)

The claim "every JSONL reader … the nine `verify_*.py` checkers now split on `"\n"` ONLY" is **not
fully true**. `validation/task_runtime/verify_research_task.py:39` still uses
`text.splitlines()` inside `independent_recall()`, which the `recall_reproduced_independently`
check compares against the runtime's now-`"\n"`-based `_recall`:

```
content/x.md = "alpha\u2028cache-one\nbeta cache-two\n", query "cache"
runtime _recall        -> [('x.md', 1), ('x.md', 2)]      # correct, "\n" only
checker independent_recall -> [('x.md', 2), ('x.md', 3)] # splitlines() splits on U+2028
MATCH: False
```

So a **legitimate** research task whose recalled content contains U+2028/U+2029/U+0085 would be
marked FAIL by the checker although the runtime is correct — a checker false-negative. Two
test-only helpers have the same residual class: `offline_crash_recovery.py:59` (reads the
quarantined crashed-facts file) and `offline_invariants.py:74` (reads `admission.jsonl`); both are
lower risk because their inputs normally lack those characters. The product runtime is clean —
`grep -rn splitlines lore_task/ lore_harness/` returns only a comment.

## Closing verdict

**CONVERGED for the `lore_task` runtime / M1 product.** I reproduced every shape from five rounds;
the R6/R7 fixes hold; the suite is deterministic at 178/0; the nine evidence checkers are stable;
and I could not construct any remaining runtime payload, tail shape, or recovery fault that bricks
a task or loses committed facts. The only outstanding items are explicitly accepted by design
(R3, R4, N4) or the known un-exercised areas below.

**NOT fully converged for the verification asset:** the R6 claim over-reached on the checker set.
`verify_research_task.py:independent_recall` (and two test-only helpers) still have the
`splitlines()`-class bug and can false-negative a legitimate task. That is a one-line fix
(`text.split("\n")`), but until it is made and re-run I will not describe the checker set as
consistent with the runtime it verifies. If the standard for "converged" is the runtime behaviour
I was asked to verify, it is converged; if it is the whole deliverable including a clean
verification asset, it is not yet.

## Residual doubts / limitations (final)

- **Role separation is partial**: same machine/workspace, started by the implementing session;
  `lore_task/` and `lore_harness/` are untracked, so no commit pin. Not third-party acceptance and
  not security isolation.
- **Recorded real-model evidence** was re-validated as on-disk artifacts only; no network re-runs.
- **Accepted, unresolved by design**: R3 (manual `requires_relation`), R4 (no concurrency lease),
  N4 (authority file is not a security boundary), plus `derived/` rebuild, real sandbox isolation
  and L2 unknown-entry preservation remain unexercised.
- **`ledger.read_jsonl` still silently `break`s** on a corrupt ledger line (unlike `facts.read_facts`,
  which now raises), so ledger corruption can drop committed round records without a trace —
  asymmetric with the new facts strictness; worth a look, not a demonstrated data-loss case here.
- **Lone-surrogate payloads** abort the Round with `UnicodeEncodeError` and require `recover`;
  recoverable, but the error surfaces as a traceback rather than a typed refusal.

---

# Closeout (round 6, 2026-09-17) — R8 + ledger asymmetry fixed

Read the changes myself (`verify_research_task.py`, `offline_crash_recovery.py`,
`offline_invariants.py`, `lore_task/ledger.py`), re-ran the R8 demonstration, swept for
`splitlines()`, exercised the new ledger strictness, and re-ran the suite and all nine checkers.

| Item | Verdict | Raw observation |
|---|---|---|
| **R8 — checker `independent_recall`** | **PASS** | Content `"alpha\u2028cache-one\nbeta cache-two\n"`, query `cache`: runtime `_recall` → `[('x.md',1),('x.md',2)]` and checker `independent_recall` → `[('x.md',1),('x.md',2)]`, **MATCH True** (was `[('x.md',2),('x.md',3)]`). `verify_research_task.py` still passes on `ark-research-009` (17 PASS). |
| **`splitlines()` sweep** | **PASS** | `grep -rn 'splitlines()' lore_task lore_harness validation/task_runtime/*.py` returns **only** the explanatory comment at `lore_task/facts.py:38`. No executable `splitlines()` remains in runtime, harnesses or validation assets. |
| **Ledger strictness — corrupt row** | **PASS** | `admission.jsonl` with a bad row: `read_jsonl`, `ingest` (dedupe) and `status` all raise `ValueError: corrupt ledger row 2 in …/admission.jsonl: …`; bytes untouched. `rounds.jsonl` with a bad row: `read_jsonl`, `run_round` and `recover` all raise; bytes untouched. (Note: `run_round`/`recover` do not read `admission.jsonl`, so corruption there is surfaced by `ingest`/`status` — correct, not a gap.) |
| **Ledger U+2028/9/85 round-trip** | **PASS** | Three rows each carrying U+2028/U+2029/U+0085 in a value → 3 rows read back, all values byte-equal, 3 physical lines. |
| **No regression** | **PASS** | Normal Round commits (`objective + sys.tool.result`); crash shape → `recovery_needed` → `recover` discards the uncommitted fact → next `run` commits. |

**Suite / checkers:** offline **11 cases / 180 PASS / 0 FAIL**, run twice, check-lines identical
(`offline_crash_recovery.py` = **46** checks; `offline_invariants.py` = **10** checks — the message
said 11, actual 10). All nine checkers `ok:true` and byte-identical to the refreshed `verify.txt`
(13/12/11/9/14/17/16/8/14). Credential scan: 1771 files, key value **none**.

## Final closing verdict — **CONVERGED** (whole deliverable: runtime + verification asset)

This round I found **no new counterexample**, and I am saying so plainly rather than inventing one.
Across six rounds every runtime failure (A-series, N1–N10) and every verification-asset defect
(R1/R2/R5/R6/R7/R8) has been fixed and independently reproduced, or explicitly accepted as policy /
known gap. The specific claim that over-reached last round ("the nine checkers split on `\n` only")
is now true — the sweep is clean and the R8 reproduction agrees. The previously noted
`ledger.read_jsonl` asymmetry is fixed and behaves loudly without touching bytes. The suite is
deterministic at 180/0, the nine evidence checkers are stable, and I can no longer construct a
payload, tail shape, ledger corruption or recovery fault that bricks a task or loses committed
facts.

The verdict is bounded by the limitations below, which no further fix in this scope removes:

- **Role separation is partial** — same machine/workspace, started by the implementing session;
  `lore_task/`/`lore_harness/` are untracked, so no commit hash pins the verified source. This is
  not third-party acceptance and not security isolation.
- **Real-model evidence** was re-validated as on-disk artifacts (bytes/digests), not reproduced
  over the network.
- **Accepted by design**: R3 (manual `requires_relation` marking), R4 (no concurrency lease;
  duplicate abort/repair rows under concurrent `recover`), N4 (authority file is not a security
  boundary; forged by anyone with write access to the target root).
- **Unexercised**: `derived/` delete-and-rebuild determinism, real sandbox isolation (Workspace
  domain is routing/bookkeeping only), L2 unknown-entry preservation, arbitrary-cut crash injection
  beyond the shapes tested.
- **Exotic input**: a lone-surrogate payload still aborts a Round with `UnicodeEncodeError` and
  requires `recover` (recoverable, but a traceback rather than a typed refusal).
