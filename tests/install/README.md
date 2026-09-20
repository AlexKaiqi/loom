# Installer checks

The [HTML design book](../../docs/loom-design-book.html) is the sole specification. These are operational instructions for the installer checks.

Run `python3 -m unittest discover -s tests/install -v` on macOS or Linux with Python 3.11+ and a real Linux Docker engine. No host Go, Node, npm or preconfigured Harness venv is required. Building the locked images needs network access and sufficient Docker storage. Set `LOOM_INSTALL_TEST_OUTPUT` to a fresh directory to retain evidence at a chosen location.

The checks install into paths containing spaces and run the installed launcher from outside the checkout. They inspect the actual image/container binding, import the installed Pi dependency, then execute `setup → new → ask` through the installed Go Runtime, restricted Python Harness and real Pi adapter against a controlled HTTP peer. The Work's SQLite records and unchanged shared source are inspected independently.

Upgrade checks retain an already-running Node process across activation and import its model component afterwards, verify both release launchers, and compare the private service configuration bytes. Other checks inject a build failure, preserve the active release, refuse an unrelated launcher and reject an unsupported execution engine before activation. The previous host-Node-version check became a Docker-engine check because Node is now part of the locked deployment image; the failure-before-activation criterion remains.

Only containers created by this test installation are removed at teardown. Releases, images, raw logs and observations are retained. A failed install or unavailable Docker engine is a failure, not a skipped acceptance case. These checks do not establish real-model effectiveness or remote Sandbox conformance.
