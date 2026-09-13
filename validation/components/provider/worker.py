"""Candidate adapter process. Inputs contain no case ID, expected fields or credentials."""
import importlib
import json
import os
from pathlib import Path
import sys

config = json.loads(Path(sys.argv[1]).read_bytes())
output = Path(config["output"])
network = []
endpoint = config["endpoint"]


def audit(event, args):
    if event == "socket.connect":
        address = args[1]
        network.append(dict(event=event, address=list(address)))
        if address[0] != "127.0.0.1" or address[1] != endpoint["port"]:
            raise RuntimeError("independent worker refuses non-fixture network")
    elif event == "socket.getaddrinfo" and (args[0] != "127.0.0.1" or args[1] != endpoint["port"]):
        network.append(dict(event=event, host=str(args[0]), port=args[1]))
        raise RuntimeError("independent worker refuses non-fixture DNS")

sys.addaudithook(audit)
try:
    try:
        module = importlib.import_module(config["module"])
    except ModuleNotFoundError as error:
        result = dict(status="MISSING", error=str(error)); code = 2
    else:
        client = module.WireClient(endpoint={k:v for k,v in endpoint.items() if k!="pid"},
                                   scope=config["scope"], evidence_dir=config["artifacts"], timeout=2.0)
        result = dict(status="RETURNED", value=client.complete(config["intent"]))
        code = 0
except Exception as error:
    result = dict(status="ERROR", error=repr(error)); code = 1
result.update(network=network, pid=os.getpid())
output.write_text(json.dumps(result,ensure_ascii=True,indent=2)+"\n")
raise SystemExit(code)
