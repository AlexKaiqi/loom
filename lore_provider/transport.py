"""One direct trusted-endpoint HTTP exchange; no environment proxy or retry."""
import http.client
import socket
import threading
import time
from .jsoncodec import require

MAX_BODY = 1048576
_DEFAULT_PREFIX = "/v1"
_PATH_PREFIX_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/_")


def _request_path(endpoint):
    """2026-09-14 baseline: optional fixed path_prefix (user Volcengine plan route).

    Omitted prefix keeps the original fixed /v1/chat/completions behavior for
    every existing profile; a present prefix must be a pre-registered literal
    path fragment with no query or fragment characters.
    """
    prefix = endpoint.get("path_prefix", _DEFAULT_PREFIX)
    require(isinstance(prefix, str) and prefix.startswith("/") and not prefix.endswith("/") and
            prefix == "/" + prefix.strip("/") and len(prefix) <= 128 and
            all(character in _PATH_PREFIX_CHARACTERS for character in prefix), "invalid_endpoint")
    return prefix + "/chat/completions"


def exchange(endpoint, request, timeout, authorization=None):
    allowed = {"scheme", "host", "port", "path_prefix"}
    require(endpoint.get("scheme") in ("http", "https"), "invalid_endpoint")
    require(isinstance(endpoint.get("host"), str) and endpoint["host"] and
            type(endpoint.get("port")) is int and 0 < endpoint["port"] <= 65535, "invalid_endpoint")
    require(set(endpoint) <= allowed and {"scheme", "host", "port"} <= set(endpoint), "invalid_endpoint")
    factory = http.client.HTTPSConnection if endpoint["scheme"]=="https" else http.client.HTTPConnection
    connection = factory(endpoint["host"], endpoint["port"], timeout=timeout)
    request_path = _request_path(endpoint)
    started = time.monotonic(); timer = None; timed_out = []
    status = length = None; raw = bytearray(); headers = []
    try:
        connection.connect()
        remaining = timeout-(time.monotonic()-started)
        if remaining <= 0: raise TimeoutError("connection deadline")
        actual_socket = connection.sock
        # Shutting down the socket also wakes HTTPResponse's buffered file wrapper.
        def expire():
            timed_out.append(True)
            try: actual_socket.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        timer = threading.Timer(remaining, expire); timer.daemon = True; timer.start()
        request_headers = {"Content-Type":"application/json", "Connection":"close"}
        if authorization is not None:
            request_headers["Authorization"] = authorization
        connection.request("POST", request_path, body=request, headers=request_headers)
        response = connection.getresponse(); status = response.status; headers = response.getheaders()
        declared = [value for key,value in headers if key.lower()=="content-length"]
        if len(declared)==1 and declared[0].isdigit(): length = int(declared[0])
        maximum = min(length, MAX_BODY) if length is not None else MAX_BODY
        while len(raw) < maximum:
            if time.monotonic()-started >= timeout: raise TimeoutError("response deadline")
            chunk = response.read1(min(65536, maximum-len(raw)))
            if not chunk: break
            raw.extend(chunk)
    except (OSError, http.client.HTTPException):
        # Return the actual received prefix to persistence, including on disconnect.
        pass
    finally:
        if timer is not None:
            timer.cancel(); timer.join()
        connection.close()
    complete = (status is not None and length is not None and length<=MAX_BODY and
                len(raw)==length and not timed_out and time.monotonic()-started<=timeout)
    return bytes(raw), dict(http_status=status,content_length=length,received_size=len(raw),complete=complete), headers
