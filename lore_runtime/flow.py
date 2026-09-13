"""R responsibility orchestration; all strategy decisions remain external originals."""
import asyncio
import copy
import math
import time
from pathlib import Path
from lore_control.values import decode, encode, fail, identifier
from lore_execution.journal import digest


class RuntimeFlow:
    def __init__(self, control, events, delivery, worker_id, checkpoint=None):
        identifier(worker_id)
        self.control, self.events, self.delivery = control, events, delivery
        self.worker_id = worker_id
        self.checkpoint = checkpoint or (lambda label, value: None)

    def start(self, principal, request):
        return self.control.accept(principal, copy.deepcopy(request))

    def register(self, principal, **registration):
        return self.control.register(principal, **registration)

    def query(self, principal, request_id):
        c = self.control
        with c._tx(False):
            first = c._get_request(request_id)
            c._authorize(principal, first['namespace'])
            rows, decisions, queue, visited = [], [], [request_id], set()
            while queue:
                id = queue.pop(0)
                if id in visited: continue
                visited.add(id)
                row = c._get_request(id); c._authorize(principal, row['namespace'])
                rows.append(c._request_value(row))
                d = c.db.execute('SELECT * FROM decisions WHERE parent_id=?', (id,)).fetchone()
                if d is not None:
                    d = c._decision_value(d); decisions.append(d)
                    if d['applied']:
                        queue.extend(r['id'] for r in d['body'].get('successors', []))
                for w in c.db.execute('SELECT successor_json FROM waits WHERE parent_id=? AND matched=1', (id,)):
                    queue.append(decode(w[0])['id'])
            ids = [r['id'] for r in rows]
            marks = ','.join('?' for _ in ids)
            facilities = [c._request_value(r) for r in c.db.execute(
                "SELECT * FROM requests WHERE json_extract(payload_json,'$.parent_id') IN (" + marks + ') ORDER BY seq', ids)]
            waits = [dict(r) for r in c.db.execute('SELECT * FROM waits WHERE parent_id IN ('+marks+') ORDER BY id', ids)]
            resource_ids = set()
            for row in rows:
                payload = row['payload']
                if 'resource_id' in payload: resource_ids.add(payload['resource_id'])
                resource_ids.update(t['resource_id'] for t in payload.get('input_binding', {}).get('execution_targets', []))
            originals = {}
            for name in ('holders', 'releases', 'installations'):
                items = []
                for record in c.db.execute('SELECT * FROM '+name):
                    value = dict(record)
                    resource = value.get('resource_id') or decode(value['binding_json'])['resource_id']
                    if resource in resource_ids: items.append(value)
                originals[name] = items
            return copy.deepcopy(dict(requests=rows, decisions=decisions, facilities=facilities, waits=waits, **originals))

    async def _inputs(self):
        for row in self.control.pending():
            if row['kind'] != 'invocation' or row['phase'] != 'accepted': continue
            selector = row['payload'].get('input_binding')
            if selector is None: continue
            if self.control.query_input(row['principal'], row['id']) is not None: continue
            target = Path(self.events.profile['input_root']) / digest(row['id'].encode())
            await self.events.prepare_input(row['principal'], row['id'], row['namespace'],
                selector['start_sequence'], selector['filters'], str(target),
                input_context={k:selector[k] for k in ('surface_ref', 'previous_session_ref', 'execution_targets')})

    async def _deliver(self, row, deadline):
        method = self.delivery.execute if row['mode'] == 'execute' else self.delivery.query
        args = (row, deadline) if row['mode'] == 'execute' else (row,)
        job = asyncio.create_task(asyncio.to_thread(method, *args))
        period = min(self.control.lease_seconds / 3, 1.0)
        try:
            while not job.done():
                await asyncio.wait({job}, timeout=period)
                if not job.done():
                    await asyncio.to_thread(self.control.renew, row['id'], row['token'], time.monotonic())
            return job.result()
        except BaseException:
            # The bounded S owner must finish its original cleanup; cancelling the
            # await cannot abandon a live execution thread or invent its release.
            await asyncio.shield(job)
            raise

    async def _advance(self, row, deadline):
        c, token = self.control, row['token']
        try:
            if row['mode'] != 'decide':
                source = await self._deliver(row, deadline)
                if source is None:
                    c.pause(row['id'], token, 'original Session result unavailable',
                            dict(owner='R', request_id=row['id']))
                    return
                row = c.save_result(row['id'], token, source) | {'token':token}
                self.checkpoint('result_saved', copy.deepcopy(row))
            proposal = self.delivery.decision(row, row['result_ref'])
            if proposal is None:
                c.pause(row['id'], token, 'original result has no external control decision', row['result_ref'])
                return
            self.delivery.validate_decision(row, proposal)
            accepted = c.accept_decision(row['id'], token, proposal['decision_id'],
                proposal['source_ref'], proposal['harness_ref'], proposal['body'])
            self.checkpoint('decision_accepted', copy.deepcopy(accepted))
            self.delivery.validate_decision(row, proposal)
            c.apply_decision(row['id'], accepted['id'])
            self.checkpoint('decision_applied', copy.deepcopy(accepted))
        except Exception as error:
            current = c.query(row['principal'], row['id'])
            if current['phase'] not in ('issued', 'decide'): raise
            c.pause(row['id'], token, 'original delivery or decision unavailable: '+type(error).__name__,
                    dict(owner='R', request_id=row['id'], code=getattr(error, 'code', None)))

    async def drive_until(self, principal, request_id, *, deadline_monotonic):
        if type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic):
            fail('invalid', 'finite monotonic deadline required')
        while True:
            snapshot = self.query(principal, request_id)
            phases = {r['phase'] for r in snapshot['requests']}
            if phases <= {'settled'} or phases & {'paused', 'waiting'} or time.monotonic() >= deadline_monotonic:
                return snapshot
            await self._inputs()
            row = self.control.claim(self.worker_id, time.monotonic())
            if row is None:
                await asyncio.sleep(min(.05, max(0, deadline_monotonic-time.monotonic())))
                continue
            await self._advance(row, deadline_monotonic)
