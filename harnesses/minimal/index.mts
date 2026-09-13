// External M policy. Runtime/Node bridge do not select files, tools or decisions.
import {project} from './projection.mts';
import {hash,requireValue,canonical} from '../../lore_session/node/common.mts';
const calls=(message:any)=>message.content.filter((part:any)=>part.type==='toolCall');
function validCall(call:any){return call.name==='shell'&&call.arguments&&Object.keys(call.arguments).length===2&&
 ['runtime','workspace'].includes(call.arguments.target)&&typeof call.arguments.script==='string'&&call.arguments.script.trim().length>0;}
export async function create({pi,store,binding,models,tool}:any){
 const configuration=store.config;const maxSteps=configuration.input.limits?.max_steps;
 if(maxSteps!==undefined){const actual=Object.values(store.raw().values['pi.result']??{}).length;requireValue(Number.isSafeInteger(maxSteps)&&maxSteps>=0&&actual<maxSteps,'stopped_limit','fixed Harness step limit reached');}
 const shell={name:'shell',label:'Ordinary authorized Shell',description:'Run ordinary Shell in an authorized target',
  parameters:{type:'object',properties:{target:{type:'string',enum:['runtime','workspace']},script:{type:'string'}},required:['target','script'],additionalProperties:false},
  replay:'unsafe' as const,execute:tool};
 const harness=(await pi.createAgentHarness({session:store.session,models,model:configuration.model,tools:[shell],
  systemPrompt:project(configuration.input),compaction:{enabled:false,reserveTokens:1024,keepRecentTokens:1024},
  retry:{enabled:false,maxRetries:0,baseDelayMs:0,maxAgentDelayMs:0},toolExecution:'sequential',steeringMode:'all',followUpMode:'all'},pi.context)).harness;
 const lane=await harness.lane('main',pi.context);let stopped:Promise<any>|undefined;
 harness.events.on('entry_added',(event:any)=>{
  const message=event.entry?.type==='message'?event.entry.message:null;
  if(event.lane!=='main'||message?.role!=='assistant')return;
  const native=calls(message);
  if(message.stopReason==='length'||native.length>1||(native.length===1&&!validCall(native[0]))){
   // Public post-commit stop: do not await inside the entry event dispatch.
   stopped=lane.requestAbort(binding.operation_id,pi.context);void stopped.catch(()=>{});
  }
 });
 harness.hooks.on('before_tool',async()=>{
  const a=(await lane.findEntries({order:'desc'},pi.context)).find((e:any)=>e.type==='message'&&e.message.role==='assistant') as any;
  if(!a||a.message.stopReason!=='toolUse'||calls(a.message).length!==1||!validCall(calls(a.message)[0]))return {block:{reason:'Incomplete or invalid single native call',terminate:true}};
 });
 harness.hooks.on('after_tool',(event:any)=>({terminate:true,isError:event.isError===true||
  (Number.isInteger(event.details?.exit_code)&&event.details.exit_code!==0)}));
 const currentHistory=configuration.input.history_views?.[0]?.read_path;
 const prompt='New Step: input includes published changes. '+
  (currentHistory?'Workspace snapshot (runtime, read-only): '+currentHistory+'. Use it, not old paths. ':'')+
  'Continue; at most one tool. Final ends task: only when complete or truly blocked.';
 return {harness,lane,prompt,
  async afterDrive(){if(stopped){const result=await stopped;requireValue(result.ok,'paused_unknown','public committed-response stop failed');}},
  decide(result:any,original:any,source:any){
   const byId=new Map(original.entries.map((e:any)=>[e.id,e]));const entries:any[]=[];let id=result.tipId;
   while(id&&id!==result.fromTipId){const e:any=byId.get(id);requireValue(e,'session_corrupt','original result path missing');entries.unshift(e);id=e.parentId;}
   const messages=entries.filter(e=>e.type==='message').map(e=>e.message);const a=messages.findLast((m:any)=>m.role==='assistant');
   const toolResults=messages.filter(m=>m.role==='toolResult');let boundary_kind='blocked_invalid',proposal:any=undefined;
   if(a?.stopReason==='stop'&&calls(a).length===0&&a.content.length&&a.content.every((p:any)=>p.type==='text'&&typeof p.text==='string')&&a.content.some((p:any)=>p.text.trim())){
    boundary_kind='answer_saved';proposal={final:{content:a.content}};
   }else if(a?.stopReason==='toolUse'&&calls(a).length===1&&validCall(calls(a)[0])&&toolResults.length===1&&toolResults[0].details?.result_ref){
    boundary_kind='tool_feedback_saved';proposal={continue:true};
   }
   if(proposal)proposal={decision_id:'m-'+hash(canonical([binding,source.result_sha256,proposal])),source_result_ref:source,harness_ref:binding.harness_ref,input_ref:binding.input_ref,...proposal};
   return {boundary_kind,...(proposal?{decision_proposal:proposal}:{})};
  }};
}
