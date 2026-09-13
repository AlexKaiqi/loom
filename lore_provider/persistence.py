"""Trusted local wire receipts; write and fsync before any parsed success returns."""
import os
from pathlib import Path
import tempfile
from .jsoncodec import encode


def save(path, data):
    path = Path(path)
    fd, pending = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(pending, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(pending): os.unlink(pending)


def save_json(path, data):
    save(path, encode(data))
