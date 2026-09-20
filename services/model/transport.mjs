// loom/1 supplies framing and capability negotiation; vscode-jsonrpc owns RPC.
import net from 'node:net';
import { TextDecoder } from 'node:util';
import { AbstractMessageReader, AbstractMessageWriter, createMessageConnection, ResponseError } from 'vscode-jsonrpc/node';
import { recordTransfer } from './records.mjs';

const HANDSHAKE = 65536;
const MAX_FRAME = 4 * 1024 * 1024;
export function createWorkerConnection(role, capabilities = []) {
  const socket = new net.Socket({ fd: 3, readable: true, writable: true });
  let limit = HANDSHAKE;
  let ready = false;
  let records;
  class Reader extends AbstractMessageReader {
    listen(callback) {
      let pending = Buffer.alloc(0);
      socket.on('data', chunk => {
        try {
          pending = Buffer.concat([pending, chunk]);
          while (true) {
            const end = pending.indexOf(10);
            if (end < 0) { if (pending.length > limit) throw new Error('frame limit'); break; }
            if (end > limit) throw new Error('frame limit');
            const frame = pending.subarray(0, end); pending = pending.subarray(end + 1);
            const message = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(frame));
            if (!message || typeof message !== 'object' || Array.isArray(message)) throw new Error('object required');
            callback(message);
          }
        } catch { this.fireError(new Error('Invalid loom/1 frame')); socket.destroy(); }
      });
      socket.on('error', error => this.fireError(error));
      socket.on('close', () => this.fireClose());
      return { dispose() { socket.destroy(); } };
    }
  }
  class Writer extends AbstractMessageWriter {
    async write(message) {
      const body = Buffer.from(JSON.stringify(message));
      if (body.length > limit) throw new Error('RPC frame exceeds negotiated limit');
      await new Promise((resolve, reject) => socket.write(Buffer.concat([body, Buffer.from('\n')]), error => error ? reject(error) : resolve()));
    }
    end() { socket.end(); }
  }
  const connection = createMessageConnection(new Reader(), new Writer());
  const onRequest = connection.onRequest.bind(connection);
  const available = [role + '/1', ...capabilities];
  onRequest('session.hello', params => {
    if (ready || params?.protocol_version !== 'loom/1' || params.role !== 'runtime' || params.peer_role !== role ||
        !Number.isInteger(params.max_frame_bytes) || params.max_frame_bytes < HANDSHAKE ||
        !Array.isArray(params.required_capabilities) || params.required_capabilities.some(c => !available.includes(c))) {
      throw new ResponseError(-32001, 'unsupported_version or capability_missing');
    }
    limit = Math.min(MAX_FRAME, params.max_frame_bytes);
    if(role==='model' && params.session?.record_directory) records=recordTransfer(params.session.record_directory);
    ready = true;
    return { protocol_version: 'loom/1', schema_version: 1, role, max_frame_bytes: limit, capabilities: available };
  });
  connection.onRequest = (method, handler) => onRequest(method, (params, token) => {
    if (!ready) throw new ResponseError(-32001, 'session.hello is required');
    return Promise.resolve(handler(records?records.unpack(params):params, token)).then(value=>records?records.pack(value):value);
  });
  const sendRequest=connection.sendRequest.bind(connection);
  connection.sendRequest=async(method,params,...rest)=>{
    const result=await sendRequest(method,records?records.pack(params):params,...rest);
    return records?records.unpack(result):result;
  };
  socket.on('end', () => process.exit(0));
  return connection;
}
