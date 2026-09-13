"""R provider responsibility around original Bridge bytes; no model or retry loop."""
import copy
import math
import time
from pathlib import Path
from lore_control.values import decode, encode, fail, identifier
from lore_provider.request import MODEL
from lore_session.provider import ProviderBridge, digest, same
from .session_plan_files import compact

DEFAULT_BUDGET = dict(max_requests=6, max_input_tokens=15360,
    max_output_tokens_per_request=2048, max_request_body_bytes=15360, max_seconds=300)


def require(value, message, code='reference_invalid'):
    if not value: fail(code, message)


class ProviderOwner:
    def __init__(self, control, root, endpoint, *, principal, budget=None,
                 credential_provider=None, timeout=60, deadline_provider=None):
        identifier(principal)
        root = Path(root).absolute()
        require(root.resolve() == root and root.parent.is_dir(), 'unaliased original provider root required')
        limits = copy.deepcopy(DEFAULT_BUDGET if budget is None else budget)
        require(type(limits) is dict and set(limits) == set(DEFAULT_BUDGET), 'complete trusted budget required')
        require(all(type(limits[k]) is int and limits[k] > 0 for k in limits if k != 'max_seconds'), 'positive token/count limits required')
        require(type(limits['max_seconds']) in (int,float) and math.isfinite(limits['max_seconds']) and limits['max_seconds'] > 0,
                'finite scope duration required')
        require(limits['max_output_tokens_per_request'] <= 2048 and limits['max_request_body_bytes'] <= 65536,
                'trusted budget exceeds original Wire profile')
        require(type(timeout) in (int,float) and 0 < timeout <= 60 and
                (deadline_provider is None or callable(deadline_provider)), 'finite transport timeout required')
        self.control, self.root, self.principal = control, root, principal
        self.endpoint, self.budget = copy.deepcopy((endpoint, limits))
        self.credential_provider, self.timeout, self.deadline_provider = credential_provider, timeout, deadline_provider
        self.config = dict(root=str(root), principal=principal, endpoint=self.endpoint, model=MODEL,
                           budget=limits, timeout=timeout)
        self.boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def _model(self, scope):
        return dict(model=MODEL, max_completion_tokens=self.budget['max_output_tokens_per_request'],
                    **{k:copy.deepcopy(scope[k]) for k in ('session_scope','input_ref','harness_ref','capability_ref')})

    def _bridge(self, payload):
        require(same(payload['owner_config'], self.config), 'original provider configuration differs', 'conflict')
        return ProviderBridge(self.root, self.endpoint, payload['model_scope'],
            credential_provider=self.credential_provider, timeout=payload['transport_timeout'])

    def _row(self, id):
        row = self.control.db.execute('SELECT * FROM requests WHERE id=?',(id,)).fetchone()
        return None if row is None else self.control._request_value(row)

    def _parent(self, scope):
        row = self._row(scope['operation_id'])
        require(row is not None and row['kind'] == 'invocation' and row['namespace'] == scope['session_scope']['namespace'],
                'original accepted invocation/namespace differs')
        self.control._authorize(self.principal, row['namespace'], {'runtime'})
        payload = row['payload']
        require(scope['harness_ref'] == compact(payload['harness_ref']) and
                scope['capability_ref'] == compact(payload['capability_ref']) and
                same(scope['source_result_ref'], payload['source_result_ref']), 'original parent references differ', 'conflict')
        return row

    def _records(self, scope):
        rows = []
        for record in self.control.db.execute("SELECT * FROM requests WHERE kind='provider_transport' ORDER BY seq"):
            payload = decode(record['payload_json'])
            if payload.get('schema') == 'lore-provider-owner/1' and payload.get('owner_config',{}).get('root') == str(self.root) and same(payload['scope']['session_scope'], scope):
                rows.append(self.control._request_value(record))
        return rows

    def _profile(self, scope, rows):
        if rows:
            profile = rows[0]['payload']['scope_profile']
            require(all(same(r['payload']['owner_config'], self.config) and same(r['payload']['scope_profile'], profile) for r in rows),
                    'scope has conflicting original configuration', 'conflict')
            return copy.deepcopy(profile)
        now = time.monotonic(); deadline = now + self.budget['max_seconds']
        if self.deadline_provider is not None:
            requested = self.deadline_provider(copy.deepcopy(scope))
            require(type(requested) in (int,float) and math.isfinite(requested), 'finite trusted scope deadline required')
            deadline = min(deadline, requested)
        return dict(scope=copy.deepcopy(scope), boot_id=self.boot_id, started_monotonic=now,
                    deadline_monotonic=deadline, limits=copy.deepcopy(self.budget))

    def _query_row(self, row):
        payload = row['payload']; bridge = self._bridge(payload)
        prepared, _, raw = bridge._prepared(payload['scope'], payload['frame'])
        require(row['kind'] == 'provider_transport' and row['principal'] == self.principal and
                row['id'] == payload['frame']['effect_id'] == prepared['effect_id'] and
                row['namespace'] == payload['scope']['session_scope']['namespace'] and
                payload['request_sha256'] == digest(raw), 'original provider request association differs')
        result = bridge.query(row['id'], payload['scope'])
        if result['status'] == 'RECEIVED':
            original = Path(result['receipt_ref']['path']).parent/'prepared.json'
            require(same(decode(bridge._read(original,2097152)), prepared), 'saved original frame/configuration differs')
        return result

    def _usage(self, rows):
        total = 0
        for row in rows:
            result = self._query_row(row)
            require(result['status'] == 'RECEIVED' and result['wire'].get('accepted') is True,
                    'original attempt usage is unresolved', 'budget_unknown')
            usage = result['wire']['normalized']['wire']['raw_usage']
            require(usage['completion_tokens'] <= row['payload']['model_scope']['max_completion_tokens'],
                    'actual original output exceeded its request budget', 'budget_exceeded')
            total += usage['prompt_tokens']
        require(total <= self.budget['max_input_tokens'], 'actual original input budget exceeded', 'budget_exceeded')
        return total

    def _admit(self, scope, rows, profile, raw):
        require(profile['boot_id'] == self.boot_id and time.monotonic() < profile['deadline_monotonic'],
                'original scope deadline expired or clock epoch changed', 'budget_exceeded')
        known = {row['id'] for row in rows}
        for path in self.root.glob('*/prepared.json'):
            bridge = ProviderBridge(self.root,self.endpoint,self._model(scope),timeout=self.timeout)
            value = decode(bridge._read(path,2097152))
            if same(value['binding']['session_scope'],scope['session_scope']):
                require(value['effect_id'] in known, 'unassociated original provider attempt cannot be ignored', 'budget_unknown')
        require(len(rows) < self.budget['max_requests'], 'scope request count exhausted', 'budget_exceeded')
        used = self._usage(rows)
        require(len(raw) <= self.budget['max_request_body_bytes'] and used+len(raw) <= self.budget['max_input_tokens'],
                'conservative input-byte reservation exceeds remaining budget', 'budget_exceeded')

    def _wrapper(self, row, result):
        binding = {k:row[k] for k in ('principal','id','namespace','kind','payload')}
        value = dict(owner='provider',kind='delivery_receipt',id=row['id']+'.receipt',
            request_id=row['id'],namespace=row['namespace'],source=row['principal'],delivery_owner='provider',
            request_digest=digest(encode(binding).encode()),outcome='positive',definite=True,
            provider_ref=dict(owner='provider',kind='wire_receipt',effect_id=row['id'],receipt_ref=result['receipt_ref']))
        return dict(value,sha256=digest(encode(value).encode()))

    def _confirm(self, row, result):
        if result['status'] == 'RECEIVED':
            receipt = self._wrapper(row,result)
            self.control.confirm_delivery(self.principal,row['id'],receipt)
        return result

    def _begin(self, scope, frame, raw, effect_id):
        # Budget and first scope profile share the existing SQLite transaction,
        # including across distinct ControlStore processes. HTTP follows commit.
        with self.control._tx():
            parent = self._parent(scope); prior = self._row(effect_id)
            if prior is not None:
                require(same(prior['payload']['scope'],scope) and same(prior['payload']['frame'],frame),
                        'same original effect has different complete parameters','conflict')
                return prior, False
            rows = self._records(scope['session_scope']);profile = self._profile(scope['session_scope'],rows)
            self._admit(scope,rows,profile,raw)
            require(parent['phase'] == 'issued', 'new provider call has no issued parent')
            timeout = min(self.timeout,profile['deadline_monotonic']-time.monotonic())
            payload = dict(schema='lore-provider-owner/1',parent_id=parent['id'],scope=scope,frame=frame,
                model_scope=self._model(scope),owner_config=copy.deepcopy(self.config),scope_profile=profile,
                transport_timeout=timeout,request_sha256=digest(raw))
            row = self.control._accept(self.principal,dict(id=effect_id,namespace=parent['namespace'],kind='provider_transport',payload=payload))
            return row, True

    def complete(self, scope, frame):
        scope, frame = copy.deepcopy((scope,frame))
        prototype = ProviderBridge(self.root,self.endpoint,self._model(scope),timeout=self.timeout)
        prepared, _, raw = prototype._prepared(scope,frame)
        row, created = self._begin(scope,frame,raw,prepared['effect_id'])
        if not created:
            with self.control._lock:result = self._query_row(row)
            return self._confirm(row,result)
        dispatch = self.control.mark_dispatched(self.principal,row['id'],'provider')
        if not dispatch['fresh']: return self.query(row['id'],scope)
        result = self._bridge(row['payload']).complete(scope,frame)
        self._confirm(row,result)
        if result['status'] == 'RECEIVED' and result['wire'].get('accepted'):
            with self.control._lock:
                self._usage(self._records(scope['session_scope']))
                require(time.monotonic() <= row['payload']['scope_profile']['deadline_monotonic'],
                        'original response arrived after scope deadline', 'budget_exceeded')
        return result

    def query(self, effect_id, scope):
        prototype = ProviderBridge(self.root,self.endpoint,self._model(scope),timeout=self.timeout)
        require(effect_id == prototype._scope(scope), 'effect identity belongs to another complete scope','conflict')
        with self.control._lock:
            self._parent(scope);row = self._row(effect_id)
            if row is None:return dict(status='UNKNOWN',effect_id=effect_id,fresh=False)
            require(same(row['payload']['scope'],scope),'original effect scope differs','conflict')
            result = self._query_row(row)
            if row['phase'] == 'confirmed':require(same(row['receipt_ref'],self._wrapper(row,result)),'original confirmed wrapper differs')
            return result

    def control_reference(self, ref, purpose, expected=None):
        try:
            if purpose != 'receipt' or ref.get('delivery_owner') != 'provider':return False
            with self.control._lock:
                row = self._row(ref['request_id'])
                require(row is not None,'original provider responsibility missing')
                original = self.control._receipt_expected(self.control._get_request(row['id']))
                require(same(original,expected) and all(ref.get(k)==v for k,v in original.items()),'R receipt expected association differs')
                result = self._query_row(row)
                return result['status'] == 'RECEIVED' and same(ref,self._wrapper(row,result))
        except Exception:return False
