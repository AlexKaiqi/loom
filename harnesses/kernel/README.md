# Reference Harness

The [HTML design book](../../docs/loom-design-book.html#chapter-04) defines the behavior. This directory contains ordinary Python policy code, its tool schemas and locked dependencies. Initial Surface files belong to `templates/default/`, outside the strategy.

`surface/main.md` is the maintained template. `include` fences select ordinary files or retained resource versions; one `facts` fence records explicit visibility choices. The model can edit both with Bash. Original facts and all actual inputs stay in immutable Runtime storage. There is no automatic archive threshold or mandatory plan/report directory.

`resource="app"` reads its fixed initial version. Add `target="backend"` to read the saved independent copy for that declared Target. In Work Bash, `/resources/bindings.json` gives the actual read-only paths and versions. `/harness` exposes the executing strategy; `/work/harness` contains its editable candidate.

Python uses pylsp-jsonrpc over inherited FD 3. stdout/stderr are diagnostic streams. Large projections are published as immutable records from the isolated output directory, so the RPC frame limit does not impose a history or projection size limit. The controller still checks model capacity before dispatch.

Run the pure renderer checks:

```sh
python3 -m unittest discover -s tests/harness -v
```

The renderer tests do not certify the Linux execution boundary, provider behavior or the quality/cost comparison required by A35. Those need combination and real-service runs.
