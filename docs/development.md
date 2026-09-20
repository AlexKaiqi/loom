# Development operations

The [HTML design book](loom-design-book.html) is the sole specification. This file contains reconstruction and verification commands, not an alternate architecture or acceptance standard.

## Build individual components

Use Go 1.25+, Node 24, Git and Python 3.11+. The production dependency inputs are `runtime/go.mod`, `runtime/go.sum`, `services/model/package-lock.json` and `harnesses/kernel/requirements.lock`. The Go SQLite driver verifies the actual engine version and WAL/FULL settings when opening each database.

```sh
npm ci --prefix services/model
(cd runtime && go build -o bin/loom ./cmd/loom)
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r harnesses/kernel/requirements.lock
.venv/bin/pip install -r tests/requirements.txt
```

A native macOS build supports management and component checks. Executing Harness or Work Bash requires the configured shared Linux facility; there is no host-shell fallback. `./install.sh` builds the reference facility and routes the CLI into it. `deploy/work/Dockerfile` pins the toolchain bases and NsJail source; the final image excludes the Go build toolchain and caches.

The installer publishes `current` only after startup checks. Failed builds retain the previous installation. Reinstall with the same workspace roots. Old images/containers and persistent state are retained so an upgrade cannot silently terminate an in-flight owner or remove its staged result; inspect and fence old domains before retiring a deployment.

## Host configuration

`loom setup` reads Pi's model catalog or an explicit native model file. For unattended setup, use references to credentials rather than putting their values in argv:

```sh
loom setup --provider PROVIDER --model MODEL \
  --sandbox-endpoint https://sandbox.example.test \
  --model-key-env LOOM_MODEL_API_KEY --sandbox-key-env LOOM_SANDBOX_API_KEY
```

The installed launcher forwards only credential environment names selected by the private host configuration. Interactive setup stores private key files in the deployment's host-state directory. Advanced `--config FILE` and credential files must be accessible to the trusted controller through its configured mounts. Secrets never belong in a Work or source checkout.

[Host configuration](../deploy/config.example.toml) binds logical services and Target profiles, credentials, the locked launcher, reserved UID range and delegated cgroup. [Work defaults](../deploy/work.example.toml) carry schema 2 logical declarations. Different Targets receive independent saved copies of their declared resources. Granting a resource does not authorize a shared-project update.

## Assemble and select a Work

A directory containing valid `work.toml`, Harness files and Surface files can be assembled with ordinary `mkdir`/`cp` operations and initialized with `loom register DIRECTORY`. Registration preserves those files and creates hidden Runtime metadata once; resource grants remain separate. An incomplete or invalid existing `.loom` directory is rejected, never silently reset.

Edit the candidate Harness and `work.toml`, check them in a separate test Work, then run `loom select-harness WORK`. This selects the complete immutable definition for a subsequent Round. Saving files alone does not activate them, and a resumed Round keeps its original code, model declaration and Target requirements. An invalid candidate does not prevent inspecting committed state or recovering the prior Round. The Work Bash view includes `/facts/interface.json` with the executing Harness reference, per-role operations and generated request/tool schemas; reading it does not grant control access. Resource aliases already bound to a source retain that identity; use a new alias for a different logical resource and grant it explicitly.

## Work history and movement

```sh
loom history WORK
loom inspect WORK CHECKPOINT_ID NEW_DIRECTORY
loom fork WORK CHECKPOINT_ID NEW_WORK
loom export WORK ARCHIVE.tar.gz
loom import ARCHIVE.tar.gz NEW_WORK
loom register NEW_WORK
```

Inspect materializes immutable content without executing it. Fork retains the selected historical fact prefix and necessary bytes under a new identity; it has no inherited pending inputs, effects or physical grants. A new input starts the exploration. Export currently requires an inactive Work or a confirmed native continuation with known effects. Unknown effects stay with their original owner and destination; they cannot be cleared by export/import.

On a new host, explicitly grant each declared resource with `loom grant-resource WORK ALIAS DIRECTORY`. Original captured versions remain available even if that host's shared project has changed. To materialize a saved copy in a new directory, use `loom restore-resource WORK ALIAS DIRECTORY --target TARGET`; it neither overwrites the shared project nor grants access to the new directory.

`loom recover WORK` revokes the old epoch and fences every retained Linux execution domain before deciding whether a confirmed continuation is ready. If fencing or an external outcome is unconfirmed, the Round remains recovering/blocked. `loom query-remote WORK ROUND_ID EFFECT_ID` queries only the original saved service binding. `loom cancel-effect WORK ROUND_ID EFFECT_ID` records cancellation responsibility before requesting a stop at that binding; a stopped execution does not prove its result or files were delivered. `loom inspect-allocation WORK ROUND_ID ALLOCATION_ID` reconciles the original resource request, including a lost create receipt. `loom release-allocation WORK ROUND_ID ALLOCATION_ID` requests release only after necessary execution output and content are saved. Reconciliation never creates a replacement instance.

## Checks

```sh
(cd runtime && go test -race ./...)
.venv/bin/python -m unittest discover -s tests/model -v
.venv/bin/python -m unittest discover -s tests/harness -v
```

CLI execution checks need a real Linux facility. Inside that facility, set `LOOM_GO_BINARY` to the compiled CLI, `LOOM_TEST_CGROUP_ROOT` to its delegated cgroup, and `LOOM_GO_EVIDENCE` to a new directory outside the source tree:

```sh
python3 -m unittest discover -s tests/go_acceptance -v
```

Remote execution checks additionally require `LOOM_SANDBOX_ENDPOINT`, `LOOM_SANDBOX_KEY_FILE` and `LOOM_SANDBOX_EVIDENCE`. Use the [OpenSandbox deployment runbook](../deploy/opensandbox/README.md). `go test ./adapters/opensandbox -run TestReal -v -count=1` runs the real SDK cases when these are configured.

The isolated execution probe retains its raw result and publishes `target.ready` with the actual platform, architecture, tools, permissions, read-only mounts and original allocation/session identity. Inspect those facts and their record references when diagnosing a Target that was allocated but could not execute.

For a bounded scheduler load and restart check, run `python3 tests/go_acceptance/scale.py --binary /absolute/path/to/loom --output /tmp/loom-load` inside the configured Linux facility. Its plan fixes 32 Works, mixed Node/Python strategies, concurrency, event rate, byte volume and thresholds before dispatch. The controlled model endpoint and two-second offline interval do not establish real-provider throughput or long-duration reliability.

Keep every failed run and record its source/image/dependency identities. Rerun changed checks against the final source. A fixture pass, skipped real-service test or old evidence directory does not establish conformance. A35 additionally needs repeated real-model workloads with fixed quality/safety/budget criteria; renderer mechanism tests cannot substitute for that comparison.
