"""JSONL verification adapter over ordinary library methods, never exposed to tasks."""

import argparse, base64, json, os, sys, threading
from .store import ExecutionStore
from .errors import require


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trusted-config")
    parser.add_argument("--trusted-config-sha256")
    options = parser.parse_args()
    require(
        bool(options.trusted_config) == bool(options.trusted_config_sha256),
        "INVALID_REQUEST",
        "trusted configuration must have an exact digest",
    )
    cap = 2097152 if options.trusted_config else 262144
    output_lock = threading.Lock()
    current = {}
    park = threading.Event()

    def emit(value):
        with output_lock:
            sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
            sys.stdout.flush()

    def barrier(label, binding):
        if current.get("barrier") == label:
            value = {"test_barrier": label, "binding": binding}
            if label in (
                "channel_prefix_written_before_ack",
                "channel_written_before_ack",
            ):
                args = current["args"]
                fields = {
                    key: args[key]
                    for key in (
                        "call_id",
                        "method",
                        "execution_id",
                        "object_generation",
                        "channel_id",
                        "request_digest",
                        "byte_offset",
                    )
                }
                value["call_ref"] = store.query_call(
                    args["request"]["execution_id"], args["authority"], fields
                )["call_ref"]
            emit(value)
            park.wait()

    store = ExecutionStore(
        os.environ["LORE_X_STATE_DIR"],
        checkpoint=barrier,
        trusted_config=options.trusted_config,
        trusted_config_sha256=options.trusted_config_sha256,
    )
    while True:
        line = sys.stdin.buffer.readline(cap + 1)
        if not line:
            break
        require(
            len(line) <= cap and line.endswith(b"\n"),
            "INVALID_REQUEST",
            "control request cap",
        )
        call = json.loads(line)
        args = call["arguments"]
        request = args["request"]
        authority = args["authority"]
        id = request["execution_id"]
        method = call["method"]
        current["barrier"] = args.get("test_context", {}).get("requested_barrier")
        current["args"] = args
        fields = {
            key: args[key]
            for key in (
                "call_id",
                "method",
                "execution_id",
                "object_generation",
                "channel_id",
                "request_digest",
                "byte_offset",
            )
            if key in args
        }
        try:
            if options.trusted_config:
                require(
                    not set(args)
                    - {
                        "request",
                        "authority",
                        "binding",
                        "state_dir",
                        "test_context",
                        "checkpoint_id",
                        "purpose",
                        "receipt",
                        "stop_id",
                        "source_ref",
                        "object_generation",
                        "call_id",
                        "method",
                        "execution_id",
                        "channel_id",
                        "request_digest",
                        "byte_offset",
                        "stream",
                        "max_bytes",
                        "data_base64",
                        "release_id",
                        "original_full_ref",
                        "owner_receipt_ref",
                    },
                    "INVALID_REQUEST",
                    "peer cannot add trusted configuration",
                )
                require(
                    "transport_principal" not in authority,
                    "INVALID_REQUEST",
                    "peer principal override forbidden",
                )
            if method == "execute":
                result = store.execute(request, authority)
            elif method == "query":
                result = store.query(id, authority)
            elif method == "resume_dispatch":
                result = store.dispatch_created(id, authority)
            elif method == "await_exit":
                result = store.await_exit(id, authority)
            elif method == "checkpoint":
                result = store.checkpoint(
                    id,
                    authority,
                    args.get("checkpoint_id", call["request_id"]),
                    args.get("purpose", "checkpoint"),
                )
            elif method in ("resume", "seal"):
                receipt = args.get("receipt") or store.query(id, authority)[
                    "artifacts"
                ].get("checkpoint")
                result = getattr(store, method)(id, authority, receipt)
            elif method == "request_stop":
                result = store.request_stop(
                    id, authority, args.get("stop_id", call["request_id"])
                )
            elif method == "release":
                result = store.release(id, authority)
            elif method == "restore":
                result = store.restore(
                    request, authority, args["source_ref"], args["object_generation"]
                )
            elif method == "channel_read":
                result = store.channel_read(
                    id,
                    authority,
                    args["stream"],
                    args["max_bytes"],
                    fields if options.trusted_config else None,
                )
            elif method == "channel_write":
                result = store.channel_write(
                    id,
                    authority,
                    base64.b64decode(args["data_base64"], validate=True),
                    fields if options.trusted_config else None,
                )
            elif method == "close_stdin":
                result = store.close_stdin(
                    id, authority, fields if options.trusted_config else None
                )
            elif method == "query_call":
                result = store.query_call(id, authority, fields)
            elif method == "query_checkpoint":
                result = store.query_checkpoint(
                    id, authority, args["original_full_ref"]
                )
            elif method == "release_checkpoint":
                result = store.release_checkpoint(
                    id,
                    authority,
                    args["release_id"],
                    args["original_full_ref"],
                    args["owner_receipt_ref"],
                )
            else:
                raise ValueError("unknown trusted verification method")
            if current["barrier"]:
                park.wait()
        except Exception as exc:
            result = {
                "error": {
                    "code": getattr(exc, "code", "INVALID_REQUEST"),
                    "message": str(exc),
                }
            }
        emit({"request_id": call["request_id"], **result})


if __name__ == "__main__":
    main()
