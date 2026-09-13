"""Finite original snapshot bytes, based on the accepted XN ordinary-file profile."""
from pathlib import Path, PurePosixPath
from decimal import Decimal, InvalidOperation
import base64
import hashlib
import io
import json
import os
import stat
import tarfile

RAW_LIMIT = 18874368
LOGICAL_LIMIT = 16777216
CONTROL_LIMIT = 2097152
SCOPE = ('namespace', 'surface_id', 'session_id', 'session_generation')
EXEC = ('execution_id', 'object_generation', 'request_digest', 'container_id', 'exec_id', 'volume_id', 'freeze_generation')
EMPTY = {'.': dict(kind='dir', mode=0o700, uid=1000, gid=1000, mtime_ns=0, xattrs={})}


class SnapshotError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(value, message, code='invalid_snapshot'):
    if not value:
        raise SnapshotError(code, message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf8')
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SnapshotError('invalid_snapshot', 'invalid finite JSON value') from exc


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        text = raw.decode('utf8') if isinstance(raw, bytes) else raw
        value = json.loads(text, object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False, 'nonfinite JSON'))
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SnapshotError('invalid_snapshot', 'invalid complete UTF8 JSON') from exc


def file_fact(path, cap=RAW_LIMIT):
    path = Path(path)
    require(path.is_absolute() and path.parent.resolve() == path.parent, 'original path is not absolute or has an aliased parent')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= cap, 'bounded regular original required')
            parts = []; length = 0
            while True:
                part = os.read(fd, min(1048576, cap+1-length))
                if not part:
                    break
                length += len(part)
                require(length <= cap, 'original exceeds byte cap')
                parts.append(part)
            after = os.fstat(fd)
            require(all(getattr(before, key) == getattr(after, key) for key in
                        ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')) and length == before.st_size,
                    'original changed during read')
            raw = b''.join(parts)
            return dict(path=str(path), sha256=sha(raw), bytes=length,
                        root=dict(dev=before.st_dev, ino=before.st_ino)), raw
        finally:
            os.close(fd)
    except OSError as exc:
        raise SnapshotError('original_unavailable', 'original file unavailable: '+str(path)) from exc


def read_ref(ref, cap=RAW_LIMIT):
    require(type(ref) is dict and {'path', 'sha256', 'bytes'} <= ref.keys(), 'complete file reference required')
    require(type(ref['bytes']) is int and 0 <= ref['bytes'] <= cap, 'invalid original file size')
    fact, raw = file_fact(ref['path'], cap)
    require(all(ref[k] == fact[k] for k in ('path', 'sha256', 'bytes')) and
            ('root' not in ref or ref['root'] == fact['root']), 'original file reference differs')
    return fact, raw


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, raw):
    """Write once; an exact existing durable original is reusable, never overwritten."""
    path = Path(path)
    require(path.parent.resolve() == path.parent, 'output parent is an alias')
    if path.exists():
        require(file_fact(path, max(len(raw), CONTROL_LIMIT))[1] == raw,
                'partial or conflicting original output is preserved', 'conflict')
        return file_fact(path, max(len(raw), CONTROL_LIMIT))[0]
    with path.open('xb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
    sync_dir(path.parent)
    return file_fact(path, max(len(raw), CONTROL_LIMIT))[0]


def member_name(name):
    require(type(name) is str and name and '\x00' not in name, 'invalid archive member')
    if name.startswith('./'):
        name = name[2:]
    require(name == '.' or (not name.startswith('/') and all(part not in ('', '.', '..') for part in name.split('/'))),
            'noncanonical archive member')
    try:
        name.encode('utf8')
    except UnicodeError as exc:
        raise SnapshotError('invalid_snapshot', 'unsupported archive name encoding') from exc
    return name


def exact_ns(member):
    value = Decimal(member.pax_headers['mtime']) if 'mtime' in member.pax_headers else Decimal(member.mtime)
    require(value.is_finite(), 'nonfinite original mtime')
    sign, digits, exponent = value.as_tuple()
    text = ''.join(str(d) for d in digits).lstrip('0')
    if not text:
        return 0
    power = exponent+9
    if power < 0:
        count = -power
        require(count < len(text) and text.endswith('0'*min(count, len(text))), 'noninteger original nanoseconds')
        text = text[:-count]; power = 0
    require(len(text)+power <= 19, 'mtime outside signed Linux nanoseconds')
    number = int(text)*(10**power)*(-1 if sign else 1)
    require(-(2**63) <= number < 2**63, 'mtime outside signed Linux nanoseconds')
    return number


def archive(raw):
    require(type(raw) is bytes and len(raw) <= RAW_LIMIT, 'raw archive exceeds profile')
    entries = {}; files = {}; logical = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as source:
            for member in source:
                name = member_name(member.name)
                require(name not in entries and len(entries) < 512, 'duplicate or excess archive member')
                require(not member.sparse and not any(k.startswith(('SCHILY.xattr', 'SCHILY.acl', 'LIBARCHIVE.xattr', 'GNU.sparse'))
                                                     for k in member.pax_headers), 'unsupported sparse/xattr/ACL')
                require(member.uid == member.gid == 1000 and 0 <= member.mode <= 4095, 'unsupported ordinary metadata')
                ns = exact_ns(member)
                kind = 'file' if member.isfile() else 'dir' if member.isdir() else 'symlink' if member.issym() else 'hardlink' if member.islnk() else None
                require(kind is not None, 'special archive member unsupported')
                row = dict(kind=kind, mode=member.mode, uid=1000, gid=1000, mtime_ns=int(ns), xattrs={})
                if kind == 'file':
                    require(0 <= member.size <= LOGICAL_LIMIT, 'ordinary file exceeds profile')
                    data = source.extractfile(member).read(LOGICAL_LIMIT+1)
                    require(len(data) == member.size, 'incomplete ordinary file')
                    logical += len(data); require(logical <= LOGICAL_LIMIT, 'logical snapshot exceeds profile')
                    row.update(byte_length=len(data), sha256=sha(data)); files[name] = data
                elif kind == 'symlink':
                    require('\x00' not in member.linkname, 'NUL symlink target')
                    row['target_base64'] = base64.b64encode(os.fsencode(member.linkname)).decode('ascii')
                elif kind == 'hardlink':
                    row['target'] = member_name(member.linkname)
                entries[name] = row
    except (tarfile.TarError, OSError, UnicodeError, InvalidOperation, ValueError, OverflowError) as exc:
        raise SnapshotError('invalid_snapshot', 'invalid original ordinary archive') from exc
    require('.' in entries and entries['.']['kind'] == 'dir', 'original root directory absent')
    for name, row in entries.items():
        if name != '.':
            parent = PurePosixPath(name).parent.as_posix()
            require(parent in entries and entries[parent]['kind'] == 'dir', 'missing or linked archive ancestor')
        if row['kind'] == 'hardlink':
            target = entries.get(row['target'])
            require(target is not None and target['kind'] == 'file' and
                    all(row[k] == target[k] for k in ('mode', 'uid', 'gid', 'mtime_ns', 'xattrs')),
                    'hardlink does not match its original regular member')
    return entries, files, logical


def empty_archive():
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w', format=tarfile.PAX_FORMAT) as target:
        member = tarfile.TarInfo('.'); member.type = tarfile.DIRTYPE
        member.uid = member.gid = 1000; member.mode = 0o700; member.mtime = 0
        target.addfile(member)
    return out.getvalue()


def session_original(files, descriptor, scope):
    jp, mp = descriptor['jsonl_relative_path'], descriptor['metadata_relative_path']
    require(member_name(jp) == jp and member_name(mp) == mp and jp in files and mp in files, 'original metadata or JSONL missing')
    raw = files[jp]
    require(raw and raw.endswith(b'\n'), 'torn original Session; do not open Pi')
    lines = raw.decode('utf8').split('\n'); lines.pop()
    header, metadata = decode(lines.pop(0)), decode(files[mp])
    require(type(header) is dict and header.get('kind') == 'header' and header.get('v') == 4, 'original Pi v4 header required')
    require(type(metadata) is dict and {'id', 'cwd', 'path', 'createdAt', 'storageVersion'} <= metadata.keys(), 'complete original metadata required')
    require(all(header.get(k) == metadata[k] for k in ('id', 'cwd', 'createdAt', 'storageVersion')) and
            metadata['id'] == scope['session_id'] and Path(metadata['cwd']).is_absolute() and
            metadata['path'] == str(Path(metadata['cwd'])/jp), 'original metadata/header/Session path differs')
    namespace = descriptor.get('binding_namespace', 'lore.prep.binding')
    key = descriptor.get('binding_key', 'op-1'); found = False; binding = None
    seq = 0; ids = set()
    for line in lines:
        transaction = decode(line); rows = transaction if type(transaction) is list else [transaction]
        require(rows, 'empty original transaction')
        for row in rows:
            require(type(row) is dict and type(row.get('seq')) is int and row['seq'] > seq, 'invalid original sequence')
            seq = row['seq']; kind = row.get('kind')
            if kind == 'entry':
                require(type(row.get('id')) is str and row['id'] not in ids and
                        (row.get('parentId') is None or row['parentId'] in ids), 'invalid original entry linkage')
                ids.add(row['id'])
            elif kind in ('value', 'list'):
                require(type(row.get('namespace')) is str and type(row.get('key')) is str and
                        (row.get('op') == 'delete' or ('value' in row and row.get('op') == ('set' if kind == 'value' else 'append'))),
                        'unknown original mutation')
                if kind == 'value' and (row['namespace'], row['key']) == (namespace, key):
                    found = row['op'] == 'set'; binding = row.get('value') if found else None
            else:
                require(kind == 'usage', 'unknown original record kind')
    require(found and canonical(binding) == canonical(descriptor['binding']), 'original complete binding differs or is absent')
    return dict(jsonl=dict(relative_path=jp, bytes=len(raw), sha256=sha(raw)),
                metadata=dict(relative_path=mp, bytes=len(files[mp]), sha256=sha(files[mp])), binding=binding)
