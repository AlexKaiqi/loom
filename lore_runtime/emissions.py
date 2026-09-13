"""Submit an ordinary tool's newly appended application data through original E."""
import copy
import os
import stat
from pathlib import Path

from lore_events.values import EventError, encode, fail, sha, same
from lore_files.archive import unpack
from lore_files.errors import FileError
from lore_files.util import DEFAULT_LIMITS, ordinary_path
from .emit_cli import RELATIVE_PATH, MAX_NEW, rows

LIMITS = dict(DEFAULT_LIMITS, max_entries=1024, max_archive_bytes=8388608,
              max_logical_bytes=12582912)


def require(value, message):
    if not value:
        fail('reference_invalid', message)


def outbox(ref, size_key):
    """Read exact original archive, retaining all of its members and bytes unchanged."""
    path = ordinary_path(ref['path'])
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_size == ref[size_key]
                and st.st_size <= LIMITS['max_archive_bytes'], 'original archive size/type differs')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(LIMITS['max_archive_bytes'] + 1)
        require(len(raw) == ref[size_key] and sha(raw) == ref['sha256'], 'original archive bytes differ')
    finally:
        os.close(fd)
    tree, contents = unpack(raw, LIMITS)
    directory = tree['entries'].get('.lore')
    require(directory is None or directory['kind'] == 'dir', 'outbox parent is not an ordinary directory')
    item = tree['entries'].get(RELATIVE_PATH)
    if item is None:
        return b''
    require(item['kind'] == 'file' and not any(RELATIVE_PATH in group for group in tree['hardlink_groups']),
            'outbox must be an independent ordinary file')
    return contents[RELATIVE_PATH]


class EmitService:
    def __init__(self, events, resolve_tool_source):
        require(callable(resolve_tool_source), 'trusted original tool source resolver required')
        self.events, self.resolve_tool_source = events, resolve_tool_source

    def _source(self, effect_id, binding, publication_ref):
        source = copy.deepcopy(self.resolve_tool_source(effect_id, copy.deepcopy(binding),
                                                       copy.deepcopy(publication_ref)))
        require(same(source['binding'], binding) and same(source['publication_ref'], publication_ref),
                'original tool binding or publication differs')
        frame, scope = source['frame'], binding['session_scope']
        require(source['namespace'] == scope['namespace'] and
                type(source['principal']) is str and source['principal'], 'original source/namespace absent')
        require(frame['type'] == 'tool.request' and frame['session_id'] == binding['session_id']
                and frame['operation_id'] == binding['operation_id']
                and same(frame['source_result_ref'], binding['source_result_ref']), 'original pending association differs')
        expected = 's-tool-' + sha(encode([scope, binding['operation_id'], frame['invocation_id']]))
        require(effect_id == source['effect_id'] == source['execution_id'] == frame['effect_id'] == expected,
                'original tool effect identity differs')
        if source['domain'] != 'runtime' or source['emit_allowed'] is not True or frame['request']['target'] != 'runtime':
            fail('denied', 'ordinary emit requires the original Runtime domain capability')
        cp, pub, base = source['output_archive_ref'], source['publication_ref'], source['base_archive_ref']
        intent, registration, release = pub['R_intent'], pub['registration'], pub['release']
        resource = registration['id']
        require(registration['namespace'] == scope['namespace'] and registration['kind'] == 'surface'
                and resource == scope['surface_id'] == intent['resource_id'] == release['resource_id'],
                'published resource/namespace differs')
        require(intent['execution_id'] == release['execution_id'] == effect_id and release['released'] is True,
                'original publication/release is not confirmed for this execution')
        require(cp['owner'] == 'X' and cp['execution_id'] == effect_id and
                cp['source_binding']['execution_id'] == effect_id and
                cp['source_binding']['domain'] == source['domain'] and
                cp['source_binding']['target_id'] == resource and
                cp['object_generation'] == cp['source_binding']['object_generation'] and
                cp['freeze_generation'] == cp['source_binding']['freeze_generation'], 'original checkpoint belongs to another execution/scope')
        require(intent['base_ref']['resource_id'] == resource and intent['base_ref']['domain'] == 'surface' and
                pub['F_query']['version_ref']['resource_id'] == resource and
                pub['F_query']['version_ref']['domain'] == 'surface' and
                intent['base_ref']['archive_sha256'] == base['sha256'] and
                pub['F_query']['version_ref']['archive_sha256'] == cp['sha256'] and
                same(pub['F_query']['version_ref'], pub['installation_ref']['version_ref']),
                'original base or full published archive differs')
        old, new = outbox(base, 'bytes'), outbox(cp, 'size')
        require(new.startswith(old), 'ordinary outbox rewrote or removed the original prefix')
        before, after = rows(old), rows(new)
        delta = after[len(before):]
        if len(delta) > MAX_NEW:
            fail('invalid', 'new outbox record budget exceeded')
        return source, delta

    async def publish(self, effect_id, binding, publication_ref):
        """Write port, never called by a read-only query; no local retry loop or ledger."""
        try:
            source, delta = self._source(effect_id, binding, publication_ref)
        except EventError:
            raise
        except (KeyError, TypeError, OSError, FileError) as exc:
            fail('reference_invalid', 'original tool/outbox source invalid: ' + str(exc))
        except ValueError as exc:
            fail('invalid', 'ordinary outbox invalid: ' + str(exc))
        results = []
        for record in delta:
            id = 'emit-' + sha(encode([source['namespace'], binding['operation_id'], effect_id, record['id']]))
            # E alone grants first dispatch. The same accepted/unknown ID never gets a second PUB here.
            result = await self.events.submit(source['principal'], id, source['namespace'],
                                              record['name'], record['payload'])
            results.append(copy.deepcopy(result))
            if result['status'] in ('UNKNOWN', 'ACCEPTED'):
                break
        return results
