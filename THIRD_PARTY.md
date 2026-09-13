# Third-party material and attribution

Loom is built around existing open-source facilities. The Session adapter uses Pi's original JSONL Session and Harness APIs; persistence uses Python's SQLite interface and Git; event delivery uses NATS; execution uses Docker Engine and an existing Python container image. These facilities are not original Loom implementations.

This public snapshot is source only. It does not include Pi implementation files, `node_modules`, Node/Python/NATS/Git/Docker binaries, container image layers, credentials, or execution evidence. Runtime dependencies must be obtained separately. Exact observed versions and the distinction between source and runtime dependencies are in [docs/dependencies.md](docs/dependencies.md).

## Material included in this repository

| Material | Origin and license | Preserved records |
| --- | --- | --- |
| `lore_execution/seccomp.json` | Unchanged Moby `v28.0.1` `profiles/seccomp/default.json`, Apache-2.0 | [LICENSE.moby](lore_execution/LICENSE.moby), [NOTICE.moby](lore_execution/NOTICE.moby), [profile attribution](lore_execution/THIRD_PARTY.md) |
| Pi patch and upstream package metadata | [earendil-works/pi](https://github.com/earendil-works/pi), commit `71dca871bc80b6bc97be37f0ca3189399d651fff`, MIT; copyright 2025 Mario Zechner | [LICENSE](third_party/pi/LICENSE), [patch](third_party/pi/compaction-enabled.patch), [source identity and hashes](third_party/pi/UPSTREAM.json), [package metadata](third_party/pi/upstream-package.json), [upstream lockfile](third_party/pi/upstream-package-lock.json) |
| NATS license text | [nats-io/nats-server](https://github.com/nats-io/nats-server) and [nats-io/nats.py](https://github.com/nats-io/nats.py), Apache-2.0 | [Original license text](third_party/nats/LICENSE); no NATS implementation or binary is vendored |

The Pi patch adds `intent.settings.compaction.enabled &&` to the existing automatic overflow-recovery predicate. It makes automatic recovery honor the existing disabled setting. The remainder of Pi is upstream code, and the patch is not a claim to authorship of Pi or its recovery algorithm. The copied upstream package/lock files include unused and development packages; they are provenance records, not Loom's complete runtime installation instructions.

The Moby profile's SHA-256 is `9c1025c88ccaa517b648da571961838744ea2137f176bfe6a48b21294cae9c76`. Its accompanying Apache license and NOTICE must remain with the copied profile. Pi's copyright and permission notice must remain with copied or substantial Pi material.

## External dependencies

Direct use of an external tool is distinct from redistributing its implementation. If a later release bundles dependency source, binaries, or an image, preserve the exact components' license and notice material for that release. In particular, Pi's root MIT license does not cover every npm package, the Node executable has a complete third-party license document, and the Python image contains components under several licenses. Do not label these aggregates as entirely MIT or Apache-2.0.

No license has been selected for Loom's own code in this source snapshot. The third-party licenses above apply to their respective material and do not supply a license for Loom's original code. Upstream names identify dependencies and do not imply endorsement.
