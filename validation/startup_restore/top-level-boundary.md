# Startup restore: loading originals versus authorizing new actions

The earlier SR02 proposal is sufficient for a completed installation, but its “confirmed R/F install before accepting a changed live root” condition must apply to new action eligibility, not to loading the saved owner or querying the original request. Treating it as an assemble-wide gate would block M03 at exactly the required loss-of-ack cut. This corrects the earlier proposal's ambiguous scope; no source or earlier evidence is overwritten.

## Original obligation and actual code

- v5 §7.2, lines 332–336: keep confirmed versions/results/identities/responsibility; when an operation may have happened but its reply is lost, query that original identity first, or explicitly pause without replay.
- G1 top-level contracts §4, lines 48–68: original accepted responsibility and non-repeatable effects survive; unknown is not permission to recompute. §6 lines 88–96: an unknown writer blocks a new writer for that resource, not access to every saved fact.
- System M03 explicitly includes installation receipt cuts; M04 requires fresh-instance original-result queries with zero additional provider/tool calls. The current fully-confirmed SR02 proves only a narrower prerequisite.
- entry-contract.md explicitly says query reads original R schema2 requests/decisions/waits/holders/releases/installations, never S.drive, capture or a new effect. drive_until is the distinct effectful entry.
- Runtime.query delegates to RuntimeFlow.query. The latter authorizes the namespace and uses an R read transaction; it does not resolve live paths, query F, dispatch X, call a model or reconcile an installation.
- R._current_resource deliberately returns pending_reconcile while an installation lacks confirmation, then checks actual path/dev/ino. It remains correct for operations requiring current resource eligibility. HostFiles._resource reads the authorized original registration without a current-directory check; _binding additionally checks the live identity. These are already distinct scopes.
- F.query_install distinguishes not_installed, installed_pending_confirmation, conflicting and unknown from actual original layout/content. It does not itself exchange files or write R confirmation. R.confirm_install is a distinct mutation. FilePublication.publish can perform confirmation/release and therefore is not a query implementation.

## Required split

| Actual condition | Load saved host/initial refs and query original R ID | New capture / writer / execution |
| --- | --- | --- |
| Original directory still unchanged | Yes, validate saved source records | Existing R/F/X checks still apply |
| Original F/R installation fully confirmed | Yes; initial refs retain historical meaning | Validate current R revision/root and original F/X bindings |
| F exchange happened, F or R reply/confirmation missing | Yes; expose original holder/installation/issued facts without inventing completion | Deny or leave pending until explicit original-ID reconciliation establishes the existing release/installation barrier |
| Live directory missing/replaced/conflicting, durable original records intact | Original R query still works; report the actual known unknown/conflict without re-capture | No new permission from the stale initial grant or matching pathname |
| Saved host/config/original F records missing or corrupt | Explicit original-source error; never regenerate from current mutable files | No fallback grant/reset. A separate direct R-owner read remains a lower-level diagnostic, not a fabricated complete Runtime recovery |

Loading saved originals does not acknowledge an operation, confirm a replacement or release a holder. Returned initial_refs stay initial refs. Current accepted invocation input/ref selection remains its original R/E/F/S binding. A catalog of current files is neither necessary for raw R query nor an authority to change those references.

## Smallest interface suggestion

Keep the original first-start `StartupAssets(root, config)` behavior and SA02's no-R replacement rejection. Add one trusted host entry, for example:

    StartupAssets.open_existing(root, config, *, control) -> StartupAssets

The existing object can retain the public `build(files)` shape, with reentry selecting read-only reconstruction from original F records rather than calling _capture. The in-memory distinction is construction intent, not a durable business state or new ledger. `control` is the already constructed actual ControlStore from bootstrap, not caller-supplied allow maps or resource snapshots.

The reentry path checks exact startup-inputs/config equality, fixed host paths/namespace/principal/trusted roots and actual original R read authority, then loads the saved host and exact original complete F capture results by their existing deterministic request IDs. It validates original request/provenance/Git bundle and descriptors. It must not stat/recapture today's Surface/Workspace as a prerequisite for returning those historical references; it must not rewrite host.json, register revision1, create new capture identities, call F.install or R.confirm_install/release. Existing immutable dependency/code/authority originals are read and verified, not re-registered as new facts. Missing original capture or descriptor records fail explicitly rather than silently switching to first-start.

Bootstrap already constructs ControlStore before StartupAssets. It may select this entry only when opening the original saved owner/config, before wiring HostFiles and the other existing shared owners. No new serialized recovery catalog or model-visible mode is needed. The original .register callable remains available to later explicitly authorized owner transitions; build/reentry does not invoke it to manufacture acknowledgments.

After loading, `rt.query` retains its existing raw R read path and does not require Runtime.open/NATS. Shared owner construction may perform its existing lock/capability checks; this is not a new guarantee of offline Engine-independent full Runtime assembly. New drive/capture/execution still passes existing R.resolve/holder/F/X checks. A later explicit same-ID reconcile may finish F query→R confirm→release under the original receipts; query must never call it. Merely accepting a new R responsibility is also distinct from granting execution and is left to the existing R acceptance contract.

## Consequence for the next finite check

Do not mutate SR02 to count an unknown installation as confirmed. Preserve its completed-install positive. The next required M03 cut should instead prove saved-owner load + original raw query while R installation confirmation is absent, with the old holder retained and zero new capture/register/model/tool/exchange/confirm/release. The separate explicit recovery action must then prove its original-ID physical and authority chain. This note does not add an implementation, a test platform, a new retry state machine, or a current M03/M04 PASS.
