import {existsSync,readdirSync,mkdirSync} from 'node:fs';
import {join,relative,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {BoundaryError,requireValue,readFile,json,equal,hash,saveMetadata} from './common.mts';
export async function loadPi(root:string){
 const load=(name:string)=>import(pathToFileURL(join(root,'packages',name)).href);
 const [ai,context,env,repo,runtime,values]=await Promise.all([load('ai/src/index.ts'),load('agent/src/harness/context.ts'),load('agent/src/harness/env/nodejs.ts'),load('agent/src/harness/session/jsonl/repo.ts'),load('agent/src/harness/runtime/harness.ts'),load('agent/src/harness/session/values.ts')]);
 return {...ai,...env,...repo,...runtime,...values,context:context.BACKGROUND_CONTEXT};
}
export function readOriginal(path:string,work:string,metadata:any){
 const raw=readFile(path,work);requireValue(raw.length>0&&raw[raw.length-1]===10,'session_corrupt','torn original JSONL');
 const lines=new TextDecoder('utf-8',{fatal:true}).decode(raw).split('\n');lines.pop();const header=json(lines.shift()!);
 requireValue(header?.kind==='header'&&header.v===4,'session_corrupt','original Pi v4 header required');
 for(const key of ['id','createdAt','cwd','storageVersion'])requireValue(header[key]===metadata[key],'session_corrupt','metadata/header mismatch');
 let seq=0;const ids=new Set<string>(),values:any=Object.create(null),entries:any[]=[];
 for(const line of lines){const transaction=json(line),rows=Array.isArray(transaction)?transaction:[transaction];requireValue(rows.length>0,'session_corrupt','empty transaction');
  for(const row of rows){requireValue(row&&Number.isSafeInteger(row.seq)&&row.seq>seq,'session_corrupt','invalid original sequence');seq=row.seq;
   if(row.kind==='entry'){requireValue(typeof row.id==='string'&&!ids.has(row.id)&&(row.parentId===null||ids.has(row.parentId)),'session_corrupt','invalid original entry linkage');ids.add(row.id);entries.push(row);}
   else if(row.kind==='value'||row.kind==='list'){requireValue(typeof row.namespace==='string'&&typeof row.key==='string','session_corrupt','invalid original value address');
    requireValue(row.op==='delete'||(row.kind==='value'&&row.op==='set'&&'value'in row)||(row.kind==='list'&&row.op==='append'&&'value'in row),'session_corrupt','unknown original mutation');
    if(row.kind==='value'){const bucket=values[row.namespace]??=Object.create(null);if(row.op==='delete')delete bucket[row.key];else bucket[row.key]=row.value;}
   }else requireValue(row.kind==='usage','session_corrupt','unknown original row kind');
  }
 }
 return {raw,header,values,entries};
}
export class OriginalSession {
 session:any;metadata:any;
 constructor(public config:any,public pi:any){}
 async open(create:boolean){
  const work=resolve(this.config.work_root);mkdirSync(work,{recursive:true});const mp=join(work,'metadata.json');
  const repo=new this.pi.JsonlSessionRepo({fileSystem:new this.pi.NodeExecutionEnv({cwd:work}),sessionsRoot:join(work,'sessions')});
  if(existsSync(mp)){
   this.metadata=json(readFile(mp,work,2097152));requireValue(this.metadata.id===this.config.session_scope.session_id&&this.metadata.cwd===work,'session_corrupt','original metadata scope/path differs');
   const before=readOriginal(this.metadata.path,work,this.metadata).raw;
   this.session=await repo.open(this.metadata,this.pi.context);
   requireValue(hash(readOriginal(this.metadata.path,work,this.metadata).raw)===hash(before),'session_corrupt','Pi open altered original');
  }else{
   requireValue(create,'session_corrupt','original metadata missing');
   const dir=join(work,'sessions');requireValue(!existsSync(dir)||readdirSync(dir).length===0,'session_corrupt','original Session exists without metadata');
   this.session=await repo.create({id:this.config.session_scope.session_id,cwd:work},this.pi.context);this.metadata=this.session.metadata;saveMetadata(mp,this.metadata);
  }
  return this;
 }
 async value(namespace:string,key:string){return (await this.session.getValue(this.pi.value(namespace,key),this.pi.context))?.value??null;}
 async set(namespace:string,key:string,value:any){await this.session.setValue(this.pi.value(namespace,key),value,this.pi.context);}
 raw(){return readOriginal(this.metadata.path,this.config.work_root,this.metadata);}
 async inspect(op:string){return {binding:await this.value('lore.s.binding',op),meta:await this.value('pi.op.meta',op),state:await this.value('pi.op.state',op),result:await this.value('pi.result',op),lane:await this.value('pi.lane.state','main'),boundary:await this.value('lore.s.boundary',op)};}
 checkState(observed:any,op:string){
  const {meta,state,result,lane}=observed;
  if(result){requireValue(result.operationId===op&&!meta&&!state,'session_corrupt','contradictory original terminal state');return 'result';}
  if(meta||state){requireValue(meta?.operationId===op&&meta.lane==='main'&&state&&lane?.currentOperationId===op,'session_corrupt','incomplete original operation state');return 'accepted';}
  requireValue(!lane?.currentOperationId||lane.currentOperationId!==op,'session_corrupt','orphan original lane');return 'binding_only';
 }
 locator(op:string,result:any){const {raw}=this.raw();return {owner:'S',session_scope:this.config.session_scope,session_id:this.config.session_scope.session_id,operation_id:op,kind:'pi-operation-result',result_sha256:hash(JSON.stringify(result)),session_relative_path:relative(this.config.work_root,this.metadata.path),session_sha256:hash(raw),session_bytes:raw.length,session_range:[0,raw.length]};}
}
export function bindingFor(config:any,request:any){
 const allowed=['protocol','action','session_ref','operation_id','harness_ref','input_ref','source_result_ref','capability_ref','read_ref'];
 requireValue(request&&Object.keys(request).every(k=>allowed.includes(k))&&request.protocol==='lore.s/1','invalid_request','unexpected request fields/protocol');
 requireValue(['accept','query','drive','export_read'].includes(request.action)&&typeof request.operation_id==='string'&&request.operation_id.length>0&&request.operation_id.length<=256,'invalid_request','invalid action/operation ID');
 requireValue(request.session_ref?.owner==='S'&&request.session_ref.session_id===config.session_scope.session_id,'conflict','Session differs');
 for(const key of ['namespace','surface_id','session_generation'])if(request.session_ref[key]!==undefined)requireValue(request.session_ref[key]===config.session_scope[key],'conflict','Session scope differs');
 for(const [key,value] of [['harness_ref',config.harness_ref],['input_ref',config.input.ref],['capability_ref',config.capability_ref]])requireValue(equal(request[key],value),'conflict','configured '+key+' differs');
 requireValue('source_result_ref'in request,'invalid_request','complete source binding required');
 return {session_id:config.session_scope.session_id,session_scope:config.session_scope,operation_id:request.operation_id,harness_ref:request.harness_ref,input_ref:request.input_ref,source_result_ref:request.source_result_ref,capability_ref:request.capability_ref};
}
