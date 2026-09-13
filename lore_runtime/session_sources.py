"""Readonly original R/S reference glue; no Session ledger, replay or policy."""
import copy

from lore_control.values import identifier
from lore_session.references import require, resolve_original, rows, same
from lore_session.snapshot_files import SCOPE, CONTROL_LIMIT, archive, decode, read_ref, sha
from .session_delivery import execution_id, confirmation_id
from .session_plan_files import compact


class SessionSources:
    def __init__(self, control, snapshots, delivery, initial_session_ref):
        initial = copy.deepcopy(initial_session_ref)
        require(type(initial) is dict and set(initial) == {'owner', *SCOPE, 'confirmation_request_id'} and
                initial['owner'] == 'S' and initial['confirmation_request_id'] is None,
                'complete trusted initial Session reference required')
        scope = {k:initial[k] for k in SCOPE}
        self._scope(scope)
        require(scope['namespace'] == snapshots.namespace and delivery.control is control,
                'trusted R/S owners differ')
        self.control, self.snapshots, self.delivery = control, snapshots, delivery
        self.initial = initial
        self.principal = delivery.principal

    @staticmethod
    def _scope(scope):
        require(type(scope) is dict and set(scope) == set(SCOPE) and
                all(type(scope[k]) is str and scope[k] for k in SCOPE[:-1]) and
                type(scope['session_generation']) is int and scope['session_generation'] > 0,
                'complete original Session scope required')

    def _row(self, id):
        identifier(id)
        # A resolver may already run in an original R reference-check transaction.
        # Match query authority without starting or ending a nested transaction.
        with self.control._lock:
            row = self.control._get_request(id)
            self.control._authorize(self.principal, row['namespace'])
            return self.control._request_value(row)

    def _parent(self, supplied):
        require(type(supplied) is dict, 'original invocation required')
        parent = self._row(supplied['id'])
        require(parent['kind'] == 'invocation' and all(same(parent[k], supplied[k]) for k in
                ('principal', 'id', 'namespace', 'kind', 'payload')), 'supplied invocation differs from original R')
        return parent

    def _healthy(self, actual, parent, node):
        binding, scope = actual['binding'], actual['binding']['session_scope']
        self._scope(scope)
        require(scope['namespace'] == parent['namespace'] and scope['surface_id'] == parent['payload']['resource_id'] and
                binding['session_id'] == scope['session_id'] and binding['operation_id'] == parent['id'] and
                all(same(binding[k], node[k]) for k in ('harness_ref','input_ref','source_result_ref','capability_ref')) and
                same(binding['harness_ref'], compact(parent['payload']['harness_ref'])) and
                same(binding['capability_ref'], compact(parent['payload']['capability_ref'])),
                'original compact binding or Session owner differs from R parent')
        bundle = self.snapshots.query(actual['confirmation_request_id'])
        owner = decode(read_ref(bundle['owner_record_ref'], CONTROL_LIMIT)[1])
        require(same(bundle, actual['bundle']) and same(owner['scope'], scope) and
                not owner.get('retention_only', False) and same(owner['original_session']['binding'], binding),
                'normal original Session ownership differs')
        return actual

    def _facility(self, parent, action):
        require(action in ('accept', 'drive'), 'only original accepted/driven Session facilities are sources')
        row = self._row(execution_id(parent['id'], action))
        payload = row['payload']
        require(row['phase'] == 'confirmed' and row['namespace'] == parent['namespace'] and
                payload['parent_id'] == parent['id'] and payload['action'] == action,
                'original Session facility is not confirmed for this parent/action')
        actual = self.delivery._verify(row, row['receipt_ref'])
        require(actual['confirmation_request_id'] == confirmation_id(row['id']),
                'original facility terminal confirmation differs')
        return row, self._healthy(actual, parent, payload['node_request'])

    def _previous(self, parent):
        payload = parent['payload']; source = payload['source_result_ref']
        require(type(source) is dict and source.get('owner') == 'S' and
                source.get('kind') == 'pi-operation-result', 'original previous result required')
        previous = self._row(source['operation_id'])
        require(previous['kind'] == 'invocation' and previous['id'] != parent['id'] and
                previous['namespace'] == parent['namespace'] and
                all(same(previous['payload'][k], payload[k]) for k in
                    ('resource_id', 'harness_ref', 'capability_ref')),
                'previous invocation belongs to different namespace/Surface/Harness/capability')
        _, actual = self._facility(previous, 'drive')
        require(same(source, actual['frame'].get('operation_result_ref')), 'selected result is not the original saved source')
        locator = dict(owner='S', kind='confirmation', confirmation_request_id=actual['confirmation_request_id'],
                       session_scope=actual['binding']['session_scope'])
        require(same(payload['session_ref'], locator) and
                same(payload['input_binding']['previous_session_ref'], locator),
                'continuation does not select the exact original confirmation')
        return actual

    def _result_bytes(self, source, actual):
        resolved = resolve_original(self.snapshots, actual['confirmation_request_id'], source, actual['binding'])
        full = resolved['snapshot_ref']
        _, raw = read_ref(dict(path=full['archive_path'], sha256=full['archive_sha256'], bytes=full['archive_bytes']))
        _, files, _ = archive(raw)
        tokens = [token for row, token, _, end in rows(files[source['session_relative_path']])
                  if row.get('kind') == 'value' and row.get('namespace') == 'pi.result' and
                  row.get('key') == source['operation_id'] and row.get('op') == 'set' and end <= source['session_bytes']]
        require(len(tokens) == 1 and tokens[0] is not None and sha(tokens[0]) == source['result_sha256'],
                'original Pi result value bytes are unavailable')
        return tokens[0]

    def resolve(self, ref, purpose, expected):
        parent = self._parent(expected['invocation']); payload = parent['payload']
        if purpose == 'session-source':
            row, actual = self._facility(parent, expected['action'])
            supplied = expected['facility']
            require(all(same(supplied[k], row[k]) for k in
                    ('id','principal','namespace','kind','payload','phase','receipt_ref')) and
                    same(ref, row['receipt_ref']), 'selected facility or receipt differs from original R')
            return dict(facility_id=row['id'], confirmation_request_id=actual['confirmation_request_id'])
        require(purpose in ('session', 'source-result'), 'unsupported original Session reference purpose')
        if purpose == 'session' and same(ref, self.initial):
            scope = {k:self.initial[k] for k in SCOPE}
            require(same(payload['session_ref'], ref) and payload['source_result_ref'] is None and
                    payload['input_binding']['previous_session_ref'] is None and
                    parent['namespace'] == scope['namespace'] and payload['resource_id'] == scope['surface_id'],
                    'initial Session conceals a previous source or differs from original Surface')
            return dict(scope=scope, confirmation_request_id=None)
        actual = self._previous(parent)
        if purpose == 'session':
            require(same(ref, payload['session_ref']), 'caller selected a different Session locator')
            return copy.deepcopy(dict(scope=actual['binding']['session_scope'],
                                      confirmation_request_id=actual['confirmation_request_id']))
        require(same(ref, payload['source_result_ref']), 'caller selected a different original result')
        return self._result_bytes(ref, actual)
