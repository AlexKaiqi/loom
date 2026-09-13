"""Finite original S reference checks; no Engine/Node/provider and no policy oracle."""
import argparse
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lore_session.snapshots import SnapshotStore
from lore_session.snapshot_files import SnapshotError

HERE = Path(__file__).resolve().parent
ACTIVE = False
FORBIDDEN = []


def audit(event, args):
    if not ACTIVE:
        return
    write = event == 'open' and bool(args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
    if write or event in {'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.truncate', 'os.chmod', 'os.chown'} or event.startswith(('subprocess.', 'socket.')):
        FORBIDDEN.append((event, repr(args)[:300]))
        raise RuntimeError('resolver attempted a forbidden side effect: '+event)


sys.addaudithook(audit)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def json_copy(value): return copy.deepcopy(value)


class Checks:
    def __init__(self): self.rows = []
    def check(self, name, fn):
        try:
            assert fn() is True, 'predicate is not true'
            self.rows.append(dict(name=name, passed=True))
        except Exception as error:
            self.rows.append(dict(name=name, passed=False, error=repr(error)))
    def rejected(self, name, fn):
        def run():
            try: fn()
            except SnapshotError as error: return error.code == 'reference_invalid'
            return False
        self.check(name, run)


def original_store(item, callbacks):
    return SnapshotStore(Path(item['root']), item['expected_binding']['session_scope']['namespace'],
                         lambda *args: callbacks.append(args), global_budget_bytes=item['query_budget'])


def invoke(fn, store, item, *, reference=None, binding=None, confirmation=None):
    global ACTIVE
    ACTIVE = True
    try:
        return fn(store, confirmation or item['confirmation_request_id'],
                  json_copy(reference if reference is not None else item['reference']),
                  json_copy(binding if binding is not None else item['expected_binding']))
    finally:
        ACTIVE = False


def derived(item, target, transform):
    """A labelled private storage fault fixture; NOT a new X execution witness."""
    request_path = next(Path(p) for p in item['source_files'] if Path(p).name == 'request.json')
    request = json.loads(request_path.read_bytes())
    source_path = next(Path(p) for p in item['source_files'] if Path(p).name == 'original.tar')
    raw = source_path.read_bytes(); output = io.BytesIO()
    target.mkdir()
    member_path = request['original_binding']['jsonl_relative_path']
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as old, tarfile.open(fileobj=output, mode='w', format=tarfile.PAX_FORMAT) as new:
        for member in old:
            data = old.extractfile(member).read() if member.isfile() else None
            if member.name.removeprefix('./') == member_path:
                data = transform(data)
                member.size = len(data)
            new.addfile(member, io.BytesIO(data) if data is not None else None)
    source = target/'source.tar'; source.write_bytes(output.getvalue())
    full = json_copy(request['checkpoint_full_ref'])
    full.update(path=str(source), size=source.stat().st_size, sha256=digest(source.read_bytes()))
    callbacks = []
    store = SnapshotStore(target/'owner', item['expected_binding']['session_scope']['namespace'],
                          lambda *args: callbacks.append(args), global_budget_bytes=item['query_budget'])
    confirmed = store.confirm(request['request_id'], request['expected_scope'], full, request['original_binding'])
    save(target/'fixture.json', dict(scope='CONTROLLED_STORAGE_ONLY_NOT_ENGINE_EVIDENCE',
         original_sources=item['source_files'], confirmed=confirmed, source_sha256=full['sha256']))
    callbacks.clear()
    return store, callbacks, confirmed


def change_boundary(raw, op, field):
    lines = raw.splitlines(keepends=True)
    for i, line in enumerate(lines[1:], 1):
        tx = json.loads(line)
        for row in tx if isinstance(tx, list) else [tx]:
            if (row.get('namespace'), row.get('key')) == ('lore.s.boundary', op):
                value = row['value']
                if field == 'locator': value['operation_result_ref']['session_sha256'] = '0'*64
                else: value['decision_proposal'][field] = {'wrong': 'real stored mismatch'}
                lines[i] = json.dumps(tx, ensure_ascii=False, separators=(',', ':')).encode()+b'\n'
    return b''.join(lines)


def append_rewrite(raw, op, namespace, value):
    maximum = 0
    for line in raw.splitlines()[1:]:
        tx = json.loads(line)
        maximum = max(maximum, *(row['seq'] for row in tx if isinstance(tx, list))) if isinstance(tx, list) else max(maximum, tx['seq'])
    row = dict(kind='value', op='set', seq=maximum+1, namespace=namespace, key=op, value=value)
    return raw+json.dumps(row, separators=(',', ':'), ensure_ascii=False).encode()+b'\n'


def exercise(fn, protocol, out):
    checks = Checks(); items = {x['key']: x for x in protocol['fixtures']}; callbacks = []
    stores = {k: original_store(v, callbacks) for k, v in items.items()}
    observed = {}
    for key in ('answer', 'tool', 'later'):
        def correct(key=key):
            item = items[key]; value = invoke(fn, stores[key], item); observed[key] = value
            return value['reference'] == item['reference'] and value['binding'] == item['expected_binding'] and value['operation_result'] == item['expected_result'] and value['boundary'] == item['expected_boundary'] and value['snapshot_ref'] == stores[key].query(item['confirmation_request_id'])['snapshot_ref']
        checks.check('original_'+key+'_exact', correct)
    tool = items['tool']; later = items['later']; answer = items['answer']
    checks.check('old_tool_prefix_inside_later_snapshot', lambda: invoke(fn, stores['later'], tool, confirmation=later['confirmation_request_id'])['boundary'] == tool['expected_boundary'])
    mutations = {'owner': 'R', 'kind': 'result', 'session_id': 'different', 'operation_id': 'different',
                 'session_relative_path': '../metadata.json', 'result_sha256': '0'*64,
                 'session_sha256': '0'*64, 'session_bytes': True, 'session_range': [1, answer['reference']['session_bytes']]}
    for key, bad in mutations.items():
        value = json_copy(answer['reference']); value[key] = bad
        checks.rejected('locator_'+key, lambda value=value: invoke(fn, stores['answer'], answer, reference=value))
    for key in ('namespace', 'surface_id', 'session_id', 'session_generation'):
        value = json_copy(answer['reference']); value['session_scope'][key] = 2 if key == 'session_generation' else 'different'
        checks.rejected('locator_scope_'+key, lambda value=value: invoke(fn, stores['answer'], answer, reference=value))
    value = json_copy(answer['reference']); value['extra'] = True
    checks.rejected('locator_unknown_field', lambda: invoke(fn, stores['answer'], answer, reference=value))
    for key in answer['expected_binding']:
        binding = json_copy(answer['expected_binding']); binding[key] = {'wrong': 'complete binding'}
        checks.rejected('expected_binding_'+key, lambda binding=binding: invoke(fn, stores['answer'], answer, binding=binding))
    for name in ('missing-confirmation', 'quarantine-not-a-normal-confirmation'):
        checks.rejected(name, lambda name=name: invoke(fn, stores['answer'], answer, confirmation=name))
    private = out/'storage-fixtures'; private.mkdir()
    store, log, _ = derived(answer, private/'prefix-only', lambda raw: raw[:answer['reference']['session_bytes']])
    def prefix_only():
        result = invoke(fn, store, answer)
        return result['operation_result'] == answer['expected_result'] and result['boundary'] is None and not log
    checks.check('saved_result_without_boundary_is_not_unknown', prefix_only)
    for field in ('locator', 'source_result_ref', 'harness_ref', 'input_ref'):
        derived_store, log, _ = derived(answer, private/('bad-boundary-'+field), lambda raw, field=field: change_boundary(raw, 'op-1', field))
        checks.rejected('stored_boundary_'+field, lambda derived_store=derived_store: invoke(fn, derived_store, answer))
    for namespace, value in [('pi.result', answer['expected_result']), ('lore.s.binding', answer['expected_binding'])]:
        derived_store, log, _ = derived(answer, private/('rewrite-'+namespace), lambda raw, namespace=namespace, value=value: append_rewrite(raw, 'op-1', namespace, value))
        checks.rejected('post_prefix_rewrite_'+namespace, lambda derived_store=derived_store: invoke(fn, derived_store, answer))
    for fault in ('missing', 'changed'):
        derived_store, log, confirmed = derived(answer, private/('source-'+fault), lambda raw: raw)
        path = Path(confirmed['snapshot_ref']['archive_path'])
        if fault == 'missing': path.unlink()
        else:
            raw = bytearray(path.read_bytes()); raw[len(raw)//2] ^= 1; path.write_bytes(raw)
        checks.rejected('actual_source_'+fault, lambda derived_store=derived_store: invoke(fn, derived_store, answer))
    checks.check('no_registry_updates_or_forbidden_side_effects', lambda: not callbacks and not FORBIDDEN)
    save(out/'observed.json', observed)
    return checks.rows


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--batch', required=True)
    parser.add_argument('--control', choices=['always-green'])
    args = parser.parse_args()
    if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch): raise ValueError('bounded batch ID')
    out = HERE/'evidence'/args.batch; out.mkdir(parents=True)
    protocol = json.loads((HERE/'protocol.json').read_bytes())
    sources = {p: h for item in protocol['fixtures'] for p, h in item['source_files'].items()}
    current = [ROOT/'lore_session/snapshot_files.py', ROOT/'lore_session/snapshots.py', HERE/'run.py', HERE/'protocol.json', ROOT/'design/g3/s/reference-contract.md']
    candidate = ROOT/'lore_session/references.py'
    if candidate.exists(): current.append(candidate)
    before = {str(p): digest(p.read_bytes()) for p in current}
    record = dict(status='MISSING', tests_run=0, checks=[], source_before=before, original_sources=sources)
    try:
        if any(digest(Path(p).read_bytes()) != h for p, h in sources.items()): raise ValueError('original evidence source drift')
        try: module = importlib.import_module('lore_session.references')
        except ModuleNotFoundError as error:
            if error.name != 'lore_session.references': raise
            record['missing'] = str(error); save(out/'result.json', record); print(json.dumps({'status':'MISSING','tests_run':0})); return 2
        function = module.resolve_original
        if args.control:
            item = protocol['fixtures'][0]; store = original_store(item, [])
            fixed = function(store, item['confirmation_request_id'], item['reference'], item['expected_binding'])
            function = lambda *args: json_copy(fixed)
        rows = exercise(function, protocol, out)
        after = {str(p): digest(p.read_bytes()) for p in current}
        intact = all(digest(Path(p).read_bytes()) == h for p, h in sources.items())
        record.update(checks=rows, tests_run=len(rows), source_after=after, source_unchanged=before == after,
                      original_sources_unchanged=intact, actual_module_path=module.__file__, forbidden=FORBIDDEN)
        record['status'] = 'PASS' if all(r['passed'] for r in rows) and before == after and intact else 'FAIL'
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
    save(out/'result.json', record)
    print(json.dumps({k:record.get(k) for k in ['status','tests_run','error']}))
    return 0 if record['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
