import {createHash} from 'node:crypto';
import {readFileSync,lstatSync,realpathSync,openSync,closeSync,fsyncSync,writeFileSync,renameSync} from 'node:fs';
import {resolve,relative,dirname,isAbsolute} from 'node:path';
export class BoundaryError extends Error {constructor(public code:string,message:string){super(message);}}
export function requireValue(value:any,code:string,message:string):asserts value {if(!value)throw new BoundaryError(code,message);}
export const hash=(raw:Buffer|string)=>createHash('sha256').update(raw).digest('hex');
export function canonical(value:any):string {
 if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
 if(typeof value==='number'){requireValue(Number.isFinite(value),'invalid_request','nonfinite number');return JSON.stringify(value);}
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 requireValue(value&&typeof value==='object','invalid_request','finite JSON required');
 return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
}
export const equal=(a:any,b:any)=>canonical(a)===canonical(b);
export function json(raw:Buffer|string){try{
 const text=typeof raw==='string'?raw:new TextDecoder('utf-8',{fatal:true}).decode(raw);const parsed=JSON.parse(text);canonical(parsed);
 let at=0;const whitespace=()=>{while(/\s/.test(text[at]??'')&&at<text.length)at++;};
 const string=()=>{const start=at++;while(at<text.length){if(text[at]==='\\'){at+=2;continue;}if(text[at++]==='"')return JSON.parse(text.slice(start,at));}throw Error('string');};
 const walk=():void=>{whitespace();const c=text[at];if(c==='"'){string();return;}if(c==='{'||c==='['){at++;whitespace();const end=c==='{'?'}':']',keys=new Set();if(text[at]===end){at++;return;}for(;;){
  if(c==='{'){whitespace();const key=string();if(keys.has(key))throw Error('duplicate key');keys.add(key);whitespace();at++;}walk();whitespace();if(text[at++]===end)return;
 }}else {while(at<text.length&&!/[\s,}\]]/.test(text[at]))at++;}};walk();return parsed;
 }catch{throw new BoundaryError('session_corrupt','invalid complete finite JSON');}}
export function readFile(path:string,root:string,cap=16777216):Buffer {
 requireValue(isAbsolute(path),'invalid_request','absolute configured path required');
 const rel=relative(resolve(root),resolve(path));requireValue(rel!==''&&!rel.startsWith('../')&&!isAbsolute(rel),'invalid_request','file outside configured root');
 const stat=lstatSync(path);requireValue(stat.isFile()&&!stat.isSymbolicLink()&&stat.size<=cap,'integrity_mismatch','bounded ordinary file required');
 requireValue(realpathSync(path)===resolve(path),'integrity_mismatch','symlink ancestor rejected');
 const raw=readFileSync(path);requireValue(raw.length===stat.size,'integrity_mismatch','read length changed');return raw;
}
export function saveMetadata(path:string,value:any){
 const temp=path+'.part';writeFileSync(temp,JSON.stringify(value));let fd=openSync(temp,'r');try{fsyncSync(fd);}finally{closeSync(fd);}
 renameSync(temp,path);fd=openSync(dirname(path),'r');try{fsyncSync(fd);}finally{closeSync(fd);}
}
