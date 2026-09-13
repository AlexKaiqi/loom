"""Test-only observation of the actual shared target guard over retained Pi bytes."""
import copy
import os
from pathlib import Path
import threading
from lore_session.snapshot_files import SnapshotError, archive, read_ref, require, sha, canonical
from lore_session.tool_authority import require_tool_target
from oracle import pi_jsonl


def state_files(roots):
    result = {}
    for root in roots:
        for path in [Path(root), *sorted(Path(root).rglob('*'))]:
            st = path.lstat()
            result[str(path)] = dict(dev=st.st_dev, ino=st.st_ino, bytes=st.st_size, blocks=st.st_blocks*512,
                sha256=sha(path.read_bytes()) if path.is_file() else None)
    return result


def preflight(controller, run, params):
    roots = (controller.x.journal.root, controller.plans.snapshots.root, controller.plans.authority_root)
    before = state_files(roots); calls = []; thread = threading.get_ident()
    actual_call = controller.x.engine.call
    def observed_call(method, path, *args, **kwargs):
        if threading.get_ident() == thread:
            calls.append(dict(method=method, path=path))
            raise RuntimeError('read-only preflight attempted an Engine call')
        return actual_call(method, path, *args, **kwargs)
    controller.x.engine.call = observed_call
    try:
        result = original_target(controller, run, params)
    finally:
        controller.x.engine.call = actual_call
    after = state_files(roots)
    require(before == after and not calls, 'preflight changed original state or attempted Engine activity')
    result['read_only_observation'] = dict(before=before, after=after, engine_calls=calls)
    return result


def original_target(controller, run, params):
    require(run.latest is not None and params['checkpoint_receipt'] == run.latest['full'] and
            params['operation_id'] == run.op, 'preflight must select current original run/checkpoint')
    retained = run.latest['confirmation']
    owner = read_ref(retained['owner_record_ref'])[1]
    import json
    owner = json.loads(owner)
    confirmed = controller.plans.snapshots.query(owner['confirmation_request_id'])
    require(confirmed == retained, 'preflight original ownership differs')
    ref = retained['snapshot_ref']
    raw = read_ref(dict(path=ref['archive_path'],sha256=ref['archive_sha256'],bytes=ref['archive_bytes']))[1]
    _, files, _ = archive(raw)
    jp = owner['original_session']['jsonl']['relative_path']; original = pi_jsonl(files[jp])
    request = controller.run_plans[run.id]['original_request']
    binding = dict(session_id=run.scope['session_id'], session_scope=run.scope, operation_id=run.op,
        **{k:request[k] for k in ('input_ref','harness_ref','capability_ref','source_result_ref')})
    require(request['session_scope'] == run.scope and request['operation_id'] == run.op and
            original['values'].get('lore.s.binding',{}).get(run.op) == binding,
            'preflight original complete operation binding differs')
    result = original['values'].get('pi.result',{}).get(run.op)
    require(result is not None and result['operationId'] == run.op, 'preflight requires original completed operation result')
    entries = {row['id']:row for row in original['entries']}; current = result['tipId']; allowed = set()
    while current != result['fromTipId']:
        require(current in entries and current not in allowed, 'original operation path is incomplete')
        allowed.add(current); current = entries[current]['parentId']
    entry_id = params['entry_id']; index = params['call_index']
    require(entry_id in allowed, 'entry is outside current original operation')
    entry = entries[entry_id]; message = entry.get('message',{})
    require(entry.get('type') == 'message' and message.get('role') == 'assistant' and
            type(index) is int and 0 <= index < len(message['content']), 'native content selection differs')
    call = message['content'][index]
    require(call.get('type') == 'toolCall' and call.get('name') == 'shell' and
            isinstance(call.get('arguments'),dict), 'selected original is not a native Shell call')
    args = copy.deepcopy(call['arguments'])
    output = dict(kind='trusted_target_preflight', dispatch=False, binding=copy.deepcopy(binding),
        checkpoint_full_ref=copy.deepcopy(run.latest['full']), snapshot_ref=copy.deepcopy(ref),
        session_jsonl=dict(relative_path=jp,sha256=original['sha256'],bytes=original['bytes']),
        operation_result=copy.deepcopy(result), entry_id=entry_id, call_index=index, tool_call_id=call['id'],
        native_request=args, native_request_sha256=sha(canonical(args)))
    try:
        require_tool_target(args.get('target'),args.get('script'))
    except SnapshotError as error:
        if error.code != 'unauthorized_target': raise
        output.update(allowed=False,error=dict(type=type(error).__name__,code=error.code,message=str(error)))
    else: output.update(allowed=True)
    return output
