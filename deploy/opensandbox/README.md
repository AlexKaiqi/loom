# OpenSandbox deployment

Loom's Go Runtime uses the official Go SDK and a separately deployed official server image. It never launches Docker from the Runtime. The supported deployment uses server v0.2.3 and execd v1.1.0, both digest-pinned in `versions.json`. No Loom sandbox image, Python proxy or custom Docker API proxy is built. The Go SDK is pinned to official commit `ff4d1bc269cf6a9be03592649bed19633bf45222`. See [the Sandbox contract](../../docs/contracts/sandbox.md).

The `code` profile uses upstream bubblewrap isolated sessions and upstream seccomp configuration. `execd.toml` preserves execd's built-in syscall deny list and adds socket/socketpair/connect denial. This closes access to the privileged execd HTTP endpoint from task code. The Runtime verifies this restriction inside each session before dispatching user code. Task processes have uid/gid 65534, zero effective/permitted/ambient capabilities and `no_new_privs=1`.

This is a network-disabled code environment. Browser, desktop and arbitrary network-enabled environments are not yet accepted. OpenSandbox 0.2.3 Docker cannot use `secureAccess`; removing the flag while sharing its network would expose an unauthenticated execd endpoint. `share_net=false` currently fails on this Docker deployment because upstream bootstrap adds SYS_ADMIN but not NET_ADMIN. The accepted mechanism is upstream seccomp denial with shared networking; it preserves the same no-network property. Kubernetes secure access is a candidate for network-enabled profiles and has not been verified here.

Deploy the official server on a Unix host with Docker. Store a random server API key and `server.toml` in an operator-only directory outside this repository. Configure the following values, with operator-local paths:

```toml
[server]
host = "0.0.0.0"
port = 18088
api_key = "<from operator secret>"
max_sandbox_timeout_seconds = 3600
[runtime]
type = "docker"
execd_image = "opensandbox/execd@sha256:6cf7dba2f21f0b536e100563d841ac58a9f31c2b0a081b7ac76796a24d6f47e2"
[docker]
network_mode = "bridge"
no_new_privileges = true
pids_limit = 256
port_range_min = 46000
port_range_max = 46999
# SYS_ADMIN is added only by upstream bootstrap.execd.isolation.
# Dropping it here would conflict with that upstream requirement.
drop_capabilities = ["AUDIT_WRITE", "MKNOD", "NET_ADMIN", "NET_RAW", "SYS_MODULE", "SYS_PTRACE", "SYS_TIME", "SYS_TTY_CONFIG"]
sandbox_env = { EXECD_ISOLATION_CONFIG = "/etc/loom-execd.toml" }
sandbox_binds = ["<absolute operator deployment path>/execd.toml:/etc/loom-execd.toml:ro"]
[storage]
allowed_host_paths = ["/nonexistent-loom-host-mounts-disabled"]
```

Copy `execd.toml` to that operator deployment directory with permissions 0600 (owned by the operator, not uid 65534). This one read-only configuration mount is not a task-data mount; it contains no credentials. Surface, Userspace, Runtime databases and host directories are never mounted. Run the official server image on Docker's bridge network so the server can reach the independent task containers, exposing only the authenticated lifecycle/proxy endpoint. Mount the Docker socket only into this trusted service, never into task containers:

```sh
docker run --name loom-opensandbox --network bridge \
  -p 127.0.0.1:18088:18088 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v <operator deployment path>/server.toml:/etc/opensandbox/config.toml:ro \
  opensandbox/server@sha256:ae8dfbb277f40a39ff01ef35e5e1c10675acfe0fa9db15259b8f323e5efab778
```

For a remote endpoint, deploy TLS and appropriate service ingress policy. The SDK's `UseServerProxy: true` keeps the client on the authenticated service protocol. Do not expose sandbox application ports to untrusted external clients; Docker service-host ingress rules remain an operator responsibility.

Verify health before running tests. From `runtime/`, run:

```sh
LOOM_SANDBOX_ENDPOINT=http://127.0.0.1:18088 \
LOOM_SANDBOX_KEY_FILE=<restricted-file> \
LOOM_SANDBOX_EVIDENCE=<new-absolute-evidence-directory> \
go test ./sandbox -run '^TestReal' -v -count=1
```

These tests use Docker as an independent observer and, in the explicit dead-execd test, as a fault injector in their own container. Each test cleans up only its own native service IDs. The shared service must remain available until independent acceptance finishes, then can be stopped separately. API keys and complete server configuration stay outside source and evidence. Tests without an explicit endpoint skip the real-service cases; a skip is not a validation pass.
