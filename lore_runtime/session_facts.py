"""Read-only projection of original X release and normal S ownership; no ledger."""
import copy
from pathlib import Path

from lore_execution.errors import ExecutionError
from lore_session.execution import session_reference
from lore_session.references import resolve_original
from lore_session.snapshots import SnapshotStore
from lore_session.snapshot_files import (CONTROL_LIMIT, RAW_LIMIT, EXEC, SCOPE,
    SnapshotError, canonical, decode, file_fact, read_ref, sha)
from lore_session.transport import original

KEYS = {'owner', 'kind', 'execution_id', 'node_request_digest', 'confirmation_request_id',
        'session_confirmation', 'original_stopped_response', 'original_execution_response'}


def require(value, message):
    if not value:
        raise SnapshotError('reference_invalid', message)


def same(a, b):
    return canonical(a) == canonical(b)


class SessionFacts:
    def __init__(self, snapshots, execution_root, engine):
        require(isinstance(snapshots, SnapshotStore), 'trusted normal SnapshotStore required')
        root = Path(execution_root)
        require(root.is_absolute() and root.resolve() == root and root.is_dir(), 'existing unaliased X root required')
        self.snapshots, self.root, self.engine = snapshots, root, engine

    def _blob(self, reference, limit=RAW_LIMIT):
        path = Path(reference['path'])
        require(path.is_absolute() and path.is_relative_to(self.root), 'X reference escaped original root')
        return read_ref(dict(path=str(path), bytes=reference['size'], sha256=reference['sha256']), limit)[1]

    def _slot(self, reference, binding, released):
        slot = decode(self._blob(reference, CONTROL_LIMIT))
        registration = slot['registration']; reservation = slot['reservations'][binding['slot_reservation_id']]
        require(registration['slot_id'] == slot['slot_id'] == binding['slot_id'] and
                registration['revision'] == slot['revision'] == binding['slot_revision'] and
                registration['namespace'] == binding['namespace'], 'original slot scope differs')
        require(reservation['id'] == binding['slot_reservation_id'] and reservation['role'] == 'session' and
                all(reservation[k] == binding[k] for k in ('execution_id', 'object_generation', 'request_digest')),
                'original slot reservation belongs to another execution')
        require(not released or reservation['state'] == 'RELEASED', 'original release response lacks released role')
        # These are original per-call snapshots, not the later mutable global totals.

    def _response(self, record, response, released):
        require(type(response) is dict and set(response) == {'binding', 'result', 'artifacts'}, 'complete native X response required')
        require(all(same(response[k], record[k]) for k in ('binding', 'result')), 'native X binding/result changed')
        without_slot = lambda a: {k:v for k,v in a.items() if k != 'slot'}
        require(same(without_slot(response['artifacts']), without_slot(record['artifacts'])), 'native original output references changed')
        self._slot(response['artifacts']['slot'], record['binding'], released)

    def _request(self, record, node_request, execution_id):
        request, binding = record['request'], record['binding']
        require(type(node_request) is dict and node_request.get('protocol') == 'lore.s/1' and
                node_request.get('action') in ('accept', 'drive', 'query'), 'original Session action required')
        require(request['schema_version'] == 2 and request['domain'] == binding['domain'] == 'session' and
                request['execution_id'] == binding['execution_id'] == execution_id and
                request['invocation_id'] == node_request['operation_id'] and
                binding['request_digest'] == sha(canonical(request)), 'original X request association differs')
        scope = request['session_binding']
        require(set(scope) == set(SCOPE) and all(binding[k] == scope[k] for k in SCOPE) and
                binding['target_id'] == scope['session_id'] and same(request['source_result'], node_request['source_result_ref']),
                'original invocation/Session source differs')
        ref = node_request['session_ref']
        require(ref['owner'] == 'S' and ref['session_id'] == scope['session_id'] and
                all(k not in ref or ref[k] == scope[k] for k in SCOPE), 'Node Session scope differs')
        if 'snapshot_ref' in ref:
            require(same(ref['snapshot_ref'], request['snapshot_ref']), 'Node selected another original Session input')
        # The original complete first write binds action, all compact refs and the full input envelope.
        raw = canonical(node_request)+b'\n'
        candidates = [c for c in record['calls'].values() if c['request'].get('method') == 'channel_write' and c['request'].get('byte_offset') == 0]
        require(len(candidates) == 1, 'original first Node write absent or ambiguous')
        call = candidates[0]; body = decode(self._blob(call['ref'], CONTROL_LIMIT))
        require(same(body, call['body']) and body['state'] == 'CONFIRMED' and
                body['written_bytes'] == body['data_bytes'] == len(raw) and body['data_sha256'] == sha(raw),
                'complete original Node input was not confirmed')
        require(all(body[k] == call['request'][k] == binding[k] for k in
                    ('execution_id', 'object_generation', 'request_digest', 'channel_id')) and
                all(body[k] == call['request'][k] for k in ('method', 'call_id', 'byte_offset', 'data_bytes', 'data_sha256')),
                'original input call belongs to another execution')
        return dict(session_id=scope['session_id'], session_scope=copy.deepcopy(scope),
                    **{k:copy.deepcopy(node_request[k]) for k in
                       ('operation_id', 'harness_ref', 'input_ref', 'source_result_ref', 'capability_ref')})

    def _retention(self, record, bundle, owner):
        checkpoint = record['artifacts']['checkpoint']; binding = record['binding']
        require(owner['source'] == {'kind':'checkpoint', 'original_checkpoint_full_ref':checkpoint}, 'normal owner came from another checkpoint')
        require(checkpoint['owner'] == 'X' and checkpoint['state'] == 'PREPARED' and
                all(checkpoint[k] == binding[k] for k in ('execution_id','object_generation','freeze_generation')) and
                same(checkpoint['source_binding'], binding), 'original complete checkpoint binding differs')
        retained = bundle['snapshot_ref']
        require(retained['archive_sha256'] == checkpoint['sha256'] and retained['archive_bytes'] == checkpoint['size'], 'retained bytes differ from original X checkpoint')
        matches = [c for c in record['checkpoints'].values() if same(c.get('artifact'), checkpoint)]
        require(len(matches) == 1, 'normal owner has no unique original checkpoint')
        retention = matches[0]['retention']; receipt = retention['owner_receipt_ref']
        require(retention['state'] == 'RELEASED' and receipt['receipt_id'] == retention['release_id'], 'original checkpoint handoff incomplete')
        receipt_body = {k:v for k,v in receipt.items() if k != 'actual_owner_receipt_path_sha_bytes'}
        require(same(decode(read_ref(receipt['actual_owner_receipt_path_sha_bytes'], CONTROL_LIMIT)[1]), receipt_body), 'original owner receipt bytes differ')
        require(receipt['owner'] == 'S' and receipt['handoff_kind'] == 'sealed_ownership_transfer' and
                same(receipt['old_checkpoint_full_ref'], checkpoint) and same(receipt['retained_original_ref'], retained) and
                same(receipt['retained_owner_record_ref'], bundle['owner_record_ref']) and
                same(receipt['storage_charge_ref'], bundle['storage_charge_ref']) and
                receipt['confirmed_successor_full_ref'] is None and receipt['successor_owner_record_ref'] is None and
                all(receipt[k] == binding[k] for k in ('namespace','session_id','session_generation')), 'original sealed owner handoff differs')
        proof = decode(self._blob(record['artifacts']['stopped'], CONTROL_LIMIT))
        require(proof['owner'] == 'X' and proof['kind'] == 'stopped' and
                all(proof[k] == binding[k] for k in ('execution_id','object_generation','target_id','domain','container_id','exec_id')) and
                proof['binding_generation'] == binding['session_generation'] and proof['base_version'] == record['request']['base_version'] and
                same(proof['prepared_ref'], checkpoint) and
                (proof['engine_state'] is None or proof['engine_state']['Running'] is False), 'original stop proof differs from frozen source')

    def _read(self, facility, node_request):
        require(type(facility) is dict and set(facility) == KEYS and
                facility['owner'] == 'X' and facility['kind'] == 'session_execution', 'complete Session facility projection required')
        execution_id = facility['execution_id']
        require(type(execution_id) is str and 0 < len(execution_id.encode()) <= 256, 'bounded original execution identity required')
        require(facility['node_request_digest'] == sha(canonical(node_request)), 'complete Node request digest differs')
        record_path = self.root/sha(execution_id.encode())/'record.json'
        record = decode(file_fact(record_path, CONTROL_LIMIT)[1])
        binding = self._request(record, node_request, execution_id)
        require(record.get('released') is True and record['result']['execution_state'] == 'STOPPED' and
                record['result']['output_state'] != 'PENDING', 'original X execution is not durably released')
        self._response(record, facility['original_stopped_response'], False)
        self._response(record, facility['original_execution_response'], True)
        confirmation_id = facility['confirmation_request_id']; bundle = self.snapshots.query(confirmation_id)
        require(same(bundle, facility['session_confirmation']), 'original confirmation bundle differs')
        owner = decode(read_ref(bundle['owner_record_ref'], CONTROL_LIMIT)[1])
        require(same(owner['scope'], binding['session_scope']) and same(owner['original_session']['binding'], binding), 'original confirmed Session binding differs')
        self._retention(record, bundle, owner)
        require(self.engine.inspect(record['binding']['container_id']) is None and
                self.engine.call('GET', '/volumes/'+record['binding']['volume_id'], missing=True) is None,
                'original released physical objects remain present')
        stdout = self._blob(record['artifacts']['stdout'], 1048576); self._blob(record['artifacts']['stderr'], 1048576)
        require(stdout and stdout.endswith(b'\n'), 'original result stream is incomplete')
        frames = [decode(line) for line in stdout.splitlines()]
        results = [f for f in frames if type(f) is dict and f.get('type') == 'result']
        require(len(results) == 1 and same(results[0], frames[-1]), 'original terminal result absent or ambiguous')
        frame = results[0]; op = binding['operation_id']
        require(frame.get('operation_id') == op, 'original terminal result belongs to another operation')
        observed = original(self.snapshots, {'original_session_snapshot_ref':session_reference(bundle)}, binding)
        if 'operation_result_ref' in frame:
            resolved = resolve_original(self.snapshots, confirmation_id, frame['operation_result_ref'], binding)
            expected = (dict(type='result', operation_id=op, **resolved['boundary']) if resolved['boundary'] is not None else
                        dict(type='result', operation_id=op, boundary_kind='paused_reconciliation_required', operation_result_ref=frame['operation_result_ref']))
            require(same(frame, expected), 'raw result differs from saved boundary or invents a missing decision')
        else:
            values = observed['values']
            require(node_request['action'] in ('accept','query') and ('pi.result',op) not in values and
                    values.get(('pi.op.meta',op),{}).get('operationId') == op and ('pi.op.state',op) in values and
                    values.get(('pi.lane.state','main'),{}).get('currentOperationId') == op and
                    same(frame,dict(type='result',operation_id=op,boundary_kind='accepted')), 'raw acceptance lacks original Pi admission')
        return copy.deepcopy(dict(frame=frame,binding=binding,bundle=bundle,confirmation_request_id=confirmation_id))

    def read(self, facility, node_request):
        try:
            return self._read(copy.deepcopy(facility), copy.deepcopy(node_request))
        except (SnapshotError, ExecutionError, OSError, KeyError, TypeError, ValueError, UnicodeError, IndexError) as error:
            if isinstance(error, SnapshotError) and error.code == 'reference_invalid':
                raise
            raise SnapshotError('reference_invalid', 'unavailable or invalid original Session fact: '+str(error)) from error

    def facility(self, node_request, execution_id, confirmation_request_id, stopped, released):
        try:
            bundle = self.snapshots.query(confirmation_request_id)
        except SnapshotError as error:
            raise SnapshotError('reference_invalid', 'normal original confirmation unavailable: '+str(error)) from error
        result = copy.deepcopy(dict(owner='X',kind='session_execution',execution_id=execution_id,
            node_request_digest=sha(canonical(node_request)),confirmation_request_id=confirmation_request_id,
            session_confirmation=bundle,original_stopped_response=stopped,original_execution_response=released))
        self.read(result,node_request)
        return result
