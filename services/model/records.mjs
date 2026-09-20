// Local immutable record transfer. Control frames carry references, never large
// native contexts. The directory is granted by the trusted controller handshake.
import fs from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
const threshold = 256 * 1024;
export function recordTransfer(directory) {
  if (!path.isAbsolute(directory) || !fs.lstatSync(directory).isDirectory()) throw new Error('record directory required');
  const read = ref => {
    if (!ref || !/^[a-f0-9]{64}$/.test(ref.sha256) || !/^(0|[1-9][0-9]*)$/.test(ref.size_bytes) || ref.media_type !== 'application/json') throw new Error('invalid record reference');
    const file = path.join(directory, ref.sha256);
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || String(stat.size) !== ref.size_bytes || stat.size > 256 * 1024 * 1024) throw new Error('record size or type mismatch');
    const data = fs.readFileSync(file);
    if (createHash('sha256').update(data).digest('hex') !== ref.sha256) throw new Error('record digest mismatch');
    return JSON.parse(data.toString('utf8'));
  };
  const put = value => {
    const data = Buffer.from(JSON.stringify(value));
    const ref = {sha256:createHash('sha256').update(data).digest('hex'),size_bytes:String(data.length),media_type:'application/json'};
    const file = path.join(directory,ref.sha256);
    if (!fs.existsSync(file)) {
      const temporary = path.join(directory,'.record-'+randomUUID());
      const fd = fs.openSync(temporary,'wx',0o400);
      try {
        fs.writeFileSync(fd,data);fs.fsyncSync(fd);
        try {fs.linkSync(temporary,file);} catch(error) {if(error.code!=='EEXIST')throw error;}
        const parent=fs.openSync(directory,'r');try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}
      } finally {fs.closeSync(fd);fs.unlinkSync(temporary);}
    }
    read(ref);
    return ref;
  };
  return {
    unpack(value) {
      if(value?.payload_ref && Object.keys(value).length===1)return read(value.payload_ref);
      if(value?.context_ref){const {context_ref,...rest}=value;return {...rest,context:read(context_ref)};}
      return value;
    },
    pack(value) {return value !== undefined && Buffer.byteLength(JSON.stringify(value))>threshold?{payload_ref:put(value)}:value;},
  };
}
