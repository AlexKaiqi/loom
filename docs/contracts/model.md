# Model component contract

`services/model/worker.mjs` is a separately installed Node 24 process. Pi owns provider encoding/decoding and the active local model/tool loop. The component does not own Work state, durable admission, host authorization, scheduling, Sandbox resources or credentials on disk.

The locked runtime dependencies are `@earendil-works/pi-ai@0.85.1`, `@earendil-works/pi-agent-core@0.85.1` and `vscode-jsonrpc@9.0.2`. Pi native `Context`, `Model`, `AssistantMessage`, tool schemas and usage data cross the boundary without a Loom transcript translation.

## Transport and credentials

Protocol v1 uses JSON-RPC 2.0 over stdio with Content-Length framing. One worker belongs to one client context; stdout contains only RPC. The API key is supplied in private request bytes, never argv, persistent files, model metadata or tool arguments. The worker inherits only allowlisted operational environment values. Retries are always disabled.

The Go Runtime resolves the Work's `[model] service` through host `[models.<service-id>]`, which supplies explicit worker argv, endpoint, credential environment reference and optional `headers_env`. Work owns the fixed native `[model.definition]` semantics. Missing service, credential or executable rejects before provider dispatch; no repository path or Python interpreter is inferred.

## Portable model requirements

Runtime requires any policy-selected model to match the Work's declared model identity, capabilities and compatibility options. Only transport fields `baseUrl` and `headers` are excluded from this semantic comparison. Harness policy can continue to change native context and request options. Before each new dispatch, Runtime supplies transport fields from the current explicitly named host service. A checkpoint's former `baseUrl` remains audit data, and saved headers cannot authorize a request on another host.

This is Runtime's Work binding rule; the independent Pi worker continues to accept its native model APIs and protocol. Prepared request artifacts retain the actual native model/endpoint and public options, while excluding keys and secret headers.

## Methods

- `model.complete` accepts protocol version, native Pi context/model, API key, timeout and provider options, and returns a native `AssistantMessage`.
- `agent.run` additionally accepts native tool declarations and a positive `maxTurns`. It invokes Pi's continuation loop with sequential tool execution and no internal persistence.
- Tools call host `tool.execute({toolCallId,name,arguments})` and receive native `{content,details,terminate?}`.
- Stable `agent.event` boundaries are awaited so the host can persist messages/results before progression.
- Immediately before every actual provider dispatch, `model_request` supplies the prepared native model, context and public options; it excludes keys, secret headers, environment overrides and executable callbacks.
- `turn_checkpoint` supplies the complete native turn before budget/policy stopping. Optional `agent.shouldStop` and `agent.prepareTurn` express Harness policy; there is no controller-owned duplicate loop.

Unknown methods, APIs and invalid limits reject before provider dispatch. Error, aborted, truncated and length outcomes retain their native meaning and are not final success. `maxTurns` prevents another model call after the bound; a final turn's already-requested tools may finish. Timeout/cancellation/process loss may occur after provider acceptance and therefore remains an unknown external effect with no implicit retry.

## Independent component criteria

| ID | Required observation |
| --- | --- |
| M01 | The real Pi OpenAI adapter sends native text/image/tool input to a controlled HTTP/SSE peer and preserves thinking, text, fragmented tool arguments, usage and finish reason. |
| M02 | A second native provider API completes through the same RPC peer, showing that Loom does not own provider codecs. |
| M03 | 429/500 yields exactly one HTTP request and native error; unsupported API rejects with zero requests. |
| M04 | Truncated SSE and length results are not promoted or replayed. |
| M05 | Hanging requests honor deadline/cancellation and the owned worker exits on client close, with one provider request at most. |
| M06 | Pi performs model → host tool → model with the expected native transcript; rejected/unknown tool outcome stops further work. |
| M07 | Prepared request custody precedes provider dispatch, assistant custody precedes tools, invalid/truncated tool calls never execute and turn bounds prevent extra model calls. |
| M08 | Synthetic secrets are absent from argv, inherited environment and repository outputs; unknown native metadata is not silently rewritten. |

Controlled provider fixtures prove the component protocol only. They do not prove live-provider availability, Sandbox isolation or whole-system recovery.
