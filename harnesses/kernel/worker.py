"""Reference ordinary-code Harness, loom/1 over inherited FD 3."""
import json
import hashlib
import os
from pathlib import Path
import socket
import sqlite3
import sys
import threading
from pylsp_jsonrpc.endpoint import Endpoint

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
from policy import Kernel, ProjectionError

kernel = Kernel(Path(__file__).parent)
channel = socket.socket(fileno=3)
reader = channel.makefile('rb')
writer = channel.makefile('wb')
lock = threading.Lock()
limit = 65536
ready = False
capabilities = ['harness/1', 'context.feedback/1', 'userspace.binding/1']


def hello(params):
    global limit, ready
    if (ready or params.get('protocol_version') != 'loom/1' or params.get('role') != 'runtime'
        or params.get('peer_role') != 'harness'
        or any(c not in capabilities for c in params.get('required_capabilities', []))):
        raise ValueError('unsupported_version or capability_missing')

    if 'context.feedback/1' not in (params.get('capabilities') or []):
        raise ValueError('capability_missing: context.feedback/1')
    requested = params.get('max_frame_bytes')
    if type(requested) is not int or requested < 65536:
        raise ValueError('invalid frame limit')
    limit = min(requested, 4 * 1024 * 1024)
    ready = True
    return {'protocol_version': 'loom/1', 'schema_version': 1, 'role': 'harness',
            'max_frame_bytes': limit, 'capabilities': capabilities}


def guarded(fn):
    def invoke(params):
        if not ready:
            raise ValueError('session.hello required')
        def execute():
            if 'turn_ref' in params:
                raw = Path(params['turn_path']).read_bytes()
                ref = params['turn_ref']
                if str(len(raw)) != ref['size_bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
                    raise ValueError('native turn integrity failure')
                params['turn'] = json.loads(raw)
            return fn(params)
        return execute
    return invoke


def send(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    if len(raw) > limit:
        raise ValueError('frame limit exceeded')
    with lock:
        writer.write(raw + b'\n')
        writer.flush()


class FixedFiles:
    def __init__(self, root):
        self.root = root.resolve(strict=True)

    def get(self, name, default=None):
        try:
            candidate = (self.root / name).resolve(strict=True)
            candidate.relative_to(self.root)
            if candidate.is_file():
                return candidate.read_bytes().decode('utf-8')
        except (OSError, ValueError, UnicodeError):
            pass
        return default


def projection_input(params):
    # Paths are scoped mounts chosen by Runtime, not filesystem grants supplied
    # by model text. The pure renderer never performs ambient host reads.
    root = Path(params['files_root'])
    # Only the main template and explicitly included text are read. Large code
    # trees and binary dependencies are retained without eagerly loading them.
    params['surface'] = FixedFiles(root / 'surface')
    params['work_files'] = FixedFiles(root)
    params['resources'] = {alias: FixedFiles(Path(bindings['source']['root']))
                           for alias, bindings in params.get('resource_views', {}).items()}
    params['resource_targets'] = {alias: {target: FixedFiles(Path(binding['root']))
                                for target, binding in bindings.items()}
                                 for alias, bindings in params.get('resource_views', {}).items()}
    facts = []
    with sqlite3.connect('file:' + params['facts_database'] + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        meta = db.execute('SELECT * FROM view_meta').fetchone()
        if meta['schema_version'] != 1 or meta['view_id'] != params['view_id'] or meta['fact_watermark'] != params['fact_watermark']:
            raise ValueError('not_ready: fixed fact view does not match projection boundary')
        for row in db.execute('SELECT * FROM facts ORDER BY ordinal'):
            fact = dict(row)
            raw = Path(fact['record_path']).read_bytes()
            ref = json.loads(fact['record_ref'])
            import hashlib
            if str(len(raw)) != ref['size_bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
                raise ValueError('fact record integrity failure')
            fact['record_ref'] = ref
            fact['payload'] = json.loads(raw)
            facts.append(fact)
    params['facts'] = facts
    return params


def publish_projection(params, prepare=False):
    try:
        result = kernel.prepare(projection_input(params)) if prepare else kernel.start(projection_input(params))
    except ProjectionError as error:
        return {'projection_error': {'file': 'surface/main.md', 'diagnostic': str(error)[:16384]}}
    # File publication keeps immutable projections independent of RPC frame size.
    import uuid
    name = str(uuid.uuid4()) + '.json'
    path = Path(params['output_directory']) / name
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    ref = endpoint.request('record.put', {'protocol_version': 'loom/1', 'schema_version': 1,
                'path': name, 'media_type': 'application/vnd.loom.projection+json'}).result(timeout=20)
    published = endpoint.request('projection.publish', {'protocol_version': 'loom/1', 'schema_version': 1,
                'record_ref': ref, 'content_version': params['content_version'],
                'harness_ref': params['harness_ref'], 'view_id': params['view_id']}).result(timeout=20)
    if params.get('model_operation') == 'model.start':
        return endpoint.request('model.start', {'protocol_version': 'loom/1', 'schema_version': 1,
                    'projection_ref': published['projection_ref'], 'request_key': 'advance:' + params['view_id']}).result(timeout=20)
    return published


def resume(params):
    return endpoint.request('model.resume', {'protocol_version': 'loom/1', 'schema_version': 1,
                'checkpoint_id': params['checkpoint_id'], 'request_key': 'resume:' + params['checkpoint_id']}).result(timeout=20)


def finish(params):
    checkpoint = endpoint.request('checkpoint.commit', {'protocol_version': 'loom/1', 'schema_version': 1,
                'content_version': params['content_version'], 'previous_checkpoint_id': params['previous_checkpoint_id'],
                'resource_copies': params['resource_copies']}).result(timeout=20)
    return endpoint.request('round.handoff', {'protocol_version': 'loom/1', 'schema_version': 1,
                'checkpoint_id': checkpoint['checkpoint_id'], 'handled_input_ids': params['claimed_input_ids'],
                'intent': 'wait'}).result(timeout=20)


handlers = {'session.hello': hello, 'policy.admit': guarded(lambda p: True),
            'policy.resume': guarded(resume),
            'policy.finish': guarded(finish),
            'policy.start': guarded(publish_projection), 'policy.continue': guarded(kernel.continuation),
            'policy.prepare': guarded(lambda p: publish_projection(p, prepare=True))}
endpoint = Endpoint(handlers, send)
try:
    while True:
        line = reader.readline(limit + 2)
        if not line:
            break
        if len(line) > limit + 1 or not line.endswith(b'\n'):
            raise ValueError('frame limit or incomplete frame')
        value = json.loads(line.decode('utf-8'))
        if not isinstance(value, dict):
            raise ValueError('batch unsupported')
        if value.get('method') and 'id' not in value and value['method'] != '$/cancelRequest':
            continue
        endpoint.consume(value)
finally:
    endpoint.shutdown()
    reader.close()
    writer.close()
    channel.close()
