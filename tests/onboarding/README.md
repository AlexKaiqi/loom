# Installed-user composition checks

The only specification is [the HTML design book](../../docs/loom-design-book.html). This directory contains operational verification instructions, not another contract.

Run with an existing official OpenSandbox service and a working Linux Docker engine:

```sh
python3 tests/onboarding/run.py \
  --output /tmp/loom-onboarding-results \
  --private-dir /tmp/loom-onboarding-private-run \
  --sandbox-endpoint http://127.0.0.1:18092 \
  --sandbox-key-file /path/to/operator/key
```

Both output directories must be fresh and outside the checkout. The driver installs into a prefix containing spaces and invokes the published CLI from an unrelated directory. The installation owns the shared Linux Work facility; the host does not need Go, Node or a separate Harness dependency installation. Private service credentials and the host authority remain outside the Work and evidence directory.

The controlled HTTP provider runs inside the facility, uses real Pi, and exercises the default Python Harness alongside real OpenSandbox. Work Bash edits ordinary optional Surface files and `surface/main.md`; Sandbox Bash changes a saved Target copy. The original shared project must remain unchanged. The provider explicitly chooses `body_refs` and then a closed `after` boundary; the checks inspect the later outbound input and retain the complete original records. Nothing triggers automatic archive or creates a second history copy.

The run also checks input idempotency, missing credentials, hard context capacity, unknown provider outcomes without replay, exact Git bytes, portable export and re-established physical authority. Source hashes, raw CLI output, SQLite rows and HTTP observations are retained, including on failure. This controlled run establishes integration properties only. It does not replace A35's repeated real-model quality, safety and cost comparisons.
