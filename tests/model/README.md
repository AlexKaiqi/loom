# Independent Pi worker tests

These tests drive the public JSON-RPC protocol with native Pi messages and controlled provider HTTP/SSE responses. `rpc_client.py` is a test-only peer using `python-lsp-jsonrpc`; it is not a production Runtime package. Runtime durable custody and composition have separate Go/black-box checks.

From the repository root, after installing the locked npm dependencies and test-only Python requirements:

```sh
python -m unittest discover -s tests/model -v
```

The cases cover provider schemas, native message/image/tool mapping, disabled retries, truncation/length, deadlines, cancellation, worker loss after dispatch, callback custody and ordering, turn budgets, unknown outcomes and credential isolation. The controlled provider is an independent oracle for request count and wire ordering; it is not live-provider compatibility evidence.
