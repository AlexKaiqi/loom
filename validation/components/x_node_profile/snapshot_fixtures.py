"""Trusted validation-only S ordinary originals; no Session implementation or Pi parser."""
from pathlib import Path
import base64, copy, io, os, tarfile
from artifacts import canonical, file_fact, save, sha_bytes

EMPTY = {'.': {'kind': 'dir', 'mode': 0o700, 'uid': 1000, 'gid': 1000, 'mtime_ns': 0, 'xattrs': {}}}

def scope(session_id='session-one', execution=None):
    return {'namespace': 'xn-fixture', 'surface_id': 'surface-one', 'session_id': session_id,
            'session_generation': 1, 'original_execution': copy.deepcopy(execution)}

def tar_bytes(entries, contents=None, duplicate=None, pax_extra=None):
    contents = contents or {}
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for name in [*entries, *([duplicate] if duplicate else [])]:
            row = entries[name]
            item = tarfile.TarInfo(name)
            item.mode = row['mode']; item.uid = row['uid']; item.gid = row['gid']
            seconds, nanos = divmod(row['mtime_ns'], 1000000000)
            item.mtime = seconds
            # divmod for negative ns yields a floor second plus positive fractional part.
            item.pax_headers = {'mtime': format(__import__('decimal').Decimal(row['mtime_ns']) / __import__('decimal').Decimal(1000000000), 'f')}
            item.pax_headers.update((pax_extra or {}).get(name, {}))
            kind = row['kind']
            item.type = {'dir': tarfile.DIRTYPE, 'file': tarfile.REGTYPE, 'symlink': tarfile.SYMTYPE,
                         'hardlink': tarfile.LNKTYPE, 'fifo': tarfile.FIFOTYPE}[kind]
            if kind == 'file':
                data = contents[name]; item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
            else:
                if kind == 'symlink': item.linkname = os.fsdecode(base64.b64decode(row['target_base64']))
                if kind == 'hardlink': item.linkname = row['target']
                archive.addfile(item)
    return out.getvalue()

def original(root, expected, entries=None, contents=None, raw=None, origin=None):
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    entries = copy.deepcopy(EMPTY if entries is None else entries)
    raw = tar_bytes(entries, contents) if raw is None else raw
    archive_path = root / 'original.tar'
    with archive_path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    archive_ref = file_fact(archive_path)[0]
    manifest = {'schema': 'lore-x-session-ordinary-manifest/v1',
                **{k: expected[k] for k in ('namespace', 'session_id', 'session_generation')},
                'metadata_profile': 'linux-posix-session-no-xattr-acl-v1', 'entries': entries,
                'logical_bytes': sum(x.get('byte_length', 0) for x in entries.values() if x['kind'] == 'file'),
                'archive_sha256': archive_ref['sha256'], 'archive_bytes': len(raw)}
    manifest_path = root / 'manifest.json'; save(manifest_path, manifest)
    manifest_ref = file_fact(manifest_path)[0]
    record = {'schema': 'lore-x-session-ordinary-snapshot/v1',
              'origin': origin or ('empty-initial' if expected['original_execution'] is None else 'checkpoint'),
              **copy.deepcopy(expected), 'archive': archive_ref, 'manifest': manifest_ref}
    record_path = root / 'record.json'; save(record_path, record)
    ref = {'owner': 'S', 'id': root.name,
           **{k: expected[k] for k in ('namespace', 'session_id', 'session_generation')},
           'record_path': str(record_path), 'record_sha256': sha_bytes(record_path.read_bytes())}
    for prefix, fact in [('archive', archive_ref), ('manifest', manifest_ref)]:
        for key in ('path', 'sha256', 'bytes'): ref[prefix + '_' + key] = fact[key]
    save(root / 'reference.json', ref)
    return ref

def regular(data, mtime_ns=1700000000123456789):
    return {'kind': 'file', 'mode': 0o600, 'uid': 1000, 'gid': 1000, 'mtime_ns': mtime_ns,
            'xattrs': {}, 'byte_length': len(data), 'sha256': sha_bytes(data)}
