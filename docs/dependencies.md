# Runtime dependencies

This is the observed Linux runtime configuration used during development and bounded validation. It records exact pins; it does not claim support for arbitrary versions or completed system acceptance. The repository is a source snapshot, not a bundled runtime or a self-contained installer. No model credentials, service state, dependency binaries, or container layers are included.

## Direct facilities

| Facility | Observed pin | Use and source |
| --- | --- | --- |
| CPython | `3.10.12` | Host Python runtime and standard library. [CPython](https://github.com/python/cpython/tree/v3.10.12); PSF license and incorporated notices. |
| SQLite | `3.37.2` through this host's Python `sqlite3` | `lore_control` uses the real SQLite engine for durable control records. [SQLite](https://www.sqlite.org/copyright.html), core public domain; interpreter/wrapper and distribution packaging have their own notices. No SQLite implementation is copied here. |
| Git CLI | `2.34.1` (observed Ubuntu package `1:2.34.1-1ubuntu1.11`) | `lore_files` invokes external Git for immutable versions. [Git](https://github.com/git/git/tree/v2.34.1); GPL-2.0 and file-specific terms. No Git binary or implementation is included. |
| nats-py | `2.15.0`, default package without extras | Python imports in `lore_events` and `lore_runtime.event_reader`. [nats.py](https://github.com/nats-io/nats.py); Apache-2.0. The default selected client has no required non-stdlib Python dependencies; `aiohttp`, `fast-parse`, and `nkeys` extras were not enabled. |
| NATS server / JetStream | commit `3c80d8f89eac613bdbae473efb59ec76f8d4ed09` (`2.15.0-dev` in that source) | Existing external service, [fixed source](https://github.com/nats-io/nats-server/tree/3c80d8f89eac613bdbae473efb59ec76f8d4ed09); Apache-2.0. Observed binary was built with Go `1.27.1`; it is not distributed here. |
| Docker Engine / CLI | `28.0.1`, Engine API `1.48` | External Linux execution service and CLI. [Moby](https://github.com/moby/moby/tree/v28.0.1), [Docker CLI](https://github.com/docker/cli/tree/v28.0.1); Apache-2.0 plus component notices. Docker Desktop is not bundled; the observed WSL installation used its Linux backend. |
| Python task image | `python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea` | Unmodified external [official Python image](https://github.com/docker-library/python), observed CPython `3.12.14` on Debian 13. It supplies Python, shell, and GNU tar; image packages keep their separate licenses. |
| Node.js | `24.21.0`, Linux x64 | External JavaScript runtime used in the isolated Session. [Node](https://github.com/nodejs/node/tree/v24.21.0); retain its [complete LICENSE](https://github.com/nodejs/node/blob/v24.21.0/LICENSE) when distributing Node, including embedded third-party notices. |
| Pi | `71dca871bc80b6bc97be37f0ca3189399d651fff` plus the supplied one-line patch | Original Session/Harness implementation, [upstream](https://github.com/earendil-works/pi/tree/71dca871bc80b6bc97be37f0ca3189399d651fff). See [patch provenance](../third_party/pi/UPSTREAM.json). |

The host's Python SQLite `3.37.2`, the task image's SQLite `3.46.1`, and Node's embedded SQLite `3.53.4` are different builds. Current control persistence uses Python `sqlite3`; Node's built-in `node:sqlite` is not the control-store implementation.

## Selected Pi and TypeScript runtime packages

The observed core route used the following packages, resolved from the pinned upstream checkout and lockfile. The runtime dependency projection retained exact files and four upstream workspace symlinks; it was not a mount of the entire checkout or arbitrary `node_modules`. This public snapshot does not include that projection or its binaries.

| Package | Version | License |
| --- | --- | --- |
| `@earendil-works/chord` | `0.85.1` | Pi MIT |
| `@earendil-works/pi-agent-core` | `0.85.1` | Pi MIT |
| `@earendil-works/pi-ai` | `0.85.1` | Pi MIT |
| `@earendil-works/pi-telemetry` | `0.85.1` | Pi MIT |
| `tsx` | `4.22.1` | MIT |
| `esbuild` and `@esbuild/linux-x64` | `0.28.2` | MIT; the executable also includes Go/x/sys BSD notices |
| `ignore` | `7.0.8` | MIT |
| `partial-json` | `0.1.7` | MIT |
| `typebox` | `1.3.27` | MIT |
| `yaml` | `2.9.0` | ISC |

The original [upstream package file](../third_party/pi/upstream-package.json) and [upstream lockfile](../third_party/pi/upstream-package-lock.json) are preserved unchanged. Their complete monorepo scope is larger than this selected route. They are not a claim that all locked packages are production dependencies, nor that running a new unrestricted install reproduces the validated projection. Do not replace these pins with `latest` while claiming the same validated configuration.

The selected esbuild executable contained Go `1.26.5` and `golang.org/x/sys v0.0.0-20220715151400-c0bba94af5f8`. If bundling that executable, preserve esbuild's MIT notice plus the matching Go/x/sys copyright, BSD conditions, and disclaimers. If bundling Node, preserve the entire Node license file rather than just its opening MIT section. Normal external installation preserves upstream distributions separately from this repository.

## Scope and packaging

Production Python imports outside the standard library are the selected `nats` client. Development formatters and validation-only parsers, observers, test fixtures, and research environments are not runtime requirements merely because they were installed in the same development environment. The provider wire adapter uses host Python networking; this selected route does not add a provider SDK to Pi's runtime dependency set.

The copied Moby profile is covered by [the repository's third-party notice](../THIRD_PARTY.md). NATS server, Docker/containerd/runc, Git, CPython, host C/C++ libraries, and image contents remain external components. Their source/binary redistribution obligations must be handled if a later release actually bundles them. The current source snapshot does not assign a license to Loom's own code.
