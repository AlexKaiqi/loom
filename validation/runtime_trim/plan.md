# M05: long-output trim, complete original source, M03 joint trajectory

Preparation mirrors `validation/runtime_recovery` / `validation/runtime_continuation`:
prepare by default, `--execute` in a separate root Engine window, source-stability
gate, `--evidence-root` state-volume evidence. Original M05 (`design/g3/system/cases.json:M05`,
properties P11/P12) requires the complete long output AND a same-length corrupted
source; contract `design/g3/system/contract.md:29` additionally requires the M03
joint trajectory. Each high-risk boundary runs under control three times.

## Grounded observable surfaces (from real batch z evidence, m01-real-2026-09-14z)

- Harness compaction settings appear in the S journal `pi.op.state.settings.compaction`
  (batch z shows `enabled:false` with 1024/1024 defaults; the m01-output-budget
  amendment's `capability_limits.archive` dict is the intended knob).
- The S journal is the Pi v4 JSONL read by `validation/components/s/oracle.py:pi_jsonl`;
  namespaces `pi.op.state`, `pi.pending.tool_output`, `pi.result`, `lore.s.binding`,
  `lore.s.boundary` are the existing readers.
- Archived payload lands in the workspace F-view (the archive budget
  `archive_bytes=8388608` in tool budgets; F identity/integrity machinery from
  `lore_files` is the corruption-rejection surface).

## Preregistered criteria (never relaxed during execution)

1. **Head/tail view and original version hash**: a chain whose fixed response is a
   long output above the fire-at threshold triggers exactly one threshold archive;
   the journal records the archive with the original version hash; the subsequent
   view keeps the head and tail segments and replaces the middle with the archive
   reference.
2. **Authorized full retrieval and corrupted rejection**: the archived original is
   retrieved complete through the ordinary F mechanism with its recorded version
   hash; a same-length corrupted variant of the source is rejected by the existing
   F identity check (negative case, three repeats of its own).
3. **M03 joint trajectory** (contract.md:29): the tool external effect happens, its
   receipt is cut at the M03 `tool` boundary, R keeps the original execution ID and
   unknown-reconciliation responsibility, the long feedback is trimmed, all old
   environments are released (404 as in M04), a new environment queries by the
   original ID or pauses with evidence: the external effect count is still exactly
   1 and the pending responsibility is not lost to the trimmed text or a read
   reference.

Zero real models (fixed HTTP), zero extra provider/tool calls beyond the counted
original ones, one sequential original slot, the original 180-second finite envelope,
first failure stops and marks the rest NOT_RUN.

## Honest unknowns before implementation

- Whether `capability_limits.archive` actually reaches the harness compaction
  settings as `enabled:true` must be proven by one real chain before the criteria
  are executed; if the knob does not reach the harness, that is a real missing
  prerequisite to report and fix at the source, not a reason to fake the view.
- The exact journal shape of the fired archive (namespace/key) is pinned from the
  proving chain and recorded here before `--execute`.
