# Loom architecture

## Components

| Component | Current implementation | Owns |
| --- | --- | --- |
| Control Runtime | `runtime/cmd/loom`, `runtime/controller` | admission, authorized dispatch, durable custody and Round completion |
| Event/control store | `runtime/store`, SQLite | immutable facts, request receipts, pending responsibility, Rounds and effects |
| Work and authority | `runtime/work`, `runtime/authority`, `runtime/filesystem` | portable Work content/versions versus host-local physical grants |
| Model component | `services/model`, Node 24 + Pi | provider codecs and the active local model/tool loop |
| Harness | any protocol-v1 executable; example in `harnesses/kernel` | projection, prompts, tools and continuation policy |
| Sandbox | remote OpenSandbox; client in `runtime/sandbox` | isolated environment lifecycle, remote commands and file handoff |

```mermaid
flowchart LR
  CLI[Host CLI] --> Runtime[Go Runtime]
  Runtime --> Store[SQLite state]
  Runtime --> Work[Work files and Git versions]
  Runtime <-->|JSON-RPC stdio| Harness[External Harness]
  Runtime <-->|JSON-RPC stdio| Pi[Node Pi worker]
  Runtime -->|Official Go SDK / HTTP(S)| Sandbox[OpenSandbox]
```

Harness and the model worker are separately installed programs launched through private local pipes. Sandbox is a remote service boundary even when deployed on the same host for development. Store, Work and authority are separate Go responsibilities inside one binary; a component boundary does not require an extra network service.

## Control flow and custody

1. Runtime atomically admits an authenticated event, its request receipt and pending responsibility.
2. One Runtime owner claims a Round with a fixed input boundary. The fixed Harness builds the native Pi plan.
3. Runtime calls one bounded `agent.run`; Pi owns provider serialization and model/tool iteration. Before every provider dispatch, Runtime persists the prepared native request and acknowledges it only after durable custody.
4. Pi requests declared tools back through the host. Runtime persists an effect identity and destination before dispatching a remote operation. Sandbox runs either the Surface or Userspace domain; there is no host-shell fallback.
5. Native model/tool results and continuation checkpoints are persisted before acknowledgement. Unknown transport or execution outcomes pause progression and are never automatically replayed.
6. A completed Round snapshots exact Surface bytes into the Work Git repository and consumes only its captured pending boundary. A confirmed budget pause retains the same Round and exact native continuation for explicit resume.

## Work and host state

```text
work/
  work.toml                  fixed, non-secret service/model/environment requirements
  harness/                   fixed external policy
  surface/                   ordinary human/model content
  .loom/
    identity.json            format 3, identity and fixed-content digests
    state.sqlite             events, pending, Rounds, effects and checkpoints
    versions.git/            exact Surface versions
    artifacts/               model/tool inputs, outputs and native receipts
    dependencies/            external Userspace revisions and snapshot references
```

The Work directory contains all portable responsibility: local content, fixed policy and requirements, facts, pending work, confirmed continuation, versions, native observations and reconstructible Userspace snapshots. Host registration, physical path identities, Userspace grants, service routing configuration and credentials remain outside it. Actual non-secret destinations used by past effects are retained inside Work for audit and recovery. Hiding `.loom/` organizes the directory; real authorization and execution isolation protect it.

`surface/` is the Work Surface itself; it is not required to contain `surface.md`, `blocks/`, a Git checkout or any other strategy-specific shape. An external Userspace remains a separate authorized directory. Only the selected domain is transferred to a fresh remote sandbox.

The initial Userspace grant captures its bytes in Work. A fresh run can capture intentional changes to an already granted directory; confirmed resume requires the recorded version. Successful remote publication updates the snapshot and physical grant. Importing the Work on another host preserves the snapshot but no authority. `register`, `restore-userspace` into a nonexistent destination, and `grant` are explicit separate steps. Snapshot restoration verifies content, paths, links and modes without the original Userspace directory.

Export uses a SQLite write barrier and includes the portable files. It accepts completed/inactive work and a confirmed paused native Pi checkpoint whose effects are complete and remote resources released. Running or unknown-effect state remains non-exportable. After import and new host setup, `resume` continues the same Round and native context with new effect IDs. Copying does not coordinate ownership of two live copies; it is not distributed automatic takeover.

## Portable requirements and host bindings

`work.toml` declares `[model] service`, native `[model.definition]` semantics, optional `[sandbox]` service/image/profile/resource/time requirements and optional `[userspace] name`. Creation requires an explicit definition file and fixes its digest together with the Harness. Editing either in an existing Work is rejected. There are no host defaults that silently supply another model or environment.

Host TOML resolves `[models.<name>]` to an endpoint, worker argv and credential environment references; `[sandboxes.<name>]` supplies an endpoint and credential reference. A new host can install equivalent services under the declared names. New model dispatches use the Work's declared semantics and the current named host transport. A checkpoint's previous `baseUrl` remains audit data; policy may prepare context and options but cannot switch to an undeclared model. The Pi worker's native protocol remains independent of this Runtime rule.

Before the first Sandbox HTTP request, Runtime persists a `planned` receipt with logical service ID, concrete endpoint, pinned image, profile, CPU, memory and time limits. Later checkpoints add native sandbox/execution IDs without losing that binding. Query resolves the saved service and rejects an endpoint mismatch before network access, so an old execution ID cannot be sent to another host's default service. Keys and secret headers never enter these bindings.

## Dependency direction

`store` has no model, policy, sandbox or network dependency. `filesystem` provides pure content archiving and verification. `work` uses store/filesystem and Git; `authority` binds a Work to host physical identities. `controller` composes those packages with protocol clients. Provider codecs, the agent loop and the execution engine stay in their owning external components.

Current protocol details are in `docs/contracts/`; deployment and validation commands are in `docs/development.md`.
