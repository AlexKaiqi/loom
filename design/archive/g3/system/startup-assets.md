# Fixed Linux startup assets

Scope: ordinary startup files/configuration only. No Engine, Node execution, model, NATS, Runtime scheduling or policy. The existing HostFiles gate must pass before the actual F composition run.

`StartupAssets(root, config)` performs only trusted file/configuration preparation and exposes `.host`, `.register(kind, full_ref, scope)`. `config` fixes `principal`, `namespace`, `sources` (exact surface/workspace `{path,resource_id}`), the exact nine `code_sources` (full `{path,bytes,sha256}`), original `profile_ref`, `request_template_ref`, `deps_mount`, keyless `model`, `capability_limits`, optional full-F `original_refs` mapping. The nine logical code paths are Node entry/adapter/session/callbacks/stdio/common, minimal index/projection, runtime index. No arbitrary module selection or credential field.

Root constructs actual R and `HostFiles(control, assets.host)`, then actual `FileStore` with its callbacks and `owner.files=files`. `assets.build(files)` returns `{host,initial_refs,registrations_spec,config_ref}`. Register callback is the exact existing immutable-full-ref-registration protocol; no fixture index or independent state authority.

Surface/Workspace captures retain caller paths and actual root identities; generated Harness code is captured/materialized through actual F. Harness/capability descriptors are actual historical F files, directly read back. The F-view for each registered caller resource names the caller root and original captured version, not a replacement directory. Initial source identities and immutable host files fix ownership on reentry. A changed existing source tree is rejected when rebuilding a captured initial version.

The trusted slot retains three objects, 768 MiB memory, 128 MiB combined writable storage and 8192 inodes; Node and tool/profile budgets are unchanged. Profile/dependency full refs are injected by trusted host and checked by the original X validator. Configuration files contain no endpoint or credentials.

## Executable checks registered before implementation

- SA01: actual R/F/HostFiles build; exact nine source bytes survive the original F Git archive/materialization; both user roots/path/inode stay original; descriptors read through F; original R registration accepts Harness; real X NodeProfile can consume the fixed config. No Engine object is constructed.
- SA02: same startup configuration/build repeats exact original refs; source file corruption, wrong complete code set, replaced caller root, or changed captured source tree is rejected. Original trees and evidence remain.
- SA03: true R/E file binding + actual S empty owner + production SessionPlans produces schema2 configuration validated by original X NodeProfile; compact refs correspond to startup full F descriptors and original nine files. E four-file packet is a controlled empty input fixture, not NATS acceptance. No Node/model execution.

The runner executes only a copied finite Python closure plus copied source code/inputs, captures original/source-copy hashes and preserves nonzero MISSING before product creation. This is startup preparation acceptance, not M01 or complete Runtime acceptance.
