# Control Runtime contract

The Runtime is a standalone Go program. It owns durable admission, host authorization, Work custody and orchestration; it does not implement provider codecs, a model/tool loop, Harness policy or a Sandbox engine.

## Public boundary

The CLI exposes explicit operations for creating/registering a Work, granting Userspace, admitting and relaying events, running/resuming a Round, reading status/events, querying saved remote effects, exporting/importing Work and granting cross-Work relay. Commands produce JSON on success and a nonzero exit on rejection. Host authority and deployment configuration paths are explicit global inputs.

Python may be a Harness language or an independent test driver, but it is not a Runtime dependency. Model and Harness processes use JSON-RPC 2.0 with Content-Length framing over owned stdio. Remote execution uses the official OpenSandbox Go SDK over HTTP(S).

## Admission and facts

- `admit(source, request_id, kind, payload)` saves the immutable event, unique request receipt and pending row in one SQLite transaction.
- Repeating the same source/request/content returns the original event. Reusing the identity for different content conflicts without mutation.
- Events cannot be updated or deleted through the state database. A committed pending event remains enumerable after process restart without an in-memory notification.
- A Harness validates the receiver's event schema/policy before admission. Callers cannot self-assert a privileged source; cross-Work source identity comes from Runtime authority.

## Rounds and effects

- A Work has at most one running or paused Round. Claim and host grant changes serialize through the authority boundary; there is no time-based or lease-expiry takeover.
- A Round captures an input sequence. Completion consumes only pending events at or below that boundary, so later input remains pending.
- Every model or tool dispatch has a durable, unique effect intent and request digest before dispatch. Same identity/different content conflicts; completed results are reused; intent/unknown effects are never automatically replayed.
- Local failure may reject a Round only before its first effect intent. After any possible external effect, failure pauses or marks the effect unknown and retains responsibility.
- A confirmed budget pause contains the exact native Pi continuation, prior results and plan. Explicit resume atomically reclaims the same Round and creates only new effect identities. Missing checkpoints, unknown effects or unreleased remote resources reject resume.
- Process termination sends protocol cancellation and reaps owned workers, but cancellation does not prove a provider or remote command had no effect.

## Model and Harness custody

Runtime calls one bounded Pi `agent.run` for a Round. Pi owns provider serialization, preparation and sequential model/tool progression. The Harness owns projection, tool declarations and continue/prepare decisions.

Before acknowledging each `model_request`, Runtime stores the actual prepared native model/context/options without credentials. It stores a terminal native assistant result before acknowledging it or dispatching its tool calls. Tool intent and any native remote checkpoint are durable before tool acknowledgement. Malformed, truncated, error, aborted, length, pending or deferred model output is not promoted to a successful business result.

The Harness is a fixed external executable. Runtime expands only the documented Harness path placeholder, passes a minimal environment and never imports Harness code. Runtime does not add a second model loop or reinterpret provider-native messages as a private transcript format.

## Authority and relay

Host authority is stored outside Work. Registration and grants bind canonical paths plus Unix physical identity and reject path aliases, overlapping roots, physical replacement and authority storage inside an authorized root. Copying, importing or restoring a Work never creates authority.

Cross-Work relay requires both Works to be registered, an explicit sender→receiver host grant and receiver admission. Runtime supplies the authenticated sender identity; the payload cannot forge it.

## Completion and failure

A Round completes only after all effects have known results, required artifacts and checkpoints are durable, remote resources are confirmed released, publication is conflict-free and exact Surface bytes are versioned. Public errors must not disclose credentials; transport failures are normalized rather than returning captured protocol bodies. Status and query operations are read-only and never redispatch an effect.

Work format, export/import and content rules are in `work.md`; model, Harness and Sandbox wire boundaries are in their respective contracts.
