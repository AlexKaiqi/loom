# External Harness protocol

A Harness is a fixed directory copied into a Work. `manifest.json` declares `protocol: 1`, command argv, accepted event JSON Schemas and native Pi tool declarations with their Runtime capability binding. The Work stores a digest of every Harness file; mutation invalidates the Work.

`{harness}` is the only command-argv expansion. The executable is explicitly deployed; Runtime does not assume an interpreter or import Harness modules. The process uses JSON-RPC 2.0 with Content-Length framing over owned stdio and a minimal environment. A Harness is trusted application policy, not the sandbox for untrusted model commands.

## Methods

| Method | Input | Output |
| --- | --- | --- |
| `policy.admit` | kind, payload, authenticated source | admit or reject |
| `policy.start` | captured facts, Surface view, timestamp | native Pi context, model choice within the Work declaration, max turns and timeout |
| `policy.continue` | native Pi turn | whether the Harness requires another turn |
| `policy.prepare` | native Pi turn | optional native context/thinking update and an equivalent declared model; Runtime rebinds host transport |

Runtime binds declared tools such as `sandbox.shell` to authorized capabilities. The Harness chooses names, descriptions and parameter schemas but cannot select an ungranted directory, change the Work's model semantics, inject host credentials or cause a local-shell fallback. A model value carried in a plan/checkpoint must equal the portable declaration after host-only endpoint/headers are removed; each new dispatch receives the current host transport. Runtime owns durable model/tool custody; the Harness owns business prompts and continuation interpretation.

A model-turn budget ending while the Harness still requires progress produces a confirmed paused Round when all prior effects are known. It is not a generic business completion. The included `harnesses/kernel` is one Python example; any language may implement the same protocol.
