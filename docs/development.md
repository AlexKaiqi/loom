# Development and reconstruction

These commands build and check the current implementation. See [Target architecture](architecture-target.md) for the accepted design and outstanding work. Existing Kernel checks cover its automatic archive behavior; they do not validate model-controlled visibility, persistent Surface templates or arbitrary recorded-state recovery.

## Prerequisites

- Unix host: macOS or Linux
- Go 1.24 or newer
- Node.js 24 and npm
- Git CLI
- Python 3.10+ for the bundled Harness and independent test drivers
- Linux container runtime for a real OpenSandbox deployment

Locked production dependencies are reconstructed from `runtime/go.mod`, `runtime/go.sum`, `services/model/package-lock.json` and `harnesses/kernel/requirements.txt`. Important direct dependencies are Pi AI/agent core 0.85.1, vscode-jsonrpc 9.0.2, sourcegraph/jsonrpc2 0.2.1, modernc SQLite 1.36.3, jsonschema/v6 6.0.2, Cobra 1.9.1, go-toml/v2 2.2.4 and the OpenSandbox Go SDK revision in `runtime/go.mod`. Server/image identities are in `deploy/opensandbox/versions.json`; license/source information is in `THIRD_PARTY.md`.

## Install and everyday use

```sh
./install.sh
export PATH="$HOME/.local/bin:$PATH"
loom setup
loom new ~/works/demo --userspace ~/projects/demo
cd ~/works/demo
loom ask "Read the task files, make a plan and write a report."
loom status
```

The task-files directory must already exist. The Work is a separate new directory. `setup` uses Pi's native model catalog for directly supported API-key deployments, asks for the independently managed OpenSandbox endpoint, and reads secret keys with terminal echo disabled. It writes private key files and configuration under `~/.config/loom/`; it performs no provider call and does not provision Sandbox infrastructure. See [OpenSandbox deployment](../deploy/opensandbox/README.md). OAuth, cloud identity and provider-specific headers require explicit advanced host configuration.

The installer builds an isolated release under `~/.local/share/loom/releases/`, with a Go binary, Node dependencies and Python venv. It publishes a `current` symlink only after the complete release passes installation checks. The launcher `~/.local/bin/loom` selects the installed components automatically; manual venv activation is unnecessary. `./install.sh --prefix "/path/with spaces/loom"` places the launcher at that prefix's `bin/loom`; `--bin-dir` overrides that location. Reinstalling preserves configuration and old releases; a failed build leaves the prior installation active. Existing Work keeps its fixed Harness and model declaration.

`ask [PATH] TEXT` admits a durable `work.message`, prints its request ID before execution, and runs pending work when no Round is already running or paused. PATH defaults to the current directory. To retry the same input, retain its text and `--request-id ID`; a changed payload with the same ID is rejected, and a completed request is not dispatched again. A newly admitted message during an active/paused Round is reported as queued. `run`, `resume`, `status` and `events` also default to the current directory. Use `resume` only for a confirmed native continuation and `run` for new pending work. No command automatically replays an unknown effect.

The bundled Kernel seeds ordinary `surface/plan.md`, `report.md` and `notes.md`. Plan projects the current and next unchecked steps and instructs the model to record evidence; it is not independent stage acceptance. Archive persists complete native context under `surface/archive/` before reducing subsequent requests to references plus recent complete tool exchanges. It does not create a lossy summary. See the [Kernel contract](contracts/kernel-harness.md) and [usage contract](contracts/usage.md).

## Advanced configuration and component builds

Unattended setup uses credential references, never key values in arguments:

```sh
loom setup --provider openai --model gpt-4o-mini \
  --sandbox-endpoint https://sandbox.example.test \
  --model-key-env LOOM_MODEL_API_KEY --sandbox-key-env LOOM_SANDBOX_API_KEY
```

`--model-key-file` and `--sandbox-key-file` accept existing restricted regular files instead. `--config FILE` selects a different host configuration location; its sibling `work-default.toml` contains the portable defaults. Setup refuses to overwrite either file. For a model absent from the supported catalog, use `--model-file /private/native-model.json --model-endpoint URL`; the JSON contains native Pi semantics without `baseUrl`, `headers` or secrets. Supply any special authentication separately through host configuration.

The two configuration files serve different purposes:

- [Work declaration](../deploy/work.example.toml) fixes native Pi model semantics, named services, a digest-pinned Sandbox image/profile/resources/time limits and a logical Userspace name. `new` copies its defaults into the Work, fixing the digest. It carries no endpoints, keys, worker paths or host grants.
- [Host configuration](../deploy/config.example.toml) maps those service names to endpoints, installed worker commands and credential references. `api_key_env` and `api_key_file` are mutually exclusive. Optional model `headers_env` maps header names to environment variable names; values are loaded only in the trusted controller. The authority database defaults to `~/.local/state/loom/authority.sqlite`, overridable with `--authority FILE`.

`new --harness DIR --definition FILE` selects explicit components. The lower-level offline `create` and separate `grant`/`admit` commands remain available for integrations:

```sh
loom create /path/to/work --harness /path/to/harness \
  --definition /path/to/work-definition.toml
loom grant /path/to/work /path/to/task-files
loom admit /path/to/work work.objective.set \
  --payload /path/to/objective.json --request-id objective-1
loom run /path/to/work
```

The payload is a JSON object such as `{"text":"Read the task files and write a report."}`. A Harness without task tools can omit `[sandbox]`; one without an external task directory can omit `[userspace]`. Runtime production code uses the official remote OpenSandbox Go SDK, never direct Docker execution.

For development, build the individual components:

```sh
npm ci --prefix services/model
(cd runtime && go mod download && go build -o bin/loom ./cmd/loom)
python3 -m venv .venv
.venv/bin/pip install -r harnesses/kernel/requirements.txt -r tests/requirements.txt
export PATH="$PWD/.venv/bin:$PWD/runtime/bin:$PATH"
```

`node_modules/`, `.venv/` and `runtime/bin/` are generated locally. The lock files and source are the reconstruction inputs. Component builds discover source assets relative to `runtime/bin/loom`; no developer-machine path is compiled into the binary.

## Move a confirmed Work to another host

Export accepts a confirmed paused native Pi checkpoint once all effects are complete and remote resources released. It rejects a running Round or unknown effect. Use the consistent export command rather than copying files during active writes:

```sh
# Source host; do not keep advancing this copy after handing it over.
loom export /path/to/work /path/to/work.tar

# Destination host, with its own authority database and named service config.
loom import /path/to/work.tar /new/path/to/work
loom register /new/path/to/work
loom restore-userspace /new/path/to/work /new/path/to/task-files
loom grant /new/path/to/work /new/path/to/task-files
loom resume /new/path/to/work
```

The import and Userspace destination must not already exist. Import grants no authority; registration is required before the CLI's restore operation, and restoration itself does not grant task access. Userspace restoration reads the captured archive in Work and does not require the original directory. An existing replacement directory can instead be granted only when its captured content identity matches. Omit restore/grant for a Work without a Userspace dependency. Use `resume` for a confirmed paused Round; use `run` for newly pending work with no such continuation.

Resume retains the same Round and native context without repeating completed tools. The new host supplies the same declared model semantics via its explicitly named transport. An old checkpoint's model endpoint is audit information. In contrast, querying an existing remote Sandbox effect requires its original concrete endpoint: `loom query-remote WORK ROUND_ID EFFECT_ID` rejects a host mapping that points elsewhere. Host grants, credentials and remote resources are never transported as authority. These commands do not coordinate two concurrent owners or reconcile unknown effects.

## Checks

```sh
(cd runtime && go test -race ./...)
.venv/bin/python -m unittest discover -s tests/model -v
.venv/bin/python -m unittest discover -s tests/harness -v
python3 -m unittest discover -s tests/install -v
.venv/bin/python tests/go_acceptance/run_frozen.py --output /tmp/loom-acceptance
```

Real service tests are opt-in because they require operator-owned credentials and infrastructure. Always use a fresh output directory outside the source tree. A skip, fixture-only pass or stale output is not evidence for a real-service property.

The frozen acceptance runner snapshots the current source/contracts and excludes generated dependencies, binaries and result directories. If contracts or source change after the snapshot, rerun against the changed tree.
