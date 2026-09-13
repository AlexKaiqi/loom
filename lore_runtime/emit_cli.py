"""Standalone ordinary application outbox helper. Local staging is never acceptance."""
import json
import math
import os
import stat

RELATIVE_PATH = '.lore/emit-requests.jsonl'
MAX_BYTES, MAX_ROWS, MAX_LINE, MAX_NEW = 65536, 64, 8192, 8


def _require(value, message):
    if not value:
        raise ValueError(message)


def _finite(value, depth=0):
    _require(depth <= 32, 'JSON nesting exceeds 32')
    if type(value) is dict:
        _require(all(type(k) is str for k in value), 'non-string object key')
        for key in value:
            key.encode('utf8')
        for item in value.values():
            _finite(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _finite(item, depth + 1)
    elif type(value) is str:
        value.encode('utf8')
    elif type(value) is float:
        _require(math.isfinite(value), 'nonfinite JSON number')
    else:
        _require(value is None or type(value) in (str, bool, int), 'non-JSON value')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate JSON field')
        result[key] = value
    return result


def decode(raw):
    value = json.loads(raw.decode('utf8'), object_pairs_hook=_pairs)
    _finite(value)
    return value


def encode(value):
    _finite(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf8')


def rows(raw):
    _require(len(raw) <= MAX_BYTES, 'outbox byte budget exceeded')
    _require(not raw or raw.endswith(b'\n'), 'incomplete outbox line')
    lines = raw.splitlines(keepends=True)
    _require(len(lines) <= MAX_ROWS, 'outbox record budget exceeded')
    result = []
    for index, line in enumerate(lines, 1):
        _require(line.endswith(b'\n') and len(line) <= MAX_LINE, 'line incomplete or too large')
        value = decode(line)
        _require(type(value) is dict and set(value) == {'id', 'name', 'payload'}, 'outbox row fields differ')
        _require(type(value['id']) is int and value['id'] == index, 'outbox ordinal differs')
        _require(type(value['name']) is str and value['name'], 'name must be nonempty text')
        payload = value['payload']
        _require(type(payload) is not dict or not set(payload) & {'origin', 'principal', 'system'},
                 'payload cannot impersonate a trusted source')
        result.append(value)
    return result


def emit_local(root, name, payload):
    """Only ordinary user data; no R, NATS, host handles or receipt/progress records."""
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory = fd = None
    try:
        try:
            os.mkdir('.lore', mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        directory = os.open('.lore', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        fd = os.open('emit-requests.jsonl', os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'outbox must be an independent regular file')
        _require(before.st_size <= MAX_BYTES, 'outbox byte budget exceeded')
        old = os.pread(fd, MAX_BYTES + 1, 0)
        parsed = rows(old)
        value = dict(id=len(parsed) + 1, name=name, payload=payload)
        line = encode(value) + b'\n'
        rows(old + line)  # Validate complete old+new data before any write.
        _require(os.fstat(fd).st_size == len(old), 'concurrent append; retry with original bytes')
        written = os.write(fd, line)
        os.fsync(fd)
        _require(written == len(line), 'partial local append; not accepted')
        _require(os.fstat(fd).st_size == len(old) + len(line), 'concurrent append; host validation required')
        os.fsync(directory)
        os.fsync(root_fd)
        return dict(status='LOCAL_STAGED', id=value['id'])
    finally:
        for handle in (fd, directory, root_fd):
            if handle is not None:
                os.close(handle)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/work')
    parser.add_argument('name')
    parser.add_argument('payload')
    args = parser.parse_args()
    print(encode(emit_local(args.root, args.name, decode(args.payload.encode('utf8')))).decode('utf8'))
