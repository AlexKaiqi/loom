# Prepared process Sandbox

`ssh-process/v1` runs ordinary Bash, builds and tests in a prepared Linux facility.
OpenSSH/SFTP provides transport, systemd transient services provide resource limits
and lifecycle, and NsJail provides the task's file/PID/network view. No task starts
a container or VM. Work and task facilities can share a machine; their views and
permissions remain separate. The [design book](../../docs/loom-design-book.html#section-5-5)
is the specification.

## Prepare once

Use a Linux facility with systemd 252+ as its service manager, cgroup v2, OpenSSH
with SFTP, Bash, Python 3 available as both `python` and `python3`, tar and the toolchain your tasks need. Debian/Ubuntu can provide the `python` alias with `python-is-python3`; the shared Loom facility already provides it in `/usr/local/loom-python/bin`. Install the audited
NsJail binary recorded in `deploy/work/Dockerfile`, or your own verified deployment
lock. `/usr`, `/bin`, `/lib` and optional `/lib64` must contain only public toolchain
files: tasks can read them. Secrets must live outside these trees. `/tmp` is private
to each task; networking is disabled. UID 65534 is reserved for isolated task
processes in this facility; untrusted host-login users must not share that identity.

Configure a dedicated controller SSH key using normal OpenSSH administration.
The controller uses the facility's root management account; this credential grants
facility administration, **not** task permissions. Put only its public key in the
facility's authorized keys. Keep the private key, mode 0600, in the controller's
private configuration outside Work and Git. Disable SSH forwarding/PTY for that
key with OpenSSH's `restrict` authorized-key option. Tasks receive neither the key
nor SSH/systemd control sockets. Do not expose this management endpoint to models.

On that facility:

```sh
python3 deploy/ssh-process/prepare.py --output /root/loom-process-options.json
```

Transfer the generated **public** options to the controller through a trusted
administrative channel. The host public key is pinned; do not replace it with an
unverified `ssh-keyscan` result. Configure the controller:

```sh
loom setup --sandbox-provider ssh-process/v1 \
  --sandbox-endpoint ssh://linux-facility.example:22 \
  --sandbox-options /private/loom-process-options.json \
  --sandbox-key-file /private/loom-process.key
```

Model selection/credentials are prompted as usual, or use the existing model
flags for noninteractive setup. With a Docker-hosted Work controller, place these
configuration files in its private host-state mount so the controller can read
them. Work authors and models still use the same `bash` tool and named Targets.

## Lifecycle and recovery

Each operation gets an exclusive directory and a unique systemd unit. Readiness
is probed in that process before a read-only FIFO gate releases the user script.
CPU/memory/process limits are checked in the actual cgroup. A confirmed command
exit and an empty cgroup precede output capture and atomic file publication.
After a disconnect, systemd's deadline still bounds compute; it does not declare
the business result successful. Unknown executions retain their original files,
logs and identities. Use `query-remote`, `cancel-effect`, and the normal Runtime
reconciliation commands. No automatic replay or garbage collection clears an
unknown result. Successful release retains small identity tombstones to prevent
reusing an old request. Administrators must retain those tombstones while the
corresponding Work histories can still refer to them.

The provider currently supports the offline ordinary-code profile. Browser,
desktop, device/network access and independent kernels require other explicitly
selected providers; this adapter does not claim those capabilities.

## Real verification

Tests require the real facility. A Docker container is used only as a Linux host
and independent observer in the test fixture, not as a task allocation mechanism.

```sh
export LOOM_SSH_ENDPOINT=ssh://127.0.0.1:22292
export LOOM_SSH_OPTIONS=/private/process-options.json
export LOOM_SSH_KEY_FILE=/private/process.key
export LOOM_SSH_EVIDENCE=/tmp/new-process-evidence
export LOOM_SSH_OBSERVER_CONTAINER=your-prepared-test-linux-host
(cd runtime && go test -race -v ./adapters/sshprocess)
```

Measure `TestRealLatency` separately from race tests. Its samples include a new
SSH connection, input transfer, native process creation and isolation validation;
they exclude facility/toolchain provisioning and model latency. A process spawn
number alone is not end-to-end readiness.
