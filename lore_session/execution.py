"""Trusted S transport over one original X owner; Pi remains the operation history."""
import base64
import copy
from pathlib import PurePosixPath

from .snapshot_files import (archive, canonical, decode, require, sha, EXEC, SCOPE)


def original_descriptor(raw, scope, operation_id):
    """Select an existing original binding; never synthesize one from a new request."""
    _, files, _ = archive(raw)
    metadata = decode(files['metadata.json'])
    path = PurePosixPath(metadata['path']).relative_to(metadata['cwd']).as_posix()
    values = {}
    for line in files[path].splitlines()[1:]:
        transaction = decode(line)
        for row in transaction if isinstance(transaction, list) else [transaction]:
            if row.get('kind') == 'value' and row.get('namespace') == 'lore.s.binding':
                if row['op'] == 'set':
                    values[row['key']] = row['value']
                else:
                    values.pop(row['key'], None)
    require(values, 'original Session has no confirmed binding')
    key = operation_id if operation_id in values else next(reversed(values))
    binding = values[key]
    require(binding['session_scope'] == scope and binding['session_id'] == scope['session_id'],
            'original binding belongs to another Session')
    return dict(jsonl_relative_path=path, metadata_relative_path='metadata.json',
                binding_namespace='lore.s.binding', binding_key=key, binding=binding)


def session_reference(confirmation):
    require(type(confirmation) is dict and 'quarantine_ref' not in confirmation,
            'quarantine is not a healthy Session reference')
    full = confirmation['snapshot_ref']
    return dict(owner='S', session_id=full['session_id'], namespace=full['namespace'],
                session_generation=full['session_generation'], snapshot_ref=copy.deepcopy(full),
                original_archive={k:full['archive_'+k] for k in ('path', 'sha256', 'bytes')},
                owner_record_ref=copy.deepcopy(confirmation['owner_record_ref']),
                storage_charge_ref=copy.deepcopy(confirmation['storage_charge_ref']))


class SessionRun:
    """A live invocation handle, not a durable Session status cache or scheduler.

    request and authority are built by the trusted registration/F resolver before
    this handle is created. They are never taken from Node/provider tool frames.
    """
    def __init__(self, execution, snapshots, request, authority, operation_id):
        require(request.get('schema_version') == 2 and request.get('domain') == 'session',
                'original internal Session plan required')
        self.x, self.owners = execution, snapshots
        self.request, self.authority = copy.deepcopy((request, authority))
        self.id, self.op = request['execution_id'], operation_id
        self.scope = copy.deepcopy(request['session_binding'])
        self.binding = None
        self.latest = None
        self.confirmations = {}
        self.quarantines = {}
        self.pending_confirmation = None

    def start(self):
        result = self.x.execute(self.request, self.authority)
        self.binding = copy.deepcopy(result['binding'])
        return result

    def write(self, raw, fields):
        require(isinstance(raw, bytes) and len(raw) <= 1048576, 'bounded exact input required')
        result = self.x.channel_write(self.id, self.authority, raw, fields)
        require(not result.get('error'), 'original write is unresolved; do not replay', 'paused_unknown')
        original = decode(self.x.journal.read(result['call_ref'], 2097152))
        require(original['state'] == 'CONFIRMED' and original['written_bytes'] == len(raw),
                'original write is not fully confirmed', 'paused_unknown')
        return result

    def read(self, maximum, calls):
        output = {}; result = None; stdout_end = calls['stdout']['byte_offset']
        # Calls and offsets belong to the original caller. A lost reply is queried at the same identity.
        for stream in ('stdout', 'stderr'):
            if stream == 'stderr' and result['result']['output_state'] == 'PENDING':
                output[stream+'_b64'] = ''
                continue
            fields = calls[stream]
            result = self.x.channel_read(self.id, self.authority, stream, maximum, fields)
            raw = base64.b64decode(result['data_base64'], validate=True)
            require(result['byte_offset'] == fields['byte_offset'] and result['next_byte_offset'] == fields['byte_offset']+len(raw),
                    'original stream range differs')
            if stream == 'stdout':
                stdout_end = result['next_byte_offset']
            output[stream+'_b64'] = result['data_base64']
        terminal = result['result']['output_state'] != 'PENDING'
        output['stdout_eof'] = terminal and stdout_end >= result['artifacts'].get('stdout', {}).get('size', 0)
        return output

    def close_stdin(self, fields):
        return self.x.close_stdin(self.id, self.authority, fields)

    def checkpoint(self, checkpoint_id, purpose='original_session'):
        require(not self.quarantines and self.pending_confirmation is None,
                'prior frozen checkpoint must be retained before another capture')
        result = self.x.checkpoint(self.id, self.authority, checkpoint_id, purpose)
        self.binding = copy.deepcopy(result['binding'])
        full = result['artifacts']['checkpoint']
        self.pending_confirmation = dict(checkpoint_id=checkpoint_id, full=copy.deepcopy(full))
        if checkpoint_id not in self.confirmations:
            raw = self.x.journal.read(full, 18874368)
            descriptor = original_descriptor(raw, self.scope, self.op)
            expected = dict(**self.scope, original_execution={**{k:full['source_binding'][k] for k in EXEC}, 'state':full['state']})
            confirmation = self.owners.confirm('s-'+sha(canonical([self.id, checkpoint_id])), expected, full, descriptor)
            self.pending_confirmation = None
            if self.latest is not None and self.latest['full'] != full:
                previous = self.latest
                receipt = self.owners.receipt('s-successor-'+sha(canonical([previous['full'], full])),
                                              previous['full'], previous['confirmation'], full, confirmation)
                self.x.release_checkpoint(self.id, self.authority, receipt['receipt_id'], previous['full'], receipt)
            self.confirmations[checkpoint_id] = dict(full=full, confirmation=confirmation)
        self.latest = self.confirmations[checkpoint_id]
        self.pending_confirmation = None
        return dict(receipt=copy.deepcopy(full),
                    prepared_artifact=dict(path=full['path'], sha256=full['sha256'], bytes=full['size']),
                    original_session_snapshot_ref=session_reference(self.latest['confirmation']))

    def quarantine(self, checkpoint_id, reason):
        """Retain an unadmitted original checkpoint without creating a Session ref."""
        require(self.pending_confirmation is None, 'retain the existing original checkpoint first')
        result = self.x.checkpoint(self.id, self.authority, checkpoint_id, 'raw_failed_input')
        self.binding = copy.deepcopy(result['binding'])
        self.pending_confirmation = dict(checkpoint_id=checkpoint_id,
                                         full=copy.deepcopy(result['artifacts']['checkpoint']))
        return self.quarantine_pending(reason)

    def quarantine_pending(self, reason):
        """Transfer exactly the original frozen bytes, with no further X capture."""
        require(self.pending_confirmation is not None, 'no original pending checkpoint')
        checkpoint_id = self.pending_confirmation['checkpoint_id']
        full = self.pending_confirmation['full']
        expected = dict(**self.scope, original_execution={**{k:full['source_binding'][k] for k in EXEC}, 'state':full['state']})
        confirmation = self.owners.quarantine('s-quarantine-'+sha(canonical([self.id, checkpoint_id])), expected, full, reason)
        self.quarantines[checkpoint_id] = dict(full=full, confirmation=confirmation)
        self.pending_confirmation = None
        return dict(receipt=copy.deepcopy(full), retained_quarantine=copy.deepcopy(confirmation))

    def resume(self, receipt):
        require(not self.quarantines and self.pending_confirmation is None,
                'unadmitted original checkpoint cannot resume')
        return self.x.resume(self.id, self.authority, receipt)

    def request_stop(self, stop_id):
        return self.x.request_stop(self.id, self.authority, stop_id)

    def seal(self, receipt):
        return self.x.seal(self.id, self.authority, receipt)

    def release(self):
        retained = ([self.latest] if self.latest is not None else []) + list(self.quarantines.values())
        for old in retained:
            receipt = self.owners.receipt('s-sealed-'+sha(canonical(old['full'])), old['full'], old['confirmation'], sealed=True)
            self.x.release_checkpoint(self.id, self.authority, receipt['receipt_id'], old['full'], receipt)
        return self.x.release(self.id, self.authority)
