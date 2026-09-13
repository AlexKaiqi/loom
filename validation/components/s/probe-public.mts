import {appendFileSync,readFileSync,writeFileSync,readdirSync,copyFileSync} from 'node:fs';
import {join} from 'node:path';
import {createModels,fauxProvider,fauxAssistantMessage,fauxToolCall,Type} from '@earendil-works/pi-ai';
import {BACKGROUND_CONTEXT as context} from '../../../research/repos/pi/packages/agent/src/harness/context.ts';
import {NodeExecutionEnv} from '../../../research/repos/pi/packages/agent/src/harness/env/nodejs.ts';
import {JsonlSessionRepo} from '../../../research/repos/pi/packages/agent/src/harness/session/jsonl/repo.ts';
import {createAgentHarness} from '../../../research/repos/pi/packages/agent/src/harness/runtime/harness.ts';
import {value} from '../../../research/repos/pi/packages/agent/src/harness/session/values.ts';
const [mode,w]=process.argv.slice(2), fresh=['single','multi','pending','control'].includes(mode);
const rawFiles=(p:string):string[]=>readdirSync(p,{withFileTypes:true}).flatMap(d=>d.isDirectory()?rawFiles(join(p,d.name)):d.name.endsWith('.jsonl')?[join(p,d.name)]:[]);
const snapshot=(label:string)=>{const files=rawFiles(join(w,'sessions'));if(files.length!==1)throw Error('expected one original Session');copyFileSync(files[0],join(w,label+'.jsonl'));};
const repo=new JsonlSessionRepo({fileSystem:new NodeExecutionEnv({cwd:w}),sessionsRoot:join(w,'sessions')});
const session=fresh?await repo.create({id:'prep-session',cwd:w},context):await repo.open(JSON.parse(readFileSync(join(w,'metadata.json'),'utf8')),context);
if(fresh)writeFileSync(join(w,'metadata.json'),JSON.stringify(session.metadata));
const bindingAddress=value('lore.prep.binding','op-1');
if(fresh)await session.setValue(bindingAddress,{harness:'h1',input:'in1',source:null},context);
const faux=fauxProvider(), models=createModels();models.setProvider(faux.provider);
const observe=(reply:any)=>(request:any)=>{
 appendFileSync(join(w,'provider.jsonl'),JSON.stringify({type:'provider_request',mode,request})+'\n');
 snapshot('provider-intent-'+faux.state.callCount);
 if(mode==='pending')process.exit(17);
 return reply;
};
const count=mode==='multi'||mode==='control'?2:1;
const calls=Array.from({length:count},(_,i)=>fauxToolCall('effect',{ordinal:i},{id:'call-'+i}));
faux.setResponses([observe(fauxAssistantMessage(calls,{stopReason:'toolUse'})),observe(fauxAssistantMessage('SECOND_PROVIDER_CONTROL'))]);
const tool={name:'effect',label:'finite probe',description:'Append a fixture marker',parameters:Type.Object({ordinal:Type.Number()}),replay:'unsafe' as const,execute:async(_id:any,args:any)=>{
 snapshot('tool-intent-'+args.ordinal);appendFileSync(join(w,'effects.jsonl'),JSON.stringify({type:'effect',ordinal:args.ordinal})+'\n');
 return{content:[{type:'text' as const,text:'ORIGINAL_TOOL_RESULT_雪'}],details:{}};
}};
const created=await createAgentHarness({session,models,model:faux.getModel(),tools:[tool],compaction:{enabled:false,reserveTokens:1024,keepRecentTokens:1024},retry:{enabled:false,maxRetries:0,baseDelayMs:0,maxAgentDelayMs:0},toolExecution:'sequential'},context);
const h=created.harness,lane=await h.lane('main',context);
if(mode!=='control'){
 h.hooks.on('before_tool',async()=>{
  const entries=await lane.findEntries({order:'desc'},context);
  const assistant=entries.find((e:any)=>e.type==='message'&&e.message.role==='assistant') as any;
  if(!assistant||assistant.message.content.filter((x:any)=>x.type==='toolCall').length!==1)return{block:{reason:'finite single-tool boundary rejects batch',terminate:true}};
  return undefined;
 },{id:'finite-batch-guard'});
 h.hooks.on('after_tool',()=>({terminate:true}),{id:'finite-step'});
}
const out:any={mode,pid:process.pid,binding:(await session.getValue(bindingAddress,context))?.value,old:await lane.getResult('op-1',context)??null};
if(fresh){out.accepted=await lane.accept({kind:'prompt',operationId:'op-1',prompt:'Finite source probe'},context);snapshot('accepted');}
if(mode!=='query')out.driven=await lane.drive({operationId:'op-1'},context);
out.result=await lane.getResult('op-1',context)??null;out.providerCalls=faux.state.callCount;
snapshot(mode+'-final');console.log(JSON.stringify(out));process.exit(0);
