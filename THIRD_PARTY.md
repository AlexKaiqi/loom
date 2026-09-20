# Third-party components

Loom imports dependencies rather than vendoring their provider codecs, agent loop, execution engine, RPC or database implementation.

| Component | License | Source / identity |
| --- | --- | --- |
| Pi AI / Pi agent core 0.85.1 | MIT | https://github.com/earendil-works/pi; npm distribution integrities in `services/model/package-lock.json` |
| vscode-jsonrpc 9.0.2 | MIT | https://github.com/microsoft/vscode-languageserver-node |
| Sourcegraph jsonrpc2 0.2.1 | MIT | https://github.com/sourcegraph/jsonrpc2 |
| python-lsp-jsonrpc 1.1.2 | MIT | https://github.com/python-lsp/python-lsp-jsonrpc; external Python Harness and test observers only |
| OpenSandbox official Go SDK / server / execd | Apache-2.0 | https://github.com/alibaba/OpenSandbox; Go sums and `deploy/opensandbox/versions.json` |
| modernc SQLite binding | BSD-3-Clause | https://gitlab.com/cznic/sqlite; underlying SQLite public domain |
| jsonschema/v6 | Apache-2.0 | https://github.com/santhosh-tekuri/jsonschema |
| Cobra | Apache-2.0 | https://github.com/spf13/cobra |
| go-toml/v2 | MIT | https://github.com/pelletier/go-toml |
| golang.org/x/term | BSD-3-Clause | https://cs.opensource.google/go/x/term; terminal secret input |
| ujson 6.0.0 | BSD-3-Clause | https://github.com/ultrajson/ultrajson; locked Python JSON-RPC dependency |
| Git CLI | GPL-2.0 | https://git-scm.com; separately installed program |

Go transitive dependencies and versions are recorded in `runtime/go.mod`/`go.sum`; npm transitive dependencies are locked independently. Their distributions retain their license notices.
