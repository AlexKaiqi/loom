"""External assertions use frozen samples, socket receipts and actual saved bytes."""
import hashlib
import json
import stat
from pathlib import Path


def exact(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)


def assess(case, kind, returned, records, request_expected, response, raw_response, scope, artifact_root, positive_normalized):
    failures = []
    def check(name, condition):
        if not condition: failures.append(name)
    expected_count = 1 if kind == "response" else case["expected_http_requests"]
    check("actual_http_count", len(records)==expected_count)
    check("worker_returned", returned.get("status")=="RETURNED")
    value = returned.get("value", {})
    if expected_count == 0:
        check("request_rejection", value.get("accepted") is False and value.get("reason")==case["expected_error"])
        check("zero_connect_attempts", returned.get("network")==[])
        check("no_fake_transport", value.get("request") is None and value.get("transport") is None and value.get("artifacts") is None)
        return failures
    if len(records)!=1:
        return failures
    actual = records[0]
    network = returned.get("network", [])
    check("one_authorized_connect", len(network)==1 and network[0].get("event")=="socket.connect" and network[0].get("address", [None])[0]=="127.0.0.1")
    check("complete_received_request", actual.get("request_complete") is True)
    check("fixed_request_method_path", actual.get("method")=="POST" and actual.get("path")=="/v1/chat/completions")
    body = Path(actual["body_path"]).read_bytes()
    check("request_bytes", body==request_expected)
    check("no_auth_header", "authorization" not in actual.get("headers", {}))
    check("socket_send_closed", actual.get("response_send_complete") is True and actual.get("closed") is True)
    complete = actual.get("response_body_size")==actual.get("advertised_response_length")
    expected_transport = dict(http_status=response["status"],content_length=response["content_length"],
                              received_size=len(raw_response),complete=complete)
    check("transport_facts", exact(value.get("transport"))==exact(expected_transport))
    check("request_facts", exact(value.get("request"))==exact(dict(method="POST",path="/v1/chat/completions",
                       size=len(request_expected),sha256=hashlib.sha256(request_expected).hexdigest())))
    artifacts = value.get("artifacts") or {}
    try:
        controlled = Path(artifact_root)
        check("artifact_root_ordinary", controlled.is_dir() and not controlled.is_symlink())
        for key in ("request_path", "response_path", "transport_path", "association_path"):
            actual_path = Path(artifacts[key])
            check("artifact_containment_"+key, actual_path.resolve().is_relative_to(controlled.resolve()) and stat.S_ISREG(actual_path.lstat().st_mode))
        saved_request = Path(artifacts["request_path"]).read_bytes()
        saved_response = Path(artifacts["response_path"]).read_bytes()
        saved_transport = json.loads(Path(artifacts["transport_path"]).read_bytes())
        association = json.loads(Path(artifacts["association_path"]).read_bytes())
        check("saved_original_bytes", saved_request==body and saved_response==raw_response)
        check("saved_transport", exact(saved_transport)==exact(expected_transport))
        expected_association = dict(binding=scope,scope=scope,request_sha256=hashlib.sha256(body).hexdigest(),
                                    response_sha256=hashlib.sha256(raw_response).hexdigest())
        check("saved_complete_association", exact(association)==exact(expected_association))
    except (OSError, KeyError, ValueError, TypeError):
        check("actual_artifacts_present", False)
    if kind == "response":
        expected = case["expected"]
        check("accepted", value.get("accepted") is expected["accepted"])
        if expected["accepted"]:
            check("full_normalized_message_wire_pricing", exact(value.get("normalized"))==exact(expected["normalized"]))
        else:
            check("response_rejection_reason", value.get("reason")==expected["reason"])
            check("no_fake_message_on_failure", "normalized" not in value)
    else:
        check("positive_request_completed", value.get("accepted") is True)
        check("positive_request_full_response", exact(value.get("normalized"))==exact(positive_normalized))
    check("no_action_or_final_interface", not any(k in value for k in ("actions","action_dispatches","final")))
    return failures
