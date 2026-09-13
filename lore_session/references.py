"""Read an original Pi result from a confirmed S archive; never run policy or effects."""
import copy
import json
import re

from .snapshots import SnapshotStore
from .snapshot_files import (SnapshotError, SCOPE, CONTROL_LIMIT, archive, canonical,
                             decode, member_name, read_ref, session_original, sha)

REF_KEYS = {'owner', 'session_scope', 'session_id', 'operation_id', 'kind',
            'result_sha256', 'session_relative_path', 'session_sha256', 'session_bytes', 'session_range'}
BINDING_KEYS = {'session_id', 'session_scope', 'operation_id', 'harness_ref',
                'input_ref', 'source_result_ref', 'capability_ref'}
DECODER = json.JSONDecoder()


def require(value, message):
    if not value:
        raise SnapshotError('reference_invalid', message)


def same(a, b):
    return canonical(a) == canonical(b)


def space(text, position):
    while position < len(text) and text[position] in ' \t\r\n':
        position += 1
    return position


def value_bytes(text):
    """Extract the actual top-level value token, preserving JSON.stringify byte order.

    The complete transaction was already strictly decoded. raw_decode supplies
    lexical endpoints; braces/escaped keys/strings are not searched with regex.
    """
    require(text.startswith('{'), 'original transaction member is not an object')
    position = space(text, 1)
    while position < len(text) and text[position] != '}':
        key, end = DECODER.raw_decode(text, position)
        require(type(key) is str, 'original object key is not text')
        position = space(text, end)
        require(text[position] == ':', 'original object separator missing')
        start = space(text, position+1)
        _, end = DECODER.raw_decode(text, start)
        if key == 'value':
            return text[start:end].encode('utf8')
        position = space(text, end)
        if text[position] == ',':
            position = space(text, position+1)
        else:
            require(text[position] == '}', 'original object terminator missing')
    return None


def rows(raw):
    """Yield original rows and raw value tokens with their full transaction bounds."""
    offset = 0
    for number, line in enumerate(raw.splitlines(keepends=True)):
        start, offset = offset, offset+len(line)
        if number == 0:
            continue  # metadata/header checked by session_original
        transaction = decode(line)
        text = line.decode('utf8'); position = space(text, 0)
        members = transaction if type(transaction) is list else [transaction]
        if type(transaction) is list:
            position = space(text, position+1)
        for row in members:
            require(type(row) is dict, 'original transaction row is not an object')
            _, end = DECODER.raw_decode(text, position)
            token = value_bytes(text[position:end])
            yield row, token, start, offset
            position = space(text, end)
            if type(transaction) is list and text[position] == ',':
                position = space(text, position+1)


def validate_arguments(reference, binding):
    require(type(reference) is dict and set(reference) == REF_KEYS, 'complete exact original locator required')
    require(type(binding) is dict and set(binding) == BINDING_KEYS, 'complete accepted binding required')
    scope = binding['session_scope']
    require(type(scope) is dict and set(scope) == set(SCOPE), 'complete Session scope required')
    require(all(type(scope[k]) is str and scope[k] for k in SCOPE[:-1]) and
            type(scope['session_generation']) is int and scope['session_generation'] > 0, 'invalid Session scope')
    require(type(binding['operation_id']) is str and 0 < len(binding['operation_id']) <= 256 and
            binding['session_id'] == scope['session_id'], 'invalid original operation binding')
    require(reference['owner'] == 'S' and reference['kind'] == 'pi-operation-result' and
            same(reference['session_scope'], scope) and reference['session_id'] == binding['session_id'] and
            reference['operation_id'] == binding['operation_id'], 'locator differs from accepted identity')
    require(all(type(reference[k]) is str and re.fullmatch('[0-9a-f]{64}', reference[k])
                for k in ('result_sha256', 'session_sha256')), 'invalid original digest')
    length = reference['session_bytes']; span = reference['session_range']
    require(type(length) is int and length > 0 and type(span) is list and
            all(type(x) is int for x in span) and span == [0, length], 'invalid original prefix range')
    require(member_name(reference['session_relative_path']) == reference['session_relative_path'], 'noncanonical Session member')
    canonical(binding)


def parse_result(raw, reference, binding):
    length, op = reference['session_bytes'], binding['operation_id']
    require(length <= len(raw) and raw[:length].endswith(b'\n'), 'prefix is outside complete original transactions')
    require(sha(raw[:length]) == reference['session_sha256'], 'original Session prefix digest differs')
    values, result, boundary = {}, None, None
    seen_result = seen_binding = 0
    prefix_values = None
    for row, token, start, end in rows(raw):
        if row.get('kind') != 'value':
            continue
        namespace, key = row['namespace'], row['key']; address = (namespace, key)
        if key == op and namespace in ('lore.s.binding', 'pi.result'):
            require(end <= length, 'original binding/result was rewritten after its saved prefix')
            require(row['op'] == 'set', 'original binding/result was deleted')
            if namespace == 'lore.s.binding':
                seen_binding += 1
                require(seen_binding == 1 and same(row['value'], binding), 'original accepted binding differs or was replaced')
            else:
                seen_result += 1
                require(seen_result == 1 and token is not None and sha(token) == reference['result_sha256'], 'original Pi result bytes differ')
                result = row['value']
                require(type(result) is dict and result.get('operationId') == op, 'original result belongs to another operation')
        if key == op and namespace == 'lore.s.boundary':
            require(start >= length and row['op'] == 'set' and boundary is None, 'original boundary order or mutation differs')
            boundary = row['value']
            require(type(boundary) is dict and same(boundary.get('operation_result_ref'), reference), 'boundary uses another original locator')
            if 'decision_proposal' in boundary:
                proposal = boundary['decision_proposal']
                require(type(proposal) is dict and type(proposal.get('decision_id')) is str and proposal['decision_id'] and
                        same(proposal.get('source_result_ref'), reference) and same(proposal.get('harness_ref'), binding['harness_ref']) and
                        same(proposal.get('input_ref'), binding['input_ref']), 'saved external proposal association differs')
        if row['op'] == 'delete':
            values.pop(address, None)
        else:
            values[address] = row['value']
        if end <= length:
            prefix_values = copy.deepcopy(values)
    require(result is not None and seen_binding == 1 and prefix_values is not None, 'original saved result or binding is missing')
    require(('pi.op.meta', op) not in prefix_values and ('pi.op.state', op) not in prefix_values and
            prefix_values.get(('pi.lane.state', 'main'), {}).get('currentOperationId') != op,
            'original result contradicts pending operation state')
    return result, boundary


def resolve_original(snapshots, confirmation_request_id, original_ref, expected_binding):
    """Resolve original data only; a missing boundary never erases an existing result.

    snapshots and expected_binding are supplied by the trusted caller. The result
    locator does not grant access or select a new unconfirmed owner directory.
    """
    try:
        require(isinstance(snapshots, SnapshotStore), 'trusted SnapshotStore required')
        reference, binding = copy.deepcopy((original_ref, expected_binding))
        validate_arguments(reference, binding)
        confirmed = snapshots.query(confirmation_request_id)
        owner = decode(read_ref(confirmed['owner_record_ref'], CONTROL_LIMIT)[1])
        require(same(owner['scope'], binding['session_scope']), 'confirmed owner belongs to another Session scope')
        full = confirmed['snapshot_ref']
        _, raw_archive = read_ref(dict(path=full['archive_path'], sha256=full['archive_sha256'], bytes=full['archive_bytes']))
        _, files, _ = archive(raw_archive)
        original = owner['original_session']
        require(original['jsonl'] is not None and original['metadata'] is not None and
                original['jsonl']['relative_path'] == reference['session_relative_path'], 'original Session member differs or is empty')
        descriptor = dict(jsonl_relative_path=reference['session_relative_path'],
                          metadata_relative_path=original['metadata']['relative_path'],
                          binding_namespace='lore.s.binding', binding_key=binding['operation_id'], binding=binding)
        session_original(files, descriptor, binding['session_scope'])
        result, boundary = parse_result(files[reference['session_relative_path']], reference, binding)
        return copy.deepcopy(dict(reference=reference, binding=binding, operation_result=result, boundary=boundary,
             snapshot_ref=full, owner_record_ref=confirmed['owner_record_ref'], storage_charge_ref=confirmed['storage_charge_ref']))
    except SnapshotError as error:
        if error.code == 'reference_invalid':
            raise
        raise SnapshotError('reference_invalid', 'original snapshot verification failed: '+str(error)) from error
    except (OSError, KeyError, TypeError, ValueError, UnicodeError, RecursionError, IndexError) as error:
        raise SnapshotError('reference_invalid', 'invalid original reference: '+str(error)) from error
