"""Original R facility deliveries to S; no policy interpretation or effect replay."""
import copy
import hashlib
from lore_control.values import encode, fail
from lore_session.execution import session_reference
from lore_session.transport import original
from .session_plan_files import compact


def sha(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()

def require(value, message):
    if not value: fail('reference_invalid', message)

def execution_id(parent, action):
    return 's-exec-' + sha([parent, action])

def confirmation_id(eid):
    return 's-' + sha([eid, 's-service-final'])


class SessionDelivery:
    def __init__(self, control, service, facts):
        self.control, self.service, self.facts = control, service, facts
        self.principal = service.plans.host['principal']

    def _row(self, id):
        with self.control._lock:
            return self.control._request_value(self.control._get_request(id))

    def _parent(self, supplied):
        actual = self._row(supplied['id'])
        keys = ('id', 'principal', 'namespace', 'kind', 'payload')
        require(actual['kind'] == 'invocation' and all(actual[k] == supplied[k] for k in keys),
                'original accepted parent differs')
        return actual

    def _wrapper(self, row, facility):
        binding = {k:row[k] for k in ('principal', 'id', 'namespace', 'kind', 'payload')}
        value = dict(owner='X', kind='delivery_receipt', id=row['id']+'.receipt',
            request_id=row['id'], namespace=row['namespace'], source=row['principal'],
            delivery_owner='X', request_digest=sha(binding), outcome='positive', definite=True, facility_ref=facility)
        return dict(value, sha256=sha(value))

    def _verify(self, row, receipt):
        require(row['kind'] == 'execution' and row['principal'] == self.principal and
                receipt == self._wrapper(row, receipt['facility_ref']), 'original facility wrapper differs')
        payload = row['payload']; node = payload['node_request']; action = payload['action']
        parent = self._row(payload['parent_id'])
        eid = execution_id(parent['id'], action)
        require(action in ('accept', 'drive') and row['id'] == payload['execution_id'] == eid and
                row['namespace'] == parent['namespace'] and node['operation_id'] == parent['id'] and
                node['action'] == action and node['harness_ref'] == compact(parent['payload']['harness_ref']),
                'facility does not bind the original parent/action/Harness')
        facility = receipt['facility_ref']
        require(facility['execution_id'] == eid and facility['confirmation_request_id'] == confirmation_id(eid),
                'facility selected another terminal confirmation')
        return self.facts.read(facility, node)

    def _confirmed(self, parent, action):
        eid = execution_id(parent['id'], action)
        with self.control._lock:
            present = self.control.db.execute('SELECT 1 FROM requests WHERE id=?', (eid,)).fetchone()
        if present is None: return None
        row = self._row(eid)
        if row['phase'] != 'confirmed': return None
        return self._verify(row, row['receipt_ref'])

    def _action(self, parent, action, node, deadline):
        eid = execution_id(parent['id'], action)
        request = dict(id=eid, namespace=parent['namespace'], kind='execution',
            payload=dict(parent_id=parent['id'], action=action, execution_id=eid, node_request=node))
        row = self.control.accept(self.principal, request)
        if row['phase'] == 'confirmed': return self._verify(row, row['receipt_ref'])
        dispatched = self.control.mark_dispatched(self.principal, eid, 'X')
        if not dispatched['fresh']: return None
        evidence = self.service.invoke(copy.deepcopy(node), execution_id=eid, deadline_monotonic=deadline)
        cid = confirmation_id(eid)
        require(evidence['confirmation_request_id'] == cid, 'S did not retain the fixed terminal confirmation')
        facility = self.facts.facility(node, eid, cid, evidence['stopped'], evidence['released'])
        receipt = self._wrapper(row, facility)
        actual = self._verify(row, receipt)
        require(actual['frame'] == evidence['frame'], 'returned S frame differs from saved original')
        self.control.confirm_delivery(self.principal, eid, receipt)
        return actual

    def execute(self, parent, deadline):
        parent = self._parent(parent)
        current = self._confirmed(parent, 'drive')
        if current is not None: return current['frame'].get('operation_result_ref')
        # An existing uncertain drive cannot be replaced by an older acceptance.
        with self.control._lock:
            issued = self.control.db.execute('SELECT 1 FROM requests WHERE id=?', (execution_id(parent['id'], 'drive'),)).fetchone()
        if issued is not None: return None
        accepted = self._confirmed(parent, 'accept')
        if accepted is None:
            with self.control._lock:
                prior = self.control.db.execute('SELECT 1 FROM requests WHERE id=?', (execution_id(parent['id'], 'accept'),)).fetchone()
            if prior is not None: return None
            plan = self.service.plans.prepare(self.principal, parent['id'], execution_id=execution_id(parent['id'], 'accept'))
            accepted = self._action(parent, 'accept', plan['node_request'], deadline)
        if accepted is None or accepted['frame'].get('boundary_kind') != 'accepted': return None
        row = self._row(execution_id(parent['id'], 'accept'))
        node = dict(row['payload']['node_request'], action='drive', session_ref=session_reference(accepted['bundle']))
        current = self._action(parent, 'drive', node, deadline)
        return None if current is None else current['frame'].get('operation_result_ref')

    def query(self, parent):
        current = self._confirmed(self._parent(parent), 'drive')
        return None if current is None else current['frame'].get('operation_result_ref')

    def decision(self, parent, source):
        current = self._confirmed(self._parent(parent), 'drive')
        require(current is not None and current['frame'].get('operation_result_ref') == source,
                'original result association differs')
        proposal = current['frame'].get('decision_proposal')
        if proposal is None or 'control' not in proposal: return None
        control, binding = proposal['control'], current['binding']
        require(control['parent_id'] == parent['id'] and control['harness_ref'] == parent['payload']['harness_ref'] and
                proposal['source_result_ref'] == source and proposal['harness_ref'] == binding['harness_ref'] == compact(control['harness_ref']) and
                proposal['input_ref'] == binding['input_ref'], 'original full and compact decision references differ')
        return copy.deepcopy(dict(decision_id=proposal['decision_id'], source_ref=source,
                                  harness_ref=control['harness_ref'], body=control['body']))

    def validate_decision(self, parent, proposal):
        require(proposal == self.decision(parent, parent['result_ref']), 'external saved decision body differs')
        current = self._confirmed(parent, 'drive')
        locator = dict(owner='S', kind='confirmation', confirmation_request_id=current['confirmation_request_id'],
                       session_scope=current['binding']['session_scope'])
        body = proposal['body']
        if 'stop_ref' in body:
            ref = body['stop_ref']
            require(ref == dict(owner='S', kind='runtime-policy-stop', confirmation_ref=locator,
                    operation_id=parent['id'], source_result_ref=parent['result_ref']), 'stop locator differs from its original source')
        for next_request in body.get('successors', []):
            if next_request['kind'] != 'invocation': continue
            payload = next_request['payload']
            require(payload['session_ref'] == payload['input_binding']['previous_session_ref'] == locator and
                    payload['source_result_ref'] == parent['result_ref'], 'successor does not select the retained original source')
        if getattr(self.service, 'tools', None) is not None:
            saved = original(self.service.snapshots, {'original_session_snapshot_ref':session_reference(current['bundle'])}, current['binding'])
            result = saved['values'].get(('pi.result', parent['id']))
            if result is not None:
                tip, seen = result['tipId'], set()
                while tip and tip != result['fromTipId']:
                    require(tip not in seen and tip in saved['entries'], 'original tool history path is unavailable')
                    seen.add(tip); entry = saved['entries'][tip]; tip = entry['parentId']
                    message = entry.get('message', {})
                    if message.get('role') == 'toolResult':
                        self.service.tools.validate_publication(message['details']['publication_ref'], current['binding'])
        return True

    def control_reference(self, ref, purpose, expected=None):
        try:
            if purpose == 'receipt' and ref.get('facility_ref', {}).get('kind') == 'session_execution':
                row = self._row(ref['request_id'])
                require(all(ref.get(k) == v for k,v in expected.items()), 'R receipt association differs')
                self._verify(row, ref); return True
            if purpose == 'result' and ref.get('owner') == 'S':
                parent = self._row(ref['operation_id'])
                return self.query(parent) == ref
            if purpose == 'stop' and ref.get('kind') == 'runtime-policy-stop':
                parent = self._row(expected['parent_id'])
                proposal = self.decision(parent, expected['source_ref'])
                return proposal is not None and proposal['body'] == dict(stop_ref=ref) and proposal['harness_ref'] == expected['harness_ref']
            return False
        except Exception:
            return False
