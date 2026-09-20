# Installation and minimal-Harness acceptance

These checks exercise the installed CLI as a separate user, with a fresh installation prefix, home, authority and Work. They do not import production Runtime or Harness modules. Output, HTTP observations and failure records belong in an explicitly supplied directory outside the repository.

The acceptance properties derive from `SPEC.md` and the component contracts:

1. Installation makes the CLI, native-Pi worker and default Harness runnable from an unrelated directory without a checkout path, hand-written worker argv, `PYTHONPATH` or a separate Python dependency-install step. Reinstallation must not overwrite private user settings or corrupt a previously usable installation on a failed preparation.
2. Service setup produces separate host-only routing and a portable Work template. Secrets are supplied through named environment references, never CLI arguments, Work content or logs. Missing dependencies and invalid settings fail before provider/Sandbox dispatch.
3. The normal path creates a valid Work with the installed default Harness, explicitly binds a task directory and accepts natural-language input without a manually created JSON payload. Stable caller-supplied request identity remains idempotent; conflicting reuse rejects with no extra pending event. A failed run does not erase admitted responsibility.
4. The minimal Harness uses ordinary Surface files for current plan, report, notes and archived context. Current plan/notes/report enter model context; archived bodies remain stored/recoverable but are not injected wholesale into every prompt. Archive references remain discoverable. Runtime has no plan/archive business policy.
5. Real Pi with a controlled provider and real official OpenSandbox executes both authorized domains, reads independently chosen task bytes and writes expected ordinary plan/report/archive files. The provider receives persisted intent before dispatch, tools execute with the accepted isolated identity, final files match independent expectations and remote operation resources are gone.
6. Failure paths preserve physical identity, scoped authority, unknown-outcome non-replay and the hidden Work boundary. A subsequent command against an unknown effect sends zero new provider/Sandbox requests.
7. Every passing conclusion is tied to source/dependency hashes and direct Work SQLite, files and HTTP observations. Controlled model output proves integration and prompt selection, not free-form model competence. No skipped real-service check counts as pass.

The installer/CLI argument spelling is taken from the published current usage contract once established; these tests do not define a second product interface.

Run the independent installed-user composition with an existing accepted service:

```sh
python3 tests/onboarding/run.py \
  --output /tmp/loom-onboarding-results \
  --private-dir /tmp/loom-onboarding-private-run \
  --sandbox-endpoint http://127.0.0.1:18092 \
  --sandbox-key-file /path/to/operator/key
```

Both output paths must be fresh. `run.py` invokes the source installer itself into a prefix containing spaces, with a fresh home; host routing and physical authority remain under the private path. Its controlled provider uses the real Pi catalog entry `groq/llama-3.1-8b-instant` and native OpenAI-completions SSE. This deliberately exercises a catalog model whose maximum output capacity equals its context capacity: supported output capacity must not be mistaken for the per-request output reservation.

The provider makes four tool-bearing turns with independently chosen 12 KB text segments, forcing the default kernel's native archive hook. Acceptance reads the saved original context and later outbound provider request, in addition to verifying the real Sandbox task and Surface bytes. Source hashes are captured before installation. Keep failed run directories; use a new pair of paths after a repair.
