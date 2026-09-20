# Remote Sandbox contract

Sandbox is a separately deployed official OpenSandbox service. Loom selects an authorized target and owns durable effect custody; OpenSandbox owns environment lifecycle, execution identity, command status, cancellation and remote files. Runtime never runs a model-requested shell on the host and never controls Docker in production code.

The current client uses the official Go SDK revision pinned in `runtime/go.mod`; server, execd and image identities are pinned in `deploy/opensandbox/versions.json`. SDK command retries and metrics are disabled. No local SDK fork, Python proxy, custom service codec or execution engine is part of Loom.

## Configuration and API

The Work declaration and host resolver must supply an explicit logical service ID, HTTP(S) origin, key, digest-pinned image, `code` profile, CPU, memory, lease and request timeout. The lower-level `New(Config)` validates the resolved boundary and retains conservative defaults for direct component calls. The accepted code profile is network-disabled. Browser, desktop and network-enabled profiles reject until independently specified and accepted.

`Execute(ctx, Request, Checkpoint)` receives a stable operation ID, target (`surface` or `userspace`), script, deadline, authorized directory and artifact directory. Local validation, input snapshot and a synchronous durable `planned` checkpoint with the complete non-secret binding happen before the first network request. Later `created`, `prepared` and `accepted` checkpoints preserve that binding and native IDs.

`Query` and `Cancel` receive the original binding and IDs. `Release` uses the client already constructed from that binding plus the original Sandbox ID. A service or endpoint mismatch rejects before network access. A lost response never dispatches a second command. Cancellation reports the requested/deleted scope; it does not fabricate a successful command result.

## Isolation and transfer

Each operation uses a fresh strict isolated session with non-root uid/gid, zero inherited credentials, a clean environment and only the selected content tree at `/workspace/<target>`. Surface and Userspace never share an instance. An in-session preflight verifies uid/gid and socket denial before user code; real integration observers separately verify capabilities and `no_new_privs`.

The pure `runtime/filesystem` package implements standard tar handoff. It rejects escaping paths/link chains, duplicates and unsupported special files, creates ordinary content before links, and fsyncs files/directories. Runtime state, Harness, the other domain, host directories and Docker socket are never included.

Input archive and digest are durable before dispatch. Source physical identity and content are checked before transfer and again before publication. Concurrent host edits or root replacement preserve local bytes and the remote output archive, returning unknown instead of overwriting. Output/log/native artifacts are durable before release and local publication.

## Result semantics

Every post-dispatch failure returns an `unknown` result with all known binding/native IDs. Only pre-network validation/preparation failure is a local rejection. A `completed` execution requires a terminal exit code, complete available logs, durable artifacts, confirmed remote deletion and conflict-free publication. Nonzero shell exit is a completed execution, not business success.

The upstream combined background log is retained as supplied. Reaching the 16 MiB native retention boundary makes completeness unknown. Timeout or interruption attempts isolated-session deletion; independent query/observation is required to establish cessation. Lifecycle release remains usable when execd is unavailable.

## Independent component criteria

| ID | Required observation |
| --- | --- |
| S01 | Real create → isolated run → file additions/deletions → artifact capture → destroy round-trips exact bytes. |
| S02 | Surface and Userspace use distinct IDs and cannot access the other domain, host control data, mounts, sockets or credentials; actual uid/capabilities/no-new-privileges/network denial match the profile. |
| S03 | Lost/truncated response yields unknown with saved binding/IDs and zero redispatch. |
| S04 | Stable operation identity is Runtime custody; SDK memory is not the idempotency authority and transport retries are disabled. |
| S05 | Query/cancel use original binding/IDs; timeout/interrupt cessation is independently observed. |
| S06 | Success appears only after artifacts/logs and lifecycle deletion are confirmed; release failure is unknown. |
| S07 | Traversal, escaping links, duplicates, special files and invalid targets fail closed. |
| S08 | Service unavailability has no host fallback; persistence failure preserves known remote identity and stops progression. |
| S09 | Concurrent content/identity change preserves both local bytes and remote archive and never replays the command. |
| S10 | Log-retention overflow is unknown and lifecycle deletion still works after execd failure. |

Fixture tests cannot prove real isolation. Real-profile claims require an independently observed official service on the stated Linux runtime and deployment configuration.
