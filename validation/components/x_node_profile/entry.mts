// Ordinary external verification Harness. No credentials, network provider, or X import.
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as crypto from 'node:crypto';
import * as readline from 'node:readline';
import * as net from 'node:net';
import {once} from 'node:events';
const [mode, work, peerIP, peerPort] = process.argv.slice(2);
const hash = (data: Buffer) => crypto.createHash('sha256').update(data).digest('hex');
const write = (name: string, data: Buffer | string) => {
  const fd = fs.openSync(path.join(work, name), 'w', 0o600);
  try { fs.writeFileSync(fd, data); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
};
const emit = (value: unknown) => process.stdout.write(JSON.stringify(value) + '\n');
const statfs = (mount: string) => {
  const value = fs.statfsSync(mount, {bigint: true});
  return {mount, bytes: Number(value.bsize * value.blocks), bytes_free: Number(value.bsize * value.bavail),
    inodes: Number(value.files), inodes_free: Number(value.ffree)};
};
const walk = (root: string): any[] => {
  const result: any[] = [];
  const visit = (current: string) => {
    for (const name of fs.readdirSync(current).sort()) {
      const full = path.join(current, name), st = fs.lstatSync(full);
      if (st.isDirectory()) { result.push({path: path.relative(root, full), kind: 'dir'}); visit(full); }
      else if (st.isFile()) { const raw = fs.readFileSync(full); result.push({path: path.relative(root, full), kind: 'file', bytes: raw.length, sha256: hash(raw)}); }
      else result.push({path: path.relative(root, full), kind: 'symlink', target: fs.readlinkSync(full)});
    }
  };
  visit(root); return result;
};
if (mode.startsWith('pi-')) {
  process.argv[2] = mode.slice(3);
  await import('./pi-probe.mts'); process.exit(0);
} else if (mode === 'channel') {
  process.argv[2] = fs.existsSync(path.join(work, 'metadata.json')) ? 'query' : 'accept';
  const pi = await import('./pi-probe.mts');
  process.argv[2] = mode;
  const fd = fs.openSync(path.join(work, 'channel.jsonl'), 'a', 0o600);
  const receivedFD = fs.openSync(path.join(work, 'received.bin'), 'a', 0o600);
  let received = fs.fstatSync(receivedFD).size;
  process.stdin.on('data', (chunk: Buffer) => {
    fs.writeSync(receivedFD, chunk); fs.fsyncSync(receivedFD); received += chunk.length;
    emit({kind: 'input-received', received_bytes: received, pid: process.pid});
  });
  emit({kind: 'ready', pid: process.pid, mode});
  for await (const line of readline.createInterface({input: process.stdin, crlfDelay: Infinity})) {
    const call = JSON.parse(line);
    if (call.op === 'exit') { emit({kind: 'closed', pid: process.pid}); break; }
    if (typeof call.nonce !== 'string' || call.nonce.length > 4096) throw new Error('finite fixture nonce');
    // Ordinary fixture data through the actual public Session API, not another pending operation.
    const address = pi.value('lore.fixture.channel', call.nonce);
    await pi.session.setValue(address, {nonce: call.nonce}, pi.context);
    if ((await pi.session.getValue(address, pi.context))?.value?.nonce !== call.nonce) throw Error('actual Pi value readback mismatch');
    const event = {kind: 'accepted', nonce: call.nonce, pid: process.pid};
    fs.writeSync(fd, JSON.stringify(event) + '\n'); fs.fsyncSync(fd); emit(event);
  }
  fs.closeSync(fd); fs.closeSync(receivedFD);
} else if (mode === 'read-files' || mode === 'isolation') {
  const attempts: any[] = [];
  for (const root of ['/opt', '/harness', '/input', '/workspace', '/']) {
    try { const p = root + '/xn-forbidden-write'; fs.writeFileSync(p, 'bad'); attempts.push({root, wrote: true}); }
    catch (error: any) { attempts.push({root, wrote: false, code: error.code}); }
  }
  const forbidden: any[] = [];
  for (const p of ['/control/canary', '/var/run/docker.sock', '/proc/1/root/control/canary']) {
    try { forbidden.push({path: p, bytes: fs.readFileSync(p).toString('base64')}); } catch {}
  }
  const fds: any[] = [];
  for (const name of fs.readdirSync('/proc/self/fd')) {
    try { fds.push({fd: Number(name), target: fs.readlinkSync('/proc/self/fd/' + name)}); } catch {}
  }
  let connection: any = null;
  if (mode === 'isolation') {
    connection = await new Promise(resolve => {
      const socket = net.createConnection({host: peerIP, port: Number(peerPort)});
      socket.setTimeout(500);
      socket.on('connect', () => { socket.destroy(); resolve({connected: true}); });
      socket.on('error', (e: any) => { socket.destroy(); resolve({connected: false, code: e.code}); });
      socket.on('timeout', () => { socket.destroy(); resolve({connected: false, code: 'TIMEOUT'}); });
    });
  }
  const value = {kind: 'read-files', pid: process.pid, node_version: process.version, uid: process.getuid!(), gid: process.getgid!(),
    status: fs.readFileSync('/proc/self/status', 'utf8'), environment: fs.readFileSync('/proc/self/environ').toString('base64'),
    fd: fds, attempts, forbidden, connection, input: walk('/input'), workspace: walk('/workspace'),
    mounts: ['/work', '/tmp', '/dev/shm'].map(statfs)};
  write('observed.json', JSON.stringify(value)); emit(value);
  // Keep the original task observable until the external collector has read its UID/cgroup/mounts.
  for await (const line of readline.createInterface({input: process.stdin, crlfDelay: Infinity})) { if (line !== 'release') throw Error('explicit observation release required'); break; }
  process.stdin.destroy(); // This finite fixture is done reading; do not await peer EOF.
} else if (mode.startsWith('quota-')) {
  const fds: number[] = [], paths: string[] = []; let error: any = null;
  try {
    if (mode === 'quota-inodes') {
      for (let i = 0; ; i++) { const p = path.join(work, 'fill-' + i); fds.push(fs.openSync(p, 'w', 0o600)); paths.push(p); }
    } else {
      const p = path.join(work, 'fill-bytes'), fd = fs.openSync(p, 'w', 0o600); fds.push(fd);
      if (mode === 'quota-unlinked') fs.unlinkSync(p); else paths.push(p);
      const block = Buffer.alloc(65536, 120); while (true) fs.writeSync(fd, block);
    }
  } catch (e: any) { error = {code: e.code, errno: e.errno}; }
  const observed = {kind: 'quota-full', pid: process.pid, mode, error, mounts: ['/work', '/tmp', '/dev/shm'].map(statfs)};
  emit(observed);
  for await (const line of readline.createInterface({input: process.stdin, crlfDelay: Infinity})) { if (line !== 'release') throw Error('explicit release required'); break; }
  process.stdin.destroy(); // This finite fixture is done reading; do not await peer EOF.
  for (const fd of fds) fs.closeSync(fd); for (const p of paths) fs.unlinkSync(p);
  write('quota.json', JSON.stringify(observed)); emit({kind: 'quota-released', mounts: ['/work', '/tmp', '/dev/shm'].map(statfs)});
} else if (mode === 'output-flood') {
  let released = false;
  emit({kind: 'flood-ready', pid: process.pid});
  for await (const line of readline.createInterface({input: process.stdin, crlfDelay: Infinity})) {
    if (line !== 'release') throw Error('explicit flood release required');
    released = true; break;
  }
  if (!released) throw Error('flood input ended before explicit release');
  process.stdin.destroy();
  const block = Buffer.alloc(65536, 120);
  while (true) {
    if (!process.stdout.write(block)) await once(process.stdout, 'drain');
    if (!process.stderr.write(block)) await once(process.stderr, 'drain');
  }
} else { throw new Error('unknown preregistered fixture mode'); }
