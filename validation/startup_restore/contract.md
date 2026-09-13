# Startup reentry after an authorized F installation

Prerequisite only for M03/M04; not a Runtime recovery gate. Sources: v5 lines 22, 106, 226, 326 and §7.2; `design/g3/system/startup-assets.md` requires original initial refs and host identity to remain fixed on reentry, SA02 rejects an unauthorized replacement. `bootstrap.assemble` reconstructs StartupAssets before HostFiles; `HostFiles._resource/_binding/resolve` already give an existing authorized R registration precedence over initial source grants.

Finite scenario, registered before execution:

1. SR01: use the existing startup_assets_probe Fixture with actual ControlStore, FileStore, Git and HostFiles, no Engine construction. Initial capture and R registration; a fresh Python process with identical configuration must return exactly the original build refs/host/config. Read initial Harness/capability through actual F.
2. SR02: use actual F capture/import/materialize, FilePublication and R acquire/prepare_install/confirm_install/release to install a modified Workspace. A narrowly bound no-Engine source/stop authority is explicitly a fixture; it proves no process revocation. Verify an actual directory exchange, R revision 2/current inode, empty holder, retained original inode, and original/new F Git archive bytes. HostFiles must resolve the actual current R registration and published F version. Then a fresh Python process using the SAME startup config must keep the original initial Harness/capability/versions and host bytes, while resolving that original R current resource; it must neither recapture/reset the initial version nor re-register revision 1.

The existing object build path is also observed after installation to locate its stale-initial-inode check. Original unauthorized replacement/mutation rejection in SA02 remains a requirement; a legitimate R/F installation cannot be accepted merely because a pathname or replacement bytes happen to match. The future narrow repair must consult original completed F/R installation evidence and explicit pending/conflicting states, not rewrite host.json or erase R authority. Missing saved initial refs or corrupt original files fail closed.

Only `validation/startup_restore/` is written. The runner reuses the original finite startup source-copy layout and Fixture; all imported product Python files execute from that copy. No Docker/Engine instance, Node, model, NATS, credentials, or old M01 directory mutation. A failure after the real installation is retained before any product fix. No new restart ledger or recovery API.

Command: `research/.venvs/runtime-research/bin/python -B validation/startup_restore/run.py --batch NAME`.
