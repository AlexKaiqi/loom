"""Bounded original X channel and read-only original Session frame guards."""
import base64
import copy
import time

from .references import rows
from .snapshot_files import (CONTROL_LIMIT, SnapshotError, archive, canonical, decode,
                             read_ref, session_original, sha)


def require(value, message):
    if not value:
        raise SnapshotError('invalid_frame', message)


def same(a, b):
    return canonical(a) == canonical(b)


class SessionChannel:
    def __init__(self, run):
        self.run = run
        self.buffer = b''
        self.stderr = b''
        self.offsets = dict(stdin=0, stdout=0, stderr=0)
        self.serial = 0
        self.eof = False

    def fields(self, method, call_id, offset):
        return dict(method=method, call_id=call_id, byte_offset=offset,
                    **{k:self.run.binding[k] for k in
                       ('execution_id', 'object_generation', 'channel_id', 'request_digest')})

    def write(self, frame):
        raw = canonical(frame)+b'\n'
        require(len(raw) <= 1048576, 'control frame exceeds byte limit')
        offset = self.offsets['stdin']
        result = self.run.write(raw, self.fields('channel_write', 's-write-'+str(offset)+'-'+sha(raw), offset))
        self.offsets['stdin'] += len(raw)  # A failed/unconfirmed write never advances or retries.
        return result

    def next(self, deadline):
        while b'\n' not in self.buffer:
            if self.eof or time.monotonic() >= deadline:
                raise SnapshotError('paused_unknown', 'original channel ended or deadline elapsed before a complete frame')
            calls = {s:self.fields('channel_read', 's-read-'+s+'-'+str(self.serial), self.offsets[s])
                     for s in ('stdout', 'stderr')}
            chunk = self.run.read(65536, calls)
            self.serial += 1
            for stream in ('stdout', 'stderr'):
                raw = base64.b64decode(chunk[stream+'_b64'], validate=True)
                require(len(raw) <= 65536, 'original read exceeds requested range')
                self.offsets[stream] += len(raw)
                if stream == 'stdout': self.buffer += raw
                else: self.stderr += raw
            self.eof = bool(chunk['stdout_eof'])
            require(len(self.buffer) <= 1048576 and len(self.stderr) <= 1048576,
                    'bounded control or stderr stream exceeded')
            if not self.buffer and not self.eof: time.sleep(0.01)
        line, self.buffer = self.buffer.split(b'\n', 1)
        frame = decode(line)
        require(type(frame) is dict, 'control frame must be an object')
        return frame

    def close(self):
        return self.run.close_stdin(self.fields('close_stdin', 's-explicit-eof', self.offsets['stdin']))


def original(snapshots, checkpoint, binding):
    envelope = checkpoint['original_session_snapshot_ref']
    owner = decode(read_ref(envelope['owner_record_ref'], CONTROL_LIMIT)[1])
    confirmation_id = owner['confirmation_request_id']
    confirmed = snapshots.query(confirmation_id)
    require(same(confirmed['snapshot_ref'], envelope['snapshot_ref']) and
            same(confirmed['owner_record_ref'], envelope['owner_record_ref']) and
            same(confirmed['storage_charge_ref'], envelope['storage_charge_ref']), 'confirmed owner envelope differs')
    require(same(owner['scope'], binding['session_scope']), 'confirmed owner scope differs')
    _, raw = read_ref(envelope['original_archive'])
    _, files, _ = archive(raw)
    saved = owner['original_session']
    require(saved and saved['jsonl'] and saved['metadata'], 'no original Session binding')
    path = saved['jsonl']['relative_path']
    descriptor = dict(jsonl_relative_path=path, metadata_relative_path=saved['metadata']['relative_path'],
                      binding_namespace='lore.s.binding', binding_key=binding['operation_id'], binding=binding)
    session_original(files, descriptor, binding['session_scope'])
    values, entries, bindings = {}, {}, []
    for row, _, _, _ in rows(files[path]):
        if row.get('kind') == 'entry': entries[row['id']] = row
        if row.get('kind') != 'value': continue
        address = (row['namespace'], row['key'])
        if address == ('lore.s.binding', binding['operation_id']): bindings.append(row)
        if row['op'] == 'delete': values.pop(address, None)
        else: values[address] = row['value']
    require(len(bindings) == 1 and bindings[0]['op'] == 'set' and
            same(bindings[0]['value'], binding), 'original full binding differs or was replaced')
    return dict(confirmation_request_id=confirmation_id, values=values, entries=entries)


def pending(observed, binding, frame):
    """Guard only the fixed public Pi pending protocol; target authority is injected."""
    kind = 'provider' if frame['type'].startswith('provider.') else 'tool'
    request = frame['type'].endswith('.request')
    common = {'type', 'session_id', 'operation_id', 'effect_id'}
    additions = ({'response_entry_id', 'payload'} if kind == 'provider' else
                 {'invocation_id', 'source_result_ref', 'request'}) if request else set()
    require(set(frame) == common|additions and frame['session_id'] == binding['session_id'] and
            frame['operation_id'] == binding['operation_id'], 'callback fields or scope differ')
    op = binding['operation_id']; values = observed['values']
    state = values.get(('pi.op.state', op), {})
    meta = values.get(('pi.op.meta', op), {})
    require(meta.get('operationId') == op and meta.get('lane') == 'main' and
            values.get(('pi.lane.state', 'main'), {}).get('currentOperationId') == op and
            ('pi.result', op) not in values, 'original operation is not pending')
    if kind == 'provider':
        require(state.get('at') == 'assistant.effect_pending', 'original provider is not pending')
        reserved = state.get('responseEntryId')
    else:
        batch = state.get('batch', {}); calls = batch.get('calls', [])
        require(state.get('at') == 'tools' and len(calls) == 1 and
                calls[0].get('status') == 'effect_pending', 'single original tool is not pending')
        call = calls[0]; reserved = call.get('resultEntryId'); index = call.get('sourceIndex')
        message = observed['entries'].get(batch.get('assistantEntryId'), {}).get('message', {})
        content = message.get('content', [])
        require(message.get('role') == 'assistant' and message.get('stopReason') == 'toolUse' and
                type(index) is int and 0 <= index < len(content) and
                len([v for v in content if v.get('type') == 'toolCall']) == 1,
                'original native tool response is incomplete or has multiple calls')
        native = content[index]
        require(native.get('type') == 'toolCall' and native.get('name') == 'shell' and
                type(native.get('id')) is str and native['id'], 'original native tool association differs')
        if request:
            address = ('pi.op.tool_args', op+':'+batch['turnId']+':'+str(index))
            require(address in values and same(frame['request'], values[address]) and
                    same(frame['source_result_ref'], binding['source_result_ref']),
                    'frame differs from persisted original delegated arguments/source')
    require(type(reserved) is str and reserved and
            frame['effect_id'] == 's-'+kind+'-'+sha(canonical([binding['session_scope'], op, reserved])),
            'stable original effect identity differs')
    if request:
        require(frame['response_entry_id' if kind == 'provider' else 'invocation_id'] == reserved,
                'reserved original entry identity differs')
    return {**copy.deepcopy(binding), **({'response_entry_id':reserved} if kind == 'provider' else {})}
