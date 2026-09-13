"""Short S validation callers forward to one real X owner; no per-call task EOF."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from lore_execution import ExecutionStore
from lore_session.execution import SessionRun
from f_peer import Peer, canonical, digest, file_fact, require, save
from execution_plans import ExecutionPlans
from tool_results import complete_tool
from session_fault import prepare_fault
from lore_session.tool_authority import require_tool_target
from native_preflight import preflight

CAP = 2097152


def receive(stream):
    data = bytearray()
    while not data.endswith(b'\n'):
        part = stream.recv(min(65536, CAP+1-len(data)))
        require(part and len(data)+len(part) <= CAP, 'incomplete/oversized control frame')
        data.extend(part)
    return json.loads(data)


class Controller:
    def __init__(self, root, authority):
        self.root, self.authority = root, authority
        self.froot = root.parent / 'f-port'
        self.plans = self.x = None
        self.runs, self.tools, self.run_plans, self.tool_plans = {}, {}, {}, {}

    def peer(self):
        return Peer(self.froot, self.authority)

    def call(self, method, params):
        if method in ('execute', 'query', 'resolve_result_stdout', 'test_cleanup', 'close_fixture', 'test_fault_input', 'authorize_original_native'):
            require(params.get('authority') == self.authority, 'untrusted fixture caller')
        if method == 'close_fixture':
            return self.cleanup()
        if method == 'execute':
            requested = params['request']
            if requested['target'] == 'session':
                if self.plans is None:
                    peer = self.peer()
                    self.plans = ExecutionPlans(self.root / 'plans', peer, requested['session_scope']['namespace'], deps_mount=self.authority['deps_mount'])
                self.plans.peer = self.peer()
                plan = self.plans.session(requested, execution_id=requested["execution_id"])
                if self.x is None:
                    self.x = ExecutionStore(self.plans.state_root, trusted_config=str(self.plans.config_path),
                                            trusted_config_sha256=self.plans.config_sha)
                run = SessionRun(self.x, self.plans.snapshots, plan['request'], plan['authority'], requested['operation_id'])
                response = run.start(); self.runs[run.id] = run; self.run_plans[run.id] = plan
                self.last_session_request = requested
                binding = {**response['binding'], 'private_volume_id':response['binding']['volume_id']}
                return dict(execution_binding=binding, channel_binding=binding)
            require(self.x is not None, 'tool outside active trusted Session')
            require_tool_target(requested['target'], requested['script'])
            self.plans.peer = self.peer()
            plan = self.plans.tool(self.last_session_request, requested['target'], requested['script'],
                                   execution_id=requested['execution_id'], source_result_ref=requested['source_result'])
            result = complete_tool(self.x, self.plans, plan, requested, self.plans.peer)
            self.tools[requested['execution_id']] = result
            self.tool_plans[requested['execution_id']] = plan
            return result
        if method == 'resolve_result_stdout':
            ref = params['original_result_ref']; saved = self.tools[ref['execution_id']]
            require(saved['result_ref'] == ref, 'original result reference differs')
            original = saved['stdout_ref']; self.x.journal.read(original, 65536)
            return dict(path=original['path'], sha256=original['sha256'], bytes=original['size'])
        if method == 'query':
            # Tool pending reconciliation is readonly and never dispatches missing identities.
            eid = params['execution_id']; saved = self.tools.get(eid)
            if saved is None:
                return dict(status='UNKNOWN')
            actual = self.x.query(eid, self.tool_plans[eid]['authority'])
            ref = saved['result_ref']; receipt = ref['original_receipt']
            require(file_fact(receipt['path']) == receipt, 'original X response copy differs')
            original = json.loads(Path(receipt['path']).read_bytes())
            require(original['binding'] == actual['binding'] and original['result'] == actual['result'], 'original execution query differs')
            self.x.journal.read(saved['stdout_ref'], 65536)
            return saved
        if method == 'test_fault_input':
            require(self.plans is not None, 'fault input requires original Session plan')
            return prepare_fault(self.plans, params['reference'], params['fault'], params['authority'])
        if method == 'test_cleanup':
            return self.cleanup()
        run = self.runs[params['execution_id']]
        require(all(params.get(k) == run.binding.get(k) for k in ('container_id', 'object_generation', 'channel_id', 'request_digest')),
                'original execution channel scope differs')
        if method == 'authorize_original_native':
            return preflight(self, run, params)
        if method == 'resolve_session_read':
            reference = params['reference']; selected = Path(reference['path'])
            mounts = self.run_plans[run.id]['request']['readonly_mounts']
            matches = [m for m in mounts if selected.is_relative_to(m['target'])]
            require(len(matches) == 1, 'read reference outside authorized ordinary mounts')
            mount = matches[0]; root = Path(mount['source']['path'])
            actual = root / selected.relative_to(mount['target'])
            require(actual.resolve(strict=True).is_relative_to(root.resolve(strict=True)), 'read path escaped its original mount')
            fact = file_fact(actual)
            require(all(fact[k] == reference[k] for k in ('bytes', 'sha256')), 'original recalled bytes differ')
            return fact
        if method == 'channel_write':
            return run.write(base64.b64decode(params['data_b64'], validate=True), params['call_fields'])
        if method == 'channel_read':
            return run.read(params['limit_bytes'], params['calls'])
        if method == 'close_stdin':
            return run.close_stdin(params['call_fields'])
        if method == 'checkpoint':
            if params['purpose'] == 'raw_failed_input':
                return run.quarantine(params['checkpoint_id'], params['reason'])
            return run.checkpoint(params['checkpoint_id'], params['purpose'])
        if method in ('resume', 'seal'):
            return getattr(run, method)(params['checkpoint_receipt'])
        if method == 'request_stop':
            return run.request_stop(params['stop_id'])
        if method == 'release':
            return run.release()
        raise ValueError('unimplemented trusted fixture method: '+method)

    def cleanup(self):
        rows = []
        if self.x is not None:
            for path in sorted(self.x.journal.root.glob('*/record.json')):
                record = json.loads(path.read_bytes()); binding = record['binding']
                cid, volume = binding.get('container_id'), binding.get('volume_id')
                if cid:
                    self.x.engine.call('DELETE', '/containers/'+cid+'?force=true', missing=True)
                if volume:
                    self.x.engine.call('DELETE', '/volumes/'+volume, missing=True)
                absent = (not cid or self.x.engine.inspect(cid) is None) and (not volume or self.x.engine.call('GET', '/volumes/'+volume, missing=True) is None)
                rows.append(dict(binding=binding, actual_absent=absent))
                require(absent, 'original test resource remains')
            self.x.journal.close()
        save(self.root / 'physical-cleanup.json', dict(objects=rows, controller_pid=os.getpid()))
        return dict(objects=rows)


def serve(root, authority, path):
    controller = Controller(root, authority); closed = False
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path); os.chmod(path, 0o600); server.listen(1)
        save(root/'controller.json', dict(pid=os.getpid(), socket=path, source=file_fact(Path(__file__).resolve()),
            actual_modules={name:file_fact(Path(module.__file__).resolve()) for name,module in sys.modules.items()
                if getattr(module, '__file__', None) and (name.startswith('lore_') or name.startswith('validation.'))}))
        try:
            while not closed:
                with server.accept()[0] as peer:
                    peer.settimeout(30); request = None
                    try:
                        request = receive(peer)
                        require(request['protocol'] == 'LORE_COMPONENT_TEST/1' and Path(request['fixture_root']) == root, 'peer fixture scope differs')
                        with (controller.froot / '.fixture-lock').open('a+b') as lock:
                            fcntl.flock(lock, fcntl.LOCK_EX)
                            result = dict(result=controller.call(request['method'], request['params']))
                        closed = request['method'] == 'close_fixture'
                    except Exception as exc:
                        result = dict(error=repr(exc), traceback=traceback.format_exc())
                    try:
                        peer.sendall(canonical(result)+b'\n')
                    except OSError:
                        # Lost caller ACK does not kill the original X owner or replay its action.
                        pass
        finally:
            try:
                if not closed:
                    controller.cleanup()
            finally:
                if Path(path).exists():
                    os.unlink(path)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--serve', type=Path)
    args = parser.parse_args(); authority = json.loads(args.authority.read_bytes())
    if args.serve:
        root = args.serve.resolve(); path = '/tmp/lore-s-peer-'+digest(str(root).encode())+'.sock'
        serve(root, authority, path); return
    request = json.loads(sys.stdin.buffer.read(CAP+1)); root = Path(request['fixture_root']).resolve(strict=True)
    path = '/tmp/lore-s-peer-'+digest(str(root).encode())+'.sock'
    with (root/'.bootstrap-lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not Path(path).exists():
            require(request['method'] == 'execute', 'original shared X owner unavailable; no automatic replay')
            with (root/'controller.stderr').open('ab') as error:
                subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--authority', str(args.authority.resolve()), '--serve', str(root)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=error, close_fds=True, start_new_session=True)
            end = time.monotonic()+10
            while not Path(path).exists():
                require(time.monotonic() < end, 'shared X owner startup timeout')
                time.sleep(.01)
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(30); peer.connect(path); peer.sendall(canonical(request)+b'\n')
        result = receive(peer)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
