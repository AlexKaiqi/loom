"""Independent finite ordinary-file oracle; never imports X/S or extracts archives."""
from pathlib import Path, PurePosixPath
from decimal import Decimal, InvalidOperation
import base64, hashlib, io, json, os, stat, tarfile

class InvalidEvidence(ValueError):
    pass

def require(value, message):
    if not value:
        raise InvalidEvidence(message)

def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(InvalidEvidence('nonfinite JSON')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InvalidEvidence('invalid finite JSON: ' + str(exc)) from exc

def file_fact(path, cap=18874368):
    p = Path(path)
    require(p.is_absolute(), 'absolute original path required')
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise InvalidEvidence('original inaccessible: ' + str(p)) from exc
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= cap, 'bounded regular original required')
        chunks = []
        count = 0
        while True:
            chunk = os.read(fd, 1048576)
            if not chunk:
                break
            count += len(chunk)
            require(count <= cap, 'original grew beyond cap')
            chunks.append(chunk)
        after = os.fstat(fd)
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'original changed while observed')
        raw = b''.join(chunks)
        require(len(raw) == info.st_size, 'incomplete original read')
        return {'path': str(p), 'sha256': sha_bytes(raw), 'bytes': len(raw),
                'root': {'dev': info.st_dev, 'ino': info.st_ino}}, raw
    finally:
        os.close(fd)

def read_ref(ref, cap=18874368):
    require(isinstance(ref, dict) and {'path', 'sha256', 'bytes'} <= ref.keys(), 'complete file ref required')
    require(type(ref['bytes']) is int and 0 <= ref['bytes'] <= cap, 'invalid original size')
    fact, raw = file_fact(ref['path'], cap)
    require(all(ref[key] == fact[key] for key in ('path', 'sha256', 'bytes')), 'original ref bytes disagree')
    if 'root' in ref:
        require(ref['root'] == fact['root'], 'original inode association differs')
    return fact, raw

def member_name(name):
    require(isinstance(name, str) and name and '\x00' not in name, 'invalid archive name')
    if name.startswith('./'): name = name[2:]  # GNU tar source bytes retained; manifest key only.
    require(name == '.' or (not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/'))),
            'noncanonical archive path')
    require(name.encode('utf8', 'surrogatepass').decode('utf8') == name, 'unsupported name encoding')
    return name

def exact_ns(member):
    value = member.pax_headers.get('mtime')
    if value is None:
        require(type(member.mtime) is int, 'nonintegral mtime needs exact PAX')
        return member.mtime * 1000000000
    try:
        number = Decimal(value) * Decimal(1000000000)
        require(number.is_finite() and number == number.to_integral_value(), 'noninteger PAX nanoseconds')
        return int(number)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidEvidence('invalid exact PAX mtime') from exc

def archive_bytes(raw):
    require(isinstance(raw, bytes) and len(raw) <= 18874368, 'archive cap')
    entries = {}
    files = {}
    logical = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            for member in archive:
                name = member_name(member.name)
                require(name not in entries and len(entries) < 512, 'duplicate or too many archive members')
                require(not member.sparse and not any(k.startswith(('SCHILY.xattr.', 'SCHILY.acl.', 'GNU.sparse.')) for k in member.pax_headers),
                        'unsupported sparse/xattr/ACL')
                require(member.uid == 1000 and member.gid == 1000 and 0 <= member.mode <= 4095, 'metadata profile differs')
                kind = 'file' if member.isfile() else 'dir' if member.isdir() else 'symlink' if member.issym() else 'hardlink' if member.islnk() else None
                require(kind is not None, 'special archive member')
                row = {'kind': kind, 'mode': member.mode, 'uid': member.uid, 'gid': member.gid,
                       'mtime_ns': exact_ns(member), 'xattrs': {}}
                if kind == 'file':
                    require(0 <= member.size <= 16777216, 'regular member cap')
                    data = archive.extractfile(member).read(16777217)
                    require(len(data) == member.size, 'truncated regular contents')
                    logical += len(data)
                    require(logical <= 16777216, 'logical archive cap')
                    row.update(byte_length=len(data), sha256=sha_bytes(data))
                    files[name] = data
                elif kind == 'symlink':
                    require('\x00' not in member.linkname, 'NUL link target')
                    row['target_base64'] = base64.b64encode(os.fsencode(member.linkname)).decode()
                elif kind == 'hardlink':
                    row['target'] = member_name(member.linkname)
                entries[name] = row
    except (tarfile.TarError, OSError, UnicodeError, OverflowError) as exc:
        raise InvalidEvidence('invalid original archive') from exc
    require('.' in entries and entries['.']['kind'] == 'dir', 'root directory member missing')
    for name, row in entries.items():
        if name == '.':
            continue
        parent = PurePosixPath(name).parent.as_posix()
        require(parent in entries and entries[parent]['kind'] == 'dir', 'missing/nondirectory ancestor')
        if row['kind'] == 'hardlink':
            target = entries.get(row['target'])
            require(target is not None and target['kind'] == 'file', 'hardlink must name original regular member')
            require(all(row[k] == target[k] for k in ('mode', 'uid', 'gid', 'mtime_ns', 'xattrs')), 'hardlink group metadata differs')
    return entries, files, logical

def snapshot(ref, expected):
    require(isinstance(ref, dict) and ref.get('owner') == 'S', 'trusted S original reference required')
    for key in ('namespace', 'session_id', 'session_generation'):
        require(ref.get(key) == expected[key], 'original session scope differs: ' + key)
    record_fact, record_raw = read_ref({'path': ref['record_path'], 'sha256': ref['record_sha256'],
                                      'bytes': Path(ref['record_path']).stat().st_size}, 2097152)
    record = strict_json(record_raw)
    require(set(record) == {'schema', 'origin', 'namespace', 'surface_id', 'session_id', 'session_generation',
                            'original_execution', 'archive', 'manifest'}, 'complete snapshot record fields')
    require(record['schema'] == 'lore-x-session-ordinary-snapshot/v1', 'snapshot schema')
    for key in ('namespace', 'surface_id', 'session_id', 'session_generation', 'original_execution'):
        require(record[key] == expected[key], 'original registered record association differs: ' + key)
    archive_fact, raw = read_ref(record['archive'])
    manifest_fact, manifest_raw = read_ref(record['manifest'], 2097152)
    for prefix, fact in [('archive', archive_fact), ('manifest', manifest_fact)]:
        for key in ('path', 'sha256', 'bytes'):
            require(ref[prefix + '_' + key] == fact[key], 'top ref disagrees with original ' + prefix)
    manifest = strict_json(manifest_raw)
    require(set(manifest) == {'schema', 'namespace', 'session_id', 'session_generation', 'metadata_profile',
                              'entries', 'logical_bytes', 'archive_sha256', 'archive_bytes'}, 'complete manifest fields')
    require(manifest['schema'] == 'lore-x-session-ordinary-manifest/v1' and
            manifest['metadata_profile'] == 'linux-posix-session-no-xattr-acl-v1', 'ordinary manifest profile')
    for key in ('namespace', 'session_id', 'session_generation'):
        require(manifest[key] == expected[key], 'manifest session association differs')
    require(manifest['archive_sha256'] == archive_fact['sha256'] and manifest['archive_bytes'] == len(raw), 'manifest/archive byte binding')
    entries, files, logical = archive_bytes(raw)
    require(manifest['entries'] == entries and type(manifest['logical_bytes']) is int and manifest['logical_bytes'] == logical,
            'actual complete members/metadata/content differ')
    if record['origin'] == 'empty-initial':
        require(expected['original_execution'] is None and entries == {'.': {'kind': 'dir', 'mode': 0o700, 'uid': 1000,
                    'gid': 1000, 'mtime_ns': 0, 'xattrs': {}}}, 'empty origin conceals actual contents')
    else:
        require(record['origin'] == 'checkpoint' and isinstance(expected['original_execution'], dict), 'checkpoint association absent')
    return {'record': record, 'manifest': manifest, 'files': files, 'archive_fact': archive_fact,
            'manifest_fact': manifest_fact, 'record_fact': record_fact}
