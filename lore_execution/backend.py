"""ExecutionBackend seam declaration (design/g3/x/backend-seam.md, D-X-SEAM-001).

Declaration only: no behavior, no runtime importers, no base-class change.
design/g3/x/contract.md §4 already requires any future execution backend to
satisfy the same contract as the fixed Docker backend; this module makes that
replacement boundary explicit in code, and
simulations/test_execution_backend.py guards it against drift.

Seam scope. The seam is the complete method surface that upper layers use on
the ExecutionStore composite (CallOperations, Retention, Lifecycle, core),
grouped by the roles of design/g3/x/contract.md §2/§3:

- acceptance/query: execute, query, await_exit, dispatch_created
- durability facts: restore, checkpoint, resume, request_stop, seal, release,
  release_checkpoint, query_checkpoint
- duplex control:   channel_read, channel_write, close_stdin
- call records:     query_call

Owner internals are NOT part of the seam: ``journal``, ``engine`` and
``node_profile`` are X-owner facilities that the host assembly and fact
readers use directly (lore_runtime/runtime.py, lore_runtime/tool_facts.py,
lore_session/execution.py). A replacement backend must deliver the same §3
facts (stopped proof, checkpoint artifact with manifest, call records,
UNKNOWN/INCOMPLETE_OBSERVATION semantics) through equivalent owner facilities,
and every assembly path that touches those internals must be re-verified per
design/g3/x/backend-seam.md §6 before any such backend enters the system.

Profile ownership (D-X-ENV-001). These request contents carry local-Docker
profile meaning and do not generalize as-is to another backend:

- ``readonly_mounts``: the single runtime-domain /input mount
- ``profile_sha256``: the pinned identity of the selected environment profile
  (design/g3/x/amendment-environment-profile-2026-09-15)
- budgets ``tmp_bytes`` / ``shm_bytes``: host tmpfs byte semantics
- ``environment``: the fixed-python-linux-v1 image/profile identity

Everything else in the request binding is backend-neutral contract surface.
"""

from typing import Protocol, runtime_checkable

BACKEND_OWNED_REQUEST_FIELDS = frozenset({"readonly_mounts"})
BACKEND_OWNED_PROFILE_FIELDS = frozenset({"profile_sha256"})
BACKEND_OWNED_BUDGET_FIELDS = frozenset({"tmp_bytes", "shm_bytes"})
BACKEND_OWNED_ENVIRONMENT = "fixed-python-linux-v1"

SEAM_METHODS = (
    "execute",
    "query",
    "await_exit",
    "dispatch_created",
    "restore",
    "checkpoint",
    "resume",
    "request_stop",
    "seal",
    "release",
    "release_checkpoint",
    "query_checkpoint",
    "channel_read",
    "channel_write",
    "close_stdin",
    "query_call",
)

OWNER_INTERNALS = frozenset({"journal", "engine", "node_profile"})

SERIALIZED_WRAPPED = frozenset({"channel_read", "channel_write", "close_stdin"})


@runtime_checkable
class ExecutionBackend(Protocol):
    """Structural contract for one execution backend; see the module docstring.

    Parameter shapes mirror the ExecutionStore composite. The three duplex
    calls are declared in their wrapped form because the store applies
    ``serialized()`` to them; their contract.md §2 argument shapes stay
    (id, authority, ...plus the documented call arguments).
    """

    def execute(self, request, authority): ...
    def query(self, id, authority): ...
    def await_exit(self, id, authority, timeout=9): ...
    def dispatch_created(self, id, authority): ...
    def restore(self, request, authority, source_ref, object_generation): ...
    def checkpoint(self, id, authority, checkpoint_id, purpose): ...
    def resume(self, id, authority, receipt): ...
    def request_stop(self, id, authority, stop_id): ...
    def seal(self, id, authority, receipt): ...
    def release(self, id, authority): ...
    def release_checkpoint(self, id, authority, release_id, fullref, receipt): ...
    def query_checkpoint(self, id, authority, fullref): ...
    def channel_read(self, id, *args, **kwargs): ...
    def channel_write(self, id, *args, **kwargs): ...
    def close_stdin(self, id, *args, **kwargs): ...
    def query_call(self, id, authority, fields): ...
