import {readFileSync, writeFileSync, readdirSync, copyFileSync} from 'node:fs';
import {join} from 'node:path';
import {createInterface} from 'node:readline';
import {createModels, createProvider, createAssistantMessageEventStream} from '@earendil-works/pi-ai';
import {BACKGROUND_CONTEXT as context} from '../../../research/repos/pi/packages/agent/src/harness/context.ts';
import {NodeExecutionEnv} from '../../../research/repos/pi/packages/agent/src/harness/env/nodejs.ts';
import {JsonlSessionRepo} from '../../../research/repos/pi/packages/agent/src/harness/session/jsonl/repo.ts';
import {createAgentHarness} from '../../../research/repos/pi/packages/agent/src/harness/runtime/harness.ts';
import {value} from '../../../research/repos/pi/packages/agent/src/harness/session/values.ts';
const [mode, work] = process.argv.slice(2);
const input = JSON.parse(readFileSync(join(work, 'binding.json'), 'utf8'));
const lines = createInterface({input:process.stdin});
const replies = new Map<string, (x:any)=>void>();
lines.on('line', line => {const x=JSON.parse(line); const resolve=replies.get(x.reply_to); if(!resolve) throw Error('unmatched reply'); replies.delete(x.reply_to); resolve(x);});
const send = (x:any) => process.stdout.write(JSON.stringify(x)+'\n');
let call=0, providerCalls=0, toolCalls=0;
const ask = (x:any) => new Promise<any>(resolve => {const call_id='channel-call-'+(++call);replies.set(call_id,resolve);send({...x,call_id});});
const files = (root:string):string[] => readdirSync(root,{withFileTypes:true}).flatMap(d=>d.isDirectory()?files(join(root,d.name)):d.name.endsWith('.jsonl')?[join(root,d.name)]:[]);
const original = () => {const f=files(join(work,'sessions'));if(f.length!==1)throw Error('one original Session');return f[0];};
const snapshot = (label:string) => {const p=original();copyFileSync(p,join(work,label+'.jsonl'));return p;};
const repo=new JsonlSessionRepo({fileSystem:new NodeExecutionEnv({cwd:work}),sessionsRoot:join(work,'sessions')});
const session=mode==='query'?await repo.open(JSON.parse(readFileSync(join(work,'metadata.json'),'utf8')),context):await repo.create({id:input.session_id,cwd:work},context);
if(mode!=='query'){writeFileSync(join(work,'metadata.json'),JSON.stringify(session.metadata));await session.setValue(value('lore.wire.binding',input.operation_id),input,context);}
const model:any={id:'gpt-5.6-terra',name:'fixed wire fixture',api:'lore-proxy-completions',provider:'lore-authorized-proxy',baseUrl:'http://localhost:0',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:16384,maxTokens:2048};
const stream=(_model:any, request:any) => {
 const output=createAssistantMessageEventStream();
 queueMicrotask(async()=>{
  try {
   providerCalls++;
   const state=(await session.getValue(value('pi.op.state',input.operation_id),context))?.value as any;
   const raw=snapshot('provider-'+providerCalls+'-pending');
   const reply=await ask({type:'provider.request',context:request,response_entry_id:state?.responseEntryId,original:raw});
   if(reply.halt){send({type:'halted',reason:reply.halt,providerCalls,toolCalls});process.exit(17);}
   // Deliver the complete native message exactly; fauxProvider would replace actual usage.
   const message=reply.message;
   if(!message||message.role!=='assistant')throw Error('complete native reply required');
   output.push({type:'start',partial:{...message,content:[],stopReason:'pending'}});
   output.push({type:'done',reason:message.stopReason,message});output.end(message);
  } catch(e){send({type:'probe.error',error:String(e)});process.exit(19);}
 });
 return output;
};
const models=createModels();models.setProvider(createProvider({id:model.provider,models:[model],auth:{apiKey:{name:'keyless fixture',resolve:async()=>({auth:{}})}},api:{stream,streamSimple:stream}}));
const shell={name:'shell',label:'finite mechanism fixture',description:'Run ordinary Shell in an authorized target',parameters:{type:'object',properties:{target:{type:'string',enum:['runtime','workspace']},script:{type:'string'}},required:['target','script'],additionalProperties:false},replay:'unsafe' as const,execute:async(id:any,args:any,_update:any,_toolContext:any,invocation:any)=>{
 toolCalls++;const raw=snapshot('tool-'+toolCalls+'-pending');const reply=await ask({type:'tool.request',invocation_id:invocation.invocationId,tool_call_id:id,args,original:raw});return {content:[{type:'text' as const,text:reply.stdout}],details:{fixture:true}};
}};
const h=(await createAgentHarness({session,models,model,tools:[shell],systemPrompt:'Finite source-bound wire/Pi mechanism probe',compaction:{enabled:false,reserveTokens:1024,keepRecentTokens:1024},retry:{enabled:false,maxRetries:0,baseDelayMs:0,maxAgentDelayMs:0},toolExecution:'sequential'},context)).harness;
const lane=await h.lane('main',context);
h.hooks.on('before_tool',async()=>{const entries=await lane.findEntries({order:'desc'},context);const a=entries.find((e:any)=>e.type==='message'&&e.message.role==='assistant') as any;if(!a||a.message.stopReason!=='toolUse'||a.message.content.filter((b:any)=>b.type==='toolCall').length!==1)return {block:{reason:'finite whole-batch guard',terminate:true}};},{id:'wire-probe-single-tool'});
send({type:'started',pid:process.pid,execPath:process.execPath,argv:process.argv,mode});
if(mode!=='query'){await lane.accept({kind:'prompt',operationId:input.operation_id,prompt:'A fixed fixture prompt'},context);snapshot('accepted');await lane.drive({operationId:input.operation_id},context);}
const result=await lane.getResult(input.operation_id,context)??null;snapshot(mode+'-final');
send({type:'result',pid:process.pid,result,providerCalls,toolCalls,original:original()});process.exit(0);
