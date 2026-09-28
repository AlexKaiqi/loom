# Loom worker RPC binding

Public Node binding for the Loom `loom/1` worker transport. It provides bounded
UTF-8 JSON-RPC framing, session negotiation and immutable large-payload records.
It contains no model, execution-provider or Harness strategy policy.

Install the repository package at a fixed Git commit with npm. Import
`createWorkerConnection` from `@loom/worker-rpc/transport`, register operations,
and call `listen()`. The host must supply connected inherited FD 3 and complete
`session.hello` first. stdout/stderr are diagnostics. Declare `record.file/1`
only when the host grants a private record directory. Records verify their byte
count and digest; an invalid frame closes the connection. Protocol/schema and
error semantics belong to the Loom runtime contract.

The model adapter and reference Harness consume this same package. Keep framing
changes here and run their wire/composition tests against the exact new commit.
