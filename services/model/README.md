# Pi model and local-loop worker

This independently installed Node 24 component owns Pi provider serialization and the active model/tool loop. The Go Runtime is its JSON-RPC client. The worker has no Work database, credential store, shell executor, Sandbox manager or durable scheduler.

```sh
npm ci --prefix services/model
node services/model/worker.mjs
```

stdin/stdout use JSON-RPC 2.0 with Content-Length framing. `model.complete` accepts and returns native Pi data. `agent.run` uses Pi's continuation loop and requests host tools/events through callbacks whose acknowledgements let Runtime establish durable custody. The full wire and failure contract is [docs/contracts/model.md](../../docs/contracts/model.md).

Install the worker independently and resolve its absolute argv through the host deployment configuration. The Go executable does not embed npm dependencies or assume a repository-relative worker path.

The caller supplies an API key through the private request pipe. Do not place it in model metadata, context, tool arguments, argv or inherited environment. Provider retries are disabled. Timeout, cancellation or worker loss may happen after provider acceptance, so the host must not blindly repeat an unconfirmed request.

## Dependency provenance

- `@earendil-works/pi-ai@0.85.1` and `@earendil-works/pi-agent-core@0.85.1`, MIT; exact packages and transitive integrity are in `package-lock.json`.
- `vscode-jsonrpc@9.0.2`, MIT. Go uses `sourcegraph/jsonrpc2@0.2.1`; the independent Python peer uses `python-lsp-jsonrpc==1.1.2`.

```sh
python -m unittest discover -s tests/model -v
```

These tests use installed Pi code against controlled HTTP/SSE provider peers. They verify component mapping, ordering and failure handling, not paid-provider availability or whole-system Sandbox/recovery behavior.
