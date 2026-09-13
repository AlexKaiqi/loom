"""Finite external JSONL transport. No semantic cache, write replay, or slot authority."""
from pathlib import Path
import json, os, selectors, signal, socket, struct, subprocess, sys, threading, time, uuid
from artifacts import canonical, file_fact, save, InvalidEvidence, require, strict_json
ROOT = Path(__file__).resolve().parents[3]
CAP = 2097152

class Rpc:
    def __init__(self, argv, fixture, out):
        self.argv = list(argv) + ['--trusted-config', str(fixture.config_path), '--trusted-config-sha256', file_fact(fixture.config_path)[0]['sha256']]
        self.fx = fixture; self.out = Path(out); self.out.mkdir(parents=True, exist_ok=False)
        self.serial = 0; self.buffer = b''; self.p = None; self.sel = None; self.lock = threading.Lock()
        self.start()
    def start(self):
        self.buffer=b''
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(self.fx.root),
               'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1',
               'LORE_X_STATE_DIR': str(self.fx.state), 'LORE_X_CACHE_DIR': str(self.fx.cache),
               'LORE_TEST_CONTROL_CANARY': self.fx.canary.decode()}
        self.control_fd = os.open(self.fx.root / 'control/control-canary', os.O_RDONLY)
        self.control_peer, self.control_child = socket.socketpair()
        self.p = subprocess.Popen(self.argv, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, close_fds=True, pass_fds=(self.control_fd, self.control_child.fileno()), start_new_session=True)
        with (self.out / 'adapter-processes.jsonl').open('a') as f:
            f.write(json.dumps({'pid': self.p.pid, 'argv': self.argv, 'cwd': str(ROOT), 'environment': env}) + '\n'); f.flush(); os.fsync(f.fileno())
        self.sel = selectors.DefaultSelector(); self.sel.register(self.p.stdout, selectors.EVENT_READ, 'stdout'); self.sel.register(self.p.stderr, selectors.EVENT_READ, 'stderr')
        os.set_blocking(self.p.stdin.fileno(), False)
        if os.environ.get('LORE_X_REQUIRE_SOURCE_AUDIT') == '1':
            sys.path.insert(0, str(ROOT / 'validation/components/x'))
            from runtime_observations import await_source_start
            await_source_start(self.p, self.argv, ROOT, self.out)
    def call(self, method, args, barrier=None):
        with self.lock:
            self.serial += 1
            frame = {'request_id': 'xn-control-' + str(self.serial), 'method': method, 'arguments': args}
            path = self.out / f'call-{self.serial:04d}'; save(path.with_suffix('.request.json'), frame)
            raw = canonical(frame) + b'\n'; require(len(raw) <= CAP, 'external control request cap')
            deadline = time.monotonic() + 30; written = 0; stdout = bytearray(); stderr = bytearray(); response = None
            try:
                while written < len(raw):
                    require(time.monotonic() < deadline and self.p.poll() is None, 'candidate control write unavailable')
                    try: written += os.write(self.p.stdin.fileno(), raw[written:written + 65536])
                    except BlockingIOError:
                        selector = selectors.DefaultSelector(); selector.register(self.p.stdin, selectors.EVENT_WRITE)
                        try: selector.select(min(.02, max(0, deadline-time.monotonic())))
                        finally: selector.close()
                while time.monotonic() < deadline:
                    while b'\n' in self.buffer:
                        line, self.buffer = self.buffer.split(b'\n', 1); value = strict_json(line)
                        if barrier is not None and value.get('test_barrier') == barrier: response = value; return value
                        require(value.get('request_id') == frame['request_id'], 'wrong control response correlation')
                        response = value; return value
                    for key, _ in self.sel.select(.02):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            self.sel.unregister(key.fileobj)
                            require(key.data != 'stdout', 'candidate ended before original response')
                            continue
                        if key.data == 'stdout': self.buffer += chunk; stdout += chunk
                        else: stderr += chunk
                        require(len(stdout) + len(stderr) <= CAP, 'external control response cap')
                raise InvalidEvidence('candidate original response deadline')
            finally:
                path.with_suffix('.stdout').write_bytes(stdout); path.with_suffix('.stderr').write_bytes(stderr)
                save(path.with_suffix('.transport.json'), {'candidate_pid': self.p.pid, 'control_bytes_written': written,
                                                          'response': response, 'semantic_receipt_owner': 'X candidate, never this transport'})
    def stop(self):
        if self.p and self.p.poll() is None:
            os.killpg(self.p.pid, signal.SIGKILL); self.p.wait(timeout=3)
        if self.sel: self.sel.close()
        if self.p:
            for stream in (self.p.stdin, self.p.stdout, self.p.stderr): stream.close()
        for name in ('control_fd',):
            value = getattr(self, name, None)
            if value is not None: os.close(value); setattr(self, name, None)
        for name in ('control_peer', 'control_child'):
            value = getattr(self, name, None)
            if value: value.close(); setattr(self, name, None)

class ShortPeerBridge:
    """One transient channel owner. Kernel peer credentials logged, no response cache."""
    def __init__(self, rpc, out):
        self.rpc = rpc; self.out = Path(out); self.out.mkdir(parents=True, exist_ok=False)
        self.path = Path('/tmp') / ('lore-xn-' + uuid.uuid4().hex + '.sock')
        self.server = socket.socket(socket.AF_UNIX); self.server.bind(str(self.path)); os.chmod(self.path, 0o600)
        self.server.listen(1); self.server.settimeout(.1); self.stopped = threading.Event(); self.rows = []
        self.thread = threading.Thread(target=self.serve, daemon=True); self.thread.start()
    def serve(self):
        while not self.stopped.is_set():
            try: peer, _ = self.server.accept()
            except socket.timeout: continue
            except OSError: return
            with peer:
                peer.settimeout(30); pid, uid, gid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                raw = bytearray()
                try:
                    while not raw.endswith(b'\n'):
                        chunk = peer.recv(65536); require(bool(chunk), 'short peer partial frame')
                        raw += chunk; require(len(raw) <= CAP, 'short peer cap')
                    call = strict_json(bytes(raw)); require(set(call) == {'method', 'arguments'}, 'thin bridge frame fields')
                    result = self.rpc.call(call['method'], call['arguments'])
                    payload = canonical(result) + b'\n'; require(len(payload) <= CAP, 'short response cap'); peer.sendall(payload)
                    row = {'pid': pid, 'uid': uid, 'gid': gid, 'call': call, 'forwarded': True, 'original_candidate_pid': self.rpc.p.pid}
                except Exception as exc:
                    row = {'pid': pid, 'uid': uid, 'gid': gid, 'error': repr(exc), 'forwarded': False}
                    try: peer.sendall(canonical({'transport_error': repr(exc)}) + b'\n')
                    except OSError: pass
                self.rows.append(row)
                (self.out / 'actual-peer-credentials.json').write_bytes(canonical(self.rows) + b'\n')
    def call(self, method, args):
        n = len(list(self.out.glob('peer-*.request.json'))) + 1
        request = self.out / f'peer-{n:03d}.request.json'; save(request, {'method': method, 'arguments': args})
        argv = [sys.executable, '-B', str(Path(__file__).with_name('short_peer.py')), str(self.path), str(request)]
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        try: stdout, stderr = process.communicate(timeout=35)
        except subprocess.TimeoutExpired: process.kill(); stdout, stderr = process.communicate(); raise InvalidEvidence('short peer deadline')
        finally: save(self.out / f'peer-{n:03d}.process.json', {'pid': process.pid, 'argv': argv, 'exit_code': process.returncode})
        (self.out / f'peer-{n:03d}.stdout').write_bytes(stdout); (self.out / f'peer-{n:03d}.stderr').write_bytes(stderr)
        require(process.returncode == 0 and len(stdout) <= CAP, 'short peer failed')
        value = strict_json(stdout); require('transport_error' not in value, 'bridge transport failed')
        return value
    def stop(self):
        self.stopped.set(); self.server.close(); self.thread.join(timeout=2)
        if self.path.exists(): self.path.unlink()
