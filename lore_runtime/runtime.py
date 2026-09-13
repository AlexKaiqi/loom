"""Shared Linux Runtime entry over the existing R/E/F/X/S owners."""
import asyncio
import copy
import concurrent.futures
import inspect
from pathlib import Path
from lore_control.values import fail
from lore_events import EventService
from .event_reader import JetStreamReader
from .event_authority import EventReferences
from .flow import RuntimeFlow
from .session_delivery import SessionDelivery
from .session_facts import SessionFacts
from .emissions import EmitService


class Runtime:
    def __init__(self, config, *, session_service, provider_bridge, checkpoint=None):
        self.config = copy.deepcopy(config)
        self.session_service, self.provider_bridge = session_service, provider_bridge
        self.checkpoint = checkpoint or (lambda label, value: None)
        plans = session_service.plans
        self.control, self.files = plans.control, plans.files
        self.execution, self.snapshots = session_service.execution, session_service.snapshots
        if session_service.provider is not provider_bridge:
            fail('invalid', 'Runtime and Session must use the same trusted provider owner')
        actual = dict(control_db=self.control.db.execute('PRAGMA database_list').fetchone()[2],
                      files_dir=self.files.control, execution_dir=self.execution.journal.root,
                      session_dir=self.snapshots.root)
        for key, path in actual.items():
            supplied = Path(self.config[key])
            if not supplied.is_absolute() or supplied.resolve() != supplied or supplied != Path(path):
                fail('invalid', 'Runtime configuration differs from actual original owner: '+key)
        if self.config['engine_endpoint'] != 'unix://' + self.execution.engine.path:
            fail('invalid', 'Runtime Engine endpoint differs from original X owner')
        if self.config['authority'] != self.control.authority:
            fail('invalid', 'Runtime authority differs from original R configuration')
        self.principal = plans.host['principal']
        if self.config['event_profile']['runtime_principal'] != self.principal:
            fail('invalid', 'Runtime event principal differs from fixed Session host')
        self.reader = JetStreamReader(self.config['nats_url'])
        self.events = EventService(self.config['nats_url'], self.control, self.config['event_profile'], self._event_checkpoint)
        self.event_references = EventReferences(self.control, self.events, self.reader)
        self.facts = SessionFacts(self.snapshots, self.execution.journal.root, self.execution.engine)
        self.delivery = SessionDelivery(self.control, session_service, self.facts)
        self.prior_reference = self.control.reference_checker
        self.control.reference_checker = self._reference
        self.flow = RuntimeFlow(self.control, self.events, self.delivery, self.config['worker_id'], checkpoint=self.checkpoint)
        self.opened = self.closed = False
        self.event_loop = None
        self.emissions = None
        if session_service.tools is not None:
            self.emissions = EmitService(self.events, session_service.tools.resolve_tool_source)
            session_service.tools.emission_submit = self._emit_from_worker

    def _emit_from_worker(self, effect_id, binding, publication_ref):
        if not self.opened or self.closed or self.event_loop is None or self.emissions is None:
            fail('invalid', 'Runtime shared event owner is not open')
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.event_loop:
            fail('invalid', 'synchronous emit must run in the existing Session worker')
        pending = asyncio.run_coroutine_threadsafe(
            self.emissions.publish(effect_id, binding, publication_ref), self.event_loop)
        try:
            return pending.result(timeout=30)
        except concurrent.futures.TimeoutError:
            pending.cancel()
            fail('delivery_unknown', 'original bounded event submission did not finish')

    def _reference(self, ref, purpose, expected=None):
        if type(ref) is not dict: return False
        if purpose in ('input', 'observation') or (purpose == 'receipt' and ref.get('delivery_owner') == 'E'):
            return self.event_references(ref, purpose, expected)
        if ((purpose == 'receipt' and ref.get('facility_ref', {}).get('kind') == 'session_execution') or
                (purpose == 'result' and ref.get('owner') == 'S') or
                (purpose == 'stop' and ref.get('kind') == 'runtime-policy-stop')):
            return self.delivery.control_reference(ref, purpose, expected)
        return callable(self.prior_reference) and self.prior_reference(ref, purpose, expected) is True

    async def _event_checkpoint(self, label, value):
        result = self.checkpoint(label, value)
        if inspect.isawaitable(result): await result

    async def open(self):
        if self.closed: fail('invalid', 'closed Runtime owner cannot be reopened')
        if self.opened: return self
        try:
            if callable(getattr(self.files, 'bind_loop', None)):
                self.files.bind_loop(asyncio.get_running_loop())
            await asyncio.to_thread(self.reader.open)
            await self.events.start()
            self.event_loop = asyncio.get_running_loop()
            self.opened = True
            return self
        except BaseException:
            await self.events.close()
            await asyncio.to_thread(self.reader.close)
            raise

    def register(self, principal, **registration):
        if self.closed: fail('invalid', 'Runtime owner is closed')
        return self.flow.register(principal, **registration)

    def start(self, principal, request):
        if self.closed: fail('invalid', 'Runtime owner is closed')
        return self.flow.start(principal, request)

    async def drive_until(self, principal, request_id, *, deadline_monotonic):
        if not self.opened or self.closed: fail('invalid', 'Runtime shared facilities are not open')
        return await self.flow.drive_until(principal, request_id, deadline_monotonic=deadline_monotonic)

    def query(self, principal, request_id):
        if self.closed: fail('invalid', 'Runtime owner is closed')
        return self.flow.query(principal, request_id)

    async def close(self):
        if self.closed: return
        try:
            await self.events.close()
        finally:
            try:
                await asyncio.to_thread(self.reader.close)
            finally:
                self.execution.journal.close()
                self.control.close()
                self.opened, self.closed = False, True
