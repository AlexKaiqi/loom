import {requireValue,hash,json,canonical} from './common.mts';
export const effectId=(binding:any,kind:string,id:string)=>'s-'+kind+'-'+hash(canonical([binding.session_scope,binding.operation_id,id]));
export function callbacks(pi:any,store:any,binding:any,transport:any,pause:(v:any)=>void){
 const identity={session_id:binding.session_id,operation_id:binding.operation_id};
 const stop=(kind:string,error:any)=>{pause({boundary_kind:kind,error:{code:'transport_unavailable',message:String(error)}});return new Promise<any>(()=>{});};
 const stream=(_model:any,payload:any)=>{
  const output=pi.createAssistantMessageEventStream();queueMicrotask(async()=>{
   try{
    const state=await store.value('pi.op.state',binding.operation_id);
    requireValue(state?.at==='assistant.effect_pending'&&typeof state.responseEntryId==='string','paused_unknown','no original provider pending');
    const id=effectId(binding,'provider',state.responseEntryId);
    const reply=await transport.ask({type:'provider.request',...identity,effect_id:id,response_entry_id:state.responseEntryId,payload},'provider.reply');
    if(reply.error)return await stop('paused_unknown',reply.error.code);
    const message=reply.message;
    requireValue(message?.role==='assistant'&&Array.isArray(message.content)&&message.usage&&typeof message.stopReason==='string','invalid_response','complete native Message required');
    output.push({type:'start',partial:{...message,content:[],stopReason:'pending'}});
    output.push({type:'done',reason:message.stopReason,message});output.end(message);
   }catch(error){await stop('paused_unknown',error);}
  });return output;
 };
 const tool=async(_callId:string,args:any,_update:any,_context:any,invocation:any)=>{
  try{
   const id=invocation.invocationId;
   const state=await store.value('pi.op.state',binding.operation_id);
   requireValue(state?.at==='tools'&&state.batch.calls.some((c:any)=>c.resultEntryId===id&&c.status==='effect_pending'),'paused_unknown','no original tool pending');
   const reply=await transport.ask({type:'tool.request',...identity,effect_id:effectId(binding,'tool',id),invocation_id:id,source_result_ref:binding.source_result_ref,request:args},'tool.reply');
   if(reply.error)return await stop('paused_unknown',reply.error.code);
   const raw=Buffer.from(reply.stdout?.data_b64??'','base64');
   requireValue(reply.result_ref&&raw.length===reply.stdout.bytes&&hash(raw)===reply.stdout.sha256,'integrity_mismatch','original tool stdout binding differs');
   const text=new TextDecoder('utf-8',{fatal:true}).decode(raw);
    const result:any={content:[{type:'text',text}],details:{result_ref:reply.result_ref,stdout:{bytes:raw.length,sha256:hash(raw)},...('publication_ref' in reply?{publication_ref:json(canonical(reply.publication_ref))}:{})}};
    if('exit_code' in reply||'stderr' in reply){
     requireValue(Number.isInteger(reply.exit_code)&&reply.exit_code>=0&&reply.exit_code<=255&&reply.stderr,'integrity_mismatch','original tool exit status and stderr required together');
     const stderr=Buffer.from(reply.stderr.data_b64,'base64');
     requireValue(stderr.length===reply.stderr.bytes&&hash(stderr)===reply.stderr.sha256,'integrity_mismatch','original tool stderr binding differs');
     const errorText=new TextDecoder('utf-8',{fatal:true}).decode(stderr);
     if(stderr.length)result.content.push({type:'text',text:'stderr:\n'+errorText});
     result.content.push({type:'text',text:'Command exited with code '+reply.exit_code});
     Object.assign(result.details,{exit_code:reply.exit_code,stderr:{bytes:stderr.length,sha256:hash(stderr)}});
    }
    return result;
  }catch(error){return await stop('paused_unknown',error);}
 };
 const models=pi.createModels();const model=store.config.model;
 models.setProvider(pi.createProvider({id:model.provider,models:[model],auth:{apiKey:{name:'trusted stdio bridge',resolve:async()=>({auth:{}})}},api:{stream,streamSimple:stream}}));
 return {models,tool};
}
export async function queryPending(observed:any,binding:any,transport:any){
 const state=observed.state;let kind:string,id:string;
 if(state?.at==='assistant.effect_pending'){kind='provider';id=state.responseEntryId;}
 else if(state?.at==='tools'){
  const unresolved=state.batch.calls.filter((c:any)=>c.status==='effect_pending');
  if(!unresolved.length)return null;
  if(unresolved.length!==1)return {boundary_kind:'paused_unknown',error:{code:'multiple_pending'}};
  kind='tool';id=unresolved[0].resultEntryId;
 }else return null;
 try{
  const reply=await transport.ask({type:kind==='provider'?'provider.query':'effect.query',session_id:binding.session_id,operation_id:binding.operation_id,effect_id:effectId(binding,kind,id)},'effect.query_reply');
  const known=!reply.error&&reply.result&&reply.result.status!=='UNKNOWN';
  return {boundary_kind:known?'paused_reconciliation_required':'paused_unknown',error:{code:'original_pending',message:'Original pending is retained; no replay or successful Pi injection.'}};
 }catch{return {boundary_kind:'paused_unknown',error:{code:'transport_unavailable'}};}
}
