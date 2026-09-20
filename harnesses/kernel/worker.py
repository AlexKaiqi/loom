"""Example policy, independently replaceable by any JSON-RPC worker."""
from pathlib import Path
import sys
from pylsp_jsonrpc.endpoint import Endpoint
from pylsp_jsonrpc.streams import JsonRpcStreamReader, JsonRpcStreamWriter

sys.dont_write_bytecode = True

# -I avoids host PYTHONPATH; only this fixed, digest-checked Harness is imported.
sys.path.insert(0, str(Path(__file__).parent))
from policy import Kernel

kernel = Kernel(Path(__file__).parent)
handlers = {
    "policy.admit": lambda params: True,
    "policy.start": kernel.start,
    "policy.continue": kernel.continuation,
    "policy.prepare": kernel.prepare,
}
writer = JsonRpcStreamWriter(sys.stdout.buffer)
endpoint = Endpoint(handlers, writer.write)
JsonRpcStreamReader(sys.stdin.buffer).listen(endpoint.consume)
endpoint.shutdown()
