# Runtime independent acceptance

Specification: [the HTML design book](../../docs/loom-design-book.html). These tests execute the compiled Go CLI. Python is only the independent driver and SQLite/HTTP observer; it never imports a Loom production package. External Harness fixtures communicate only through the public protocol, and model cases use real Pi even when provider responses are controlled.

Inside a configured shared Linux Work facility, set `LOOM_GO_BINARY` to the compiled absolute binary, `LOOM_TEST_CGROUP_ROOT` to a delegated cgroup, and `LOOM_GO_EVIDENCE` to a fresh directory outside the checkout. Then run:

```sh
python3 -m unittest discover -s tests/go_acceptance -v
```

For a frozen combined run:

```sh
python3 tests/go_acceptance/run_frozen.py --output /tmp/loom-acceptance
```

Use a fresh output directory outside the repository. Live-provider and real-Sandbox cases are separately opt-in; fixtures do not certify execution isolation or remote lifecycle behavior.

`python3 tests/go_acceptance/scale.py --binary /absolute/path/to/loom --output /tmp/loom-load` runs a fixed 32-Work load in the same Linux facility. The saved plan defines all thresholds before dispatch; observations include process residency, measured delivery latency, concurrency and restart results. It uses real Python and Node Harnesses, with a controlled HTTP model. It is a bounded test, not a long-duration soak or the A35 real-model comparison.
