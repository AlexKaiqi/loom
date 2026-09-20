# Portable Work contract

Work format 3 is the portable unit of durable responsibility. It is the only accepted layout; the product contains no compatibility decoder.

## Shape

```text
work/
  work.toml
  harness/
  surface/
  .loom/
    identity.json
    state.sqlite
    versions.git/
    artifacts/
    dependencies/
```

`work.toml`, `harness/` and `surface/` are the readable product surface. `.loom/` contains machine-owned state; hiding it is presentation, not an access-control mechanism. Only `surface/` is the Work's model-editable content. Its internal files and conventions belong to the Harness.

`identity.json` records format 3, a stable Work ID, the fixed Harness digest and the declaration digest. Changing `work.toml` or Harness bytes invalidates the Work instead of silently changing an active responsibility. Every boundary path is a real directory/file of the expected type; symbolic redirection of Work control paths is rejected.

## Portable declaration and host resolution

`work.toml` declares:

- `[model] service` and `[model.definition]`: the complete non-secret native Pi model semantics needed by the Work;
- optional `[sandbox]`: logical service, digest-pinned image, profile, CPU, memory, lease and request timeout;
- optional `[userspace] name`: the logical external dependency.

Worker argv, endpoints, credential names/values, transport headers and physical grants are host deployment data and cannot appear as portable model fields. Unknown declaration fields reject. The host resolves an explicit logical service; it may not supply a missing model meaning, silently switch a service for an existing effect or use a default destination for an old native ID.

Creation is offline: it validates the explicit definition and fixed Harness, creates the format-3 tree, initializes SQLite and the bare version repository, and captures an initial Surface version. Opening revalidates layout, formats, digests, database version and safe Git configuration.

The Harness manifest may declare `initial_surface`, a relative real directory inside its fixed content. Creation copies those ordinary bytes to Surface before the initial version capture. Missing, absolute, traversing, linked or non-directory seed paths reject before creating a Work. Without that declaration, the initial Surface is empty; Runtime does not impose Kernel filenames or layout.

## Surface versions and artifacts

Surface snapshots retain actual bytes, including ignored files, binary data and content affected by `.gitattributes`. Capture force-adds all ordinary files while fixed repository attributes disable text, filter, ident and working-tree-encoding conversions. Nested repositories, special files, unsafe Git configuration, hooks and object alternates reject.

Model requests/results, tool inputs/outputs, remote checkpoints and transfer archives are stored under `.loom/artifacts/` with content digests and are fsynced before dependent acknowledgement. Standalone artifacts use content-addressed names; an effect may also own a stable subdirectory containing its transfer files. Artifacts are durable continuation data, not a disposable cache.

## External Userspace dependency

Userspace remains a separately authorized directory outside Work. When declared, Work stores its logical name and a verifiable snapshot/reference under `.loom/dependencies/`, sufficient to restore the captured state without the original path or inode. Content identity covers bytes and the supported filesystem metadata needed for faithful restoration.

Granting/rebinding verifies the declared dependency rather than silently accepting different bytes. A new Round may deliberately capture authorized intervening edits; resuming a confirmed checkpoint requires the recorded version. Confirmed remote publication updates the captured dependency before the host grant is refreshed. Restoration targets a nonexistent external path and never grants it authority.

## Remote destination custody

Before a Sandbox network request, the durable effect records its logical service, canonical endpoint, image, profile, CPU, memory, lease and request timeout. Later native IDs and results retain that binding. API keys are excluded. Query, cancellation and reconciliation require the original binding; if the current host resolves the service to another endpoint, the operation rejects before network access.

## Export and import

Export holds a SQLite immediate writer guard and uses an independent consistent database snapshot. Running Rounds, unconfirmed pauses and unresolved effects reject. A confirmed paused Round with all effects known and remote resources released is portable, including its exact native continuation.

The archive contains all Work files, pending responsibility, checkpoints, Git objects, artifacts and dependency snapshots, but no host authority or credentials. Import rejects traversal, duplicate members, links or special files outside the supported shape, digest changes, unsafe Git state, corrupt SQLite and unsupported formats. It creates no registration, grant or service credential on the destination host.

After import, a host must explicitly register the new physical Work, resolve every named service, restore/provide matching Userspace and grant it before running. Continuation uses the same Round and prior results; it never repeats an old tool merely because the directory moved.
