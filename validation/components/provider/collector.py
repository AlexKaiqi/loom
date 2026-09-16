"""Independent real localhost HTTP collector. Does not import any wire candidate."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import select
import socket
import time

# darwin defaults to spawn, which would re-run the unprotected runner module in
# the child. The collector child is a plain socket/pipe loop, so fork is safe
# on every supported Unix platform.
if multiprocessing.get_start_method(allow_none=True) != "fork":
    multiprocessing.set_start_method("fork", force=True)


def _serve(pipe, directory):
    out = Path(directory)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0)); listener.listen(2)
    records, configured = [], None
    active = peak = total_io = 0
    started = time.monotonic()
    pipe.send(dict(host="127.0.0.1", port=listener.getsockname()[1], scheme="http", pid=os.getpid()))
    try:
        while time.monotonic() - started < 45:
            ready, _, _ = select.select([pipe.fileno(), listener], [], [], .05)
            if pipe.fileno() in ready:
                message = pipe.recv()
                if message["op"] == "stop":
                    break
                if message["op"] == "configure":
                    configured = message["response"]
                    pipe.send(dict(ready=True))
                elif message["op"] == "snapshot":
                    pipe.send(dict(records=records, max_active=peak, total_io=total_io,
                                   elapsed=time.monotonic()-started, pid=os.getpid()))
            if listener in ready:
                sock, peer = listener.accept(); active += 1; peak = max(peak, active)
                assert active <= 2 and len(records) < 32
                number = len(records) + 1
                record = dict(index=number, peer=list(peer), accepted_at=time.monotonic(),
                              request_complete=False, response_send_complete=False, closed=False)
                received = bytearray(); transmitted = 0
                sock.settimeout(2)
                try:
                    while b"\r\n\r\n" not in received:
                        part = sock.recv(4096)
                        if not part: break
                        received.extend(part)
                        assert len(received) <= 73729
                    head, sep, rest = received.partition(b"\r\n\r\n")
                    assert sep and len(head) <= 8192
                    lines = head.decode("iso-8859-1").split("\r\n")
                    method, path, protocol = lines[0].split(" ")
                    headers = {}
                    for line in lines[1:]:
                        key, value = line.split(":", 1)
                        assert key.lower() not in headers
                        headers[key.lower()] = value.strip()
                    assert "transfer-encoding" not in headers
                    length = int(headers["content-length"])
                    assert 0 <= length <= 65537
                    while len(rest) < length:
                        part = sock.recv(min(4096, length-len(rest)))
                        if not part: break
                        received.extend(part); rest.extend(part)
                    body = bytes(rest)
                    record.update(method=method, path=path, protocol=protocol, headers=headers,
                                  declared_request_length=length, request_complete=len(body)==length,
                                  body_sha256=hashlib.sha256(body).hexdigest(), body_size=len(body))
                    request_path = out / f"{number:03}-request.http"
                    body_path = out / f"{number:03}-request.body"
                    request_path.write_bytes(received); body_path.write_bytes(body)
                    record.update(request_path=str(request_path), body_path=str(body_path))
                    assert configured is not None and record["request_complete"]
                    data = configured["body"]
                    header = (f"HTTP/1.1 {configured['status']} Fixture\r\n"
                              f"Content-Length: {configured['content_length']}\r\n"
                              "Content-Type: application/json\r\nConnection: close\r\n\r\n").encode("ascii")
                    outgoing = header + data
                    (out / f"{number:03}-response.http").write_bytes(outgoing)
                    view = memoryview(outgoing)
                    while transmitted < len(view):
                        sent = sock.send(view[transmitted:])
                        assert sent > 0
                        transmitted += sent
                    record.update(response_status=configured["status"], advertised_response_length=configured["content_length"],
                                  response_body_size=len(data), response_body_sha256=hashlib.sha256(data).hexdigest(),
                                  actual_sent_bytes=transmitted, response_header_size=len(header),
                                  response_send_complete=transmitted==len(outgoing))
                    sock.shutdown(socket.SHUT_WR)
                except Exception as error:
                    record["error"] = repr(error)
                finally:
                    sock.close(); active -= 1
                    record.update(closed=True, closed_at=time.monotonic(), actual_received_bytes=len(received))
                    total_io += len(received) + transmitted
                    records.append(record)
                    with (out / "connections.jsonl").open("a") as stream:
                        stream.write(json.dumps(record)+"\n")
                    assert total_io <= 67108864
    finally:
        listener.close()
        (out / "final.json").write_text(json.dumps(dict(records=records,max_active=peak,total_io=total_io,
                                          elapsed=time.monotonic()-started),indent=2)+"\n")


class Collector:
    def __init__(self, directory):
        self.directory = Path(directory); self.directory.mkdir()
        self.pipe, child = multiprocessing.Pipe()
        self.process = multiprocessing.Process(target=_serve, args=(child, str(self.directory)))
        self.process.start()
        assert self.pipe.poll(3)
        self.endpoint = self.pipe.recv()

    def configure(self, response, body):
        self.pipe.send(dict(op="configure", response=dict(status=response["status"],
                            content_length=response["content_length"], body=body)))
        assert self.pipe.poll(3) and self.pipe.recv()["ready"]

    def snapshot(self):
        self.pipe.send(dict(op="snapshot")); assert self.pipe.poll(3)
        return self.pipe.recv()

    def close(self):
        if self.process.is_alive():
            self.pipe.send(dict(op="stop")); self.process.join(3)
        if self.process.is_alive():
            self.process.kill(); self.process.join()
        self.pipe.close()
