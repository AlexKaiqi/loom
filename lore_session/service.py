"""Trusted transport glue for the existing Pi Session. No model or policy loop."""
import base64
import copy
import math
import time

from .execution import SessionRun
from .references import resolve_original
from .snapshot_files import SnapshotError, decode, read_ref, sha
from .transport import SessionChannel, original, pending, require, same


class SessionServiceError(RuntimeError):
    def __init__(self, code, message, evidence):
        super().__init__(message)
        self.code, self.evidence = code, copy.deepcopy(evidence)


class SessionService:
    def __init__(self, execution, snapshots, provider, plans, tools, checkpoint=None):
        self.execution, self.snapshots, self.provider = execution, snapshots, provider
        self.plans, self.tools = plans, tools
        self.checkpoint = checkpoint

    def invoke(self, request, *, execution_id, deadline_monotonic):
        request = copy.deepcopy(request)
        allowed = {'protocol', 'action', 'session_ref', 'operation_id', 'harness_ref',
                   'input_ref', 'source_result_ref', 'capability_ref', 'read_ref'}
        try:
            require(type(request) is dict and set(request) <= allowed and
                    allowed-{'read_ref'} <= set(request) and request['protocol'] == 'lore.s/1' and
                    request['action'] in ('accept', 'query', 'drive', 'export_read'), 'invalid original Node request')
            require(type(deadline_monotonic) in (int, float) and
                    math.isfinite(deadline_monotonic) and time.monotonic() < deadline_monotonic, 'future monotonic deadline required')
            plan = self.plans.session(copy.deepcopy(request), execution_id=execution_id)
            x_request = plan['request']; scope = x_request['session_binding']
            require(x_request['execution_id'] == execution_id and
                    same(x_request['source_result'], request['source_result_ref']) and
                    request['session_ref']['owner'] == 'S' and
                    request['session_ref']['session_id'] == scope['session_id'] and
                    all(k not in request['session_ref'] or request['session_ref'][k] == scope[k]
                        for k in ('namespace', 'surface_id', 'session_generation')), 'trusted plan/request scope differs')
            binding = dict(session_id=scope['session_id'], session_scope=copy.deepcopy(scope),
                           **{k:copy.deepcopy(request[k]) for k in
                              ('operation_id', 'harness_ref', 'input_ref', 'source_result_ref', 'capability_ref')})
            run = SessionRun(self.execution, self.snapshots, x_request, plan['authority'], binding['operation_id'])
        except Exception as error:
            raise SessionServiceError(getattr(error, 'code', 'invalid_frame'), str(error), {}) from error
        invocation = _Invocation(self, run, request, binding, deadline_monotonic)
        return invocation.invoke()


class _Invocation:
    def __init__(self, service, run, request, binding, deadline):
        self.service, self.run, self.request, self.binding, self.deadline = service, run, request, binding, deadline
        self.channel = SessionChannel(run)
        self.evidence = {}
        self.frozen = False
        self.started = False
        self.serial = 0
        self.counts = {'provider':0, 'tool':0}
        self.quarantine_reason = 'unadmitted original after transport failure'

    def hook(self, label, extra=None):
        if self.service.checkpoint:
            self.service.checkpoint(label, copy.deepcopy(dict(binding=self.binding,
                execution_binding=self.run.binding, **self.evidence, **(extra or {}))))

    def save(self, label, quarantine=None):
        self.serial += 1
        checkpoint_id = 's-service-final' if label == 'final' else 's-service-'+str(self.serial)+'-'+label
        if quarantine:
            self.quarantine_reason = quarantine
            saved = self.run.quarantine(checkpoint_id, quarantine)
            self.evidence.update(retained_quarantine=saved['retained_quarantine'])
        else:
            saved = self.run.checkpoint(checkpoint_id)
            self.evidence.update(original_session_snapshot_ref=saved['original_session_snapshot_ref'])
            owner = decode(read_ref(saved['original_session_snapshot_ref']['owner_record_ref'])[1])
            self.evidence['confirmation_request_id'] = owner['confirmation_request_id']
        self.evidence['checkpoint_ref'] = saved['receipt']
        self.frozen = True
        return saved

    def resume(self):
        self.run.resume(self.evidence['checkpoint_ref'])
        self.frozen = False

    def retain_pending(self):
        saved = self.run.quarantine_pending(self.quarantine_reason)
        self.evidence.update(retained_quarantine=saved['retained_quarantine'], checkpoint_ref=saved['receipt'])
        self.frozen = True

    def cleanup(self):
        if not self.started: return
        if self.run.pending_confirmation is not None:
            self.retain_pending()
        if not self.frozen:
            try: self.save('failed')
            except Exception:
                if self.run.pending_confirmation is not None: self.retain_pending()
                else: self.save('failed-original', self.quarantine_reason)
        self.evidence['stopped'] = self.run.seal(self.evidence['checkpoint_ref'])
        self.evidence['released'] = self.run.release()
        self.started = False

    def callback(self, frame):
        kind = 'provider' if frame['type'].startswith('provider.') else 'tool'
        is_request = frame['type'].endswith('.request')
        require(not is_request or self.request['action'] == 'drive', 'read/accept cannot dispatch new effects')
        if is_request:
            self.counts[kind] += 1
            require(self.counts[kind] <= 1, 'single-step effect budget exceeded')
        saved = self.save(kind+'-intent')
        observed = original(self.service.snapshots, saved, self.binding)
        scope = pending(observed, self.binding, frame)
        self.hook('before_dispatch' if is_request else 'before_query', {'callback':frame})
        # The original private process is paused only until its pending is externally saved.
        self.resume()
        if not is_request:
            owner = self.service.provider if kind == 'provider' else self.service.tools
            result = owner.query(frame['effect_id'], scope)
            self.hook('effect_queried', {'callback':frame, 'owner_result':result})
            self.channel.write(dict(type='effect.query_reply', effect_id=frame['effect_id'], result=result))
            return
        if kind == 'provider':
            result = self.service.provider.complete(scope, copy.deepcopy(frame))
        else:
            result = self.service.tools.execute(copy.deepcopy(scope), copy.deepcopy(frame),
                                                saved['original_session_snapshot_ref'])
        self.evidence['pending_receipt'] = copy.deepcopy(result)
        self.hook('effect_received', {'callback':frame, 'owner_result':result})
        if result.get('status') == 'UNKNOWN':
            raise SnapshotError('paused_unknown', 'original external effect remains unresolved')
        if result.get('fresh') is not True:
            raise SnapshotError('paused_reconciliation_required', 'retained original receipt cannot be replayed into orphan pending')
        require(result.get('status') == 'RECEIVED', 'external owner did not return a complete receipt')
        if kind == 'provider':
            wire = result['wire']
            if not wire.get('accepted'):
                raise SnapshotError('paused_reconciliation_required', 'original provider reply is retained but not a valid Message')
            reply = dict(type='provider.reply', effect_id=frame['effect_id'],
                         response_entry_id=frame['response_entry_id'], message=wire['normalized']['message'])
        else:
            _, raw = read_ref(result['stdout_ref'], 1048576)
            raw.decode('utf8')
            reply = dict(type='tool.reply', effect_id=frame['effect_id'], invocation_id=frame['invocation_id'],
                         result_ref=result['result_ref'], stdout=dict(data_b64=base64.b64encode(raw).decode(),
                                                                    bytes=len(raw), sha256=sha(raw)))
            if 'exit_code' in result or 'stderr_ref' in result:
                code = result.get('exit_code')
                require(type(code) is int and 0 <= code <= 255 and 'stderr_ref' in result,
                        'complete original tool exit status and stderr required together')
                _, stderr = read_ref(result['stderr_ref'], 1048576)
                stderr.decode('utf8')
                reply.update(exit_code=code, stderr=dict(data_b64=base64.b64encode(stderr).decode(),
                                                        bytes=len(stderr), sha256=sha(stderr)))
        if kind == 'tool' and 'publication_ref' in result:
            reply['publication_ref'] = copy.deepcopy(result['publication_ref'])
        self.channel.write(reply)

    def finish(self, frame):
        require(frame.get('operation_id') == self.binding['operation_id'], 'terminal operation identity differs')
        self.channel.close()
        error = frame.get('error', {})
        is_read = self.request['action'] == 'export_read' and not error
        if is_read:
            require(set(frame) <= {'type', 'operation_id', 'boundary_kind', 'read_result_ref', 'operation_result_ref'} and
                    frame.get('boundary_kind') == 'accepted' and type(frame.get('read_result_ref')) is dict and
                    set(frame['read_result_ref']) == {'path', 'sha256', 'bytes'}, 'invalid original read descriptor')
        if error.get('code') in ('session_corrupt', 'integrity_mismatch'):
            self.save('quarantine', error['code'])
        else:
            saved = self.save('final')
            if not error or frame.get('operation_result_ref'):
                observed = original(self.service.snapshots, saved, self.binding)
                if frame.get('operation_result_ref'):
                    resolved = resolve_original(self.service.snapshots, self.evidence['confirmation_request_id'],
                                                frame['operation_result_ref'], self.binding)
                    if is_read:
                        pass  # The locator is verified, while the distinct original read frame remains unchanged.
                    elif resolved['boundary'] is not None:
                        require(same(frame, dict(type='result', operation_id=self.binding['operation_id'],
                                                  **resolved['boundary'])), 'frame changes the original Harness boundary')
                    else:
                        require('decision_proposal' not in frame and frame.get('boundary_kind') == 'paused_reconciliation_required',
                                'missing original boundary cannot become an accepted decision')
                else:
                    op = self.binding['operation_id']; values = observed['values']
                    require('decision_proposal' not in frame and ('pi.result', op) not in values,
                            'terminal frame hides a saved result or invents a decision')
                    require(frame.get('boundary_kind') == 'accepted' and
                            values.get(('pi.op.meta', op), {}).get('operationId') == op and
                            ('pi.op.state', op) in values and
                            values.get(('pi.lane.state', 'main'), {}).get('currentOperationId') == op,
                            'acceptance lacks original accepted operation')
        if is_read:
            actual = self.service.plans.resolve_read(copy.deepcopy(self.request['read_ref']), copy.deepcopy(frame['read_result_ref']))
            fact, _ = read_ref(actual)
            require(all(fact[k] == frame['read_result_ref'][k] for k in ('bytes', 'sha256')),
                    'trusted original read bytes differ from Node descriptor')
            self.evidence['resolved_read_ref'] = copy.deepcopy(actual)
        self.hook('result_saved', {'frame':frame})
        self.cleanup()
        return copy.deepcopy(dict(frame=frame, **self.evidence))

    def invoke(self):
        try:
            self.run.start(); self.started = True
            self.channel.write(self.request)
            while True:
                frame = self.channel.next(self.deadline)
                if frame.get('type') in ('provider.request', 'tool.request', 'provider.query', 'effect.query'):
                    self.callback(frame)
                else:
                    require(frame.get('type') == 'result', 'unknown control frame')
                    return self.finish(frame)
        except Exception as error:
            try: self.cleanup()
            except Exception as cleanup_error:
                self.evidence['cleanup_error'] = dict(code=getattr(cleanup_error, 'code', None), message=str(cleanup_error))
            code = getattr(error, 'code', 'paused_unknown')
            if code in ('invalid_snapshot', 'reference_invalid'): code = 'invalid_frame'
            raise SessionServiceError(code, str(error), self.evidence) from error
