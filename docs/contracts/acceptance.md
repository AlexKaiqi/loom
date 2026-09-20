# Independent acceptance contract

Acceptance starts from `SPEC.md` and the current component contracts. Tests execute production boundaries and derive expected values from independent fixture bytes, raw SQLite/file/protocol observations and the execution environment—not from the implementation's status output. A fresh run must identify the exact source, dependencies and environment it covers.

| ID | Required system observation |
| --- | --- |
| G01 | Build and run the real Go CLI without a Python Runtime. A non-Python Harness can complete the same protocol path; Pi, JSON-RPC and official OpenSandbox are reused rather than reimplemented. |
| G02 | Concurrent identical admission creates exactly one immutable event/receipt/pending tuple; changed content conflicts; a forced transaction failure leaves all three absent; committed pending work survives restart. |
| G03 | Concurrent run/resume has one winner. Durable model/tool intent precedes external request, result custody precedes dependent dispatch, and kill/timeout/lost acknowledgement causes no automatic redispatch. |
| G04 | Real Pi against controlled provider HTTP/SSE reaches a confirmed native continuation; explicit resume sends only the next model request, retains the same Round, repeats no old tool and survives a local pre-dispatch failure. Unknown effects produce zero new calls. |
| G05 | Official OpenSandbox executes Surface and Userspace in separate real environments, enforces the accepted profile, round-trips exact files, preserves complete artifacts and confirms release. Missing service/configuration fails closed and unknown acceptance is not retried. |
| G06 | A newly created format-3 Work has the declared roots plus `.loom`; additional ordinary user files are retained, while declaration/Harness tampering and unsupported formats reject. Host registration/grants bind physical identity, reject overlap/replacement, and are not conveyed by copy/import. Relay requires explicit sender→receiver authority and receiver admission. |
| G07 | Export/import preserves pending work, committed WAL state, Git actual bytes, artifacts, dependency snapshots and a confirmed paused continuation. Archive/path/digest/database/Git corruption rejects. The destination begins unauthorized; matching Userspace/service resolution is explicit, and old effects retain their original destination binding. |
| G08 | In an explicitly authorized live-model/live-Sandbox scenario, independent observers confirm the expected task files, Surface version, native model usage, effect identities, pending consumption and remote release. One live sample proves only that bounded scenario, not arbitrary recovery or scale. |

## Required negative coverage

- transaction cut points, multi-process races, immutable-event attempts and pending-boundary races;
- unknown model and Sandbox outcomes, response loss, worker death, cancellation and repeated run/resume;
- invalid schemas/tool arguments, truncated provider streams, budget boundaries and credential canaries;
- path traversal, escaping link chains, special files, Git conversion/ignored bytes, concurrent publication and physical root replacement;
- missing/mismatched named services, endpoint drift for saved remote IDs, absent Userspace, declaration drift and archive corruption;
- real sandbox identity, mounts, capabilities, network denial, descendant cessation, log-retention boundary and lifecycle deletion.

## Evidence rules

Component checks precede their integration use, and component success cannot stand in for a system observation. Controlled provider/service peers establish request count and protocol behavior only; real isolation needs real environment observation. A skip is not a pass. Failure output must remain available for the active investigation but does not belong in the source tree; final conclusions reference fresh external run output tied to the tested source.

An independent reviewer reruns representative core checks and inspects the underlying database, files, HTTP requests and remote resources. Role separation in one writable workspace is useful but is not a security boundary.
