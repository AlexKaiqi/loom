# Runtime independent acceptance

Contract: `docs/contracts/acceptance.md` (G01–G08). These tests execute the compiled Go CLI. Python is only the independent driver and SQLite/HTTP observer; it never imports a Loom production package. External Harness fixtures communicate only through the public protocol, and model cases use real Pi even when provider responses are controlled.

Set `LOOM_GO_BINARY` to the compiled absolute binary and run:

```sh
python3 -m unittest discover -s tests/go_acceptance -v
```

For a frozen combined run:

```sh
python3 tests/go_acceptance/run_frozen.py --output /tmp/loom-acceptance
```

Use a fresh output directory outside the repository. Live-provider and real-Sandbox cases are separately opt-in; fixtures do not certify execution isolation or remote lifecycle behavior.
