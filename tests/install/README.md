# Source installation contract and checks

The source installer assembles the existing Go Runtime, independent Pi worker and
Kernel Harness into one user-owned prefix. It never changes host configuration,
authority databases, Work directories, shell profiles or service deployments.
`./install.sh` defaults to `~/.local/share/loom` with `~/.local/bin/loom` as the
launcher. `--prefix DIR` instead defaults to `DIR/bin/loom`; `--bin-dir DIR`
selects another launcher directory. Installation requires Unix, Go 1.24+, Node
24/npm, Git and Python 3.10+ with venv support. The script installs Harness dependencies
itself. It does not download or configure a Sandbox server.

Each release contains `bin/loom-runtime`, `bin/loom-model`, `services/model/`, `harnesses/kernel/`,
`deploy/`, and a private Python venv. Its launcher sets `LOOM_INSTALL_ROOT` to that
release and prepares only its child process PATH, with that release's `bin` first.
Setup records `worker = ["loom-model"]`; its executable is bound to the same
release as the Runtime even if an upgrade changes `current` before the worker is
started. New CLI invocations get the new worker without rewriting configuration.
Explicit operator worker argv remains available. Runtime can use that root to
find the bundled worker and Harness without recording their paths in Work.
Host configuration remains explicit. Existing releases remain available to
processes that have already started.

Before activation, the installer checks executable prerequisites, builds all
components and starts each installed executable. `current` is replaced with one
atomic symlink operation only after all checks pass. A failure must preserve the
previous active release and launcher. Existing unrelated launcher files or links
are rejected rather than overwritten. Concurrent installs of the same prefix are
serialized with an operating-system file lock.

Executable criteria in `test_install.py`:

1. A real install into paths containing spaces runs from an unrelated working
   directory and launches the installed Harness with no manually prepared venv or
   PATH; the Pi worker resolves its locked modules from the installed release.
2. Reinstallation activates a complete new release, retains the preceding one,
   and does not touch synthetic host configuration.
3. An actual build failure before activation preserves the prior symlink, CLI,
   source configuration, and release files.
4. An unrelated launcher file is rejected and retains its exact bytes.
5. Invalid Node versions fail before a release can become active.
6. After an upgrade, an already-started launcher and a new launcher each resolve
   and start the model process from their respective releases; setup configuration
   retains the same deployed worker command.

Run `python3 -m unittest discover -s tests/install -v`. The real installation
checks use temporary directories, leave the user's real home unchanged, and need
normal package download access. Raw command logs are available under the test
output directory printed by the runner; an exit code alone does not constitute
its assertions.
