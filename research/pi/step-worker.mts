import {appendFileSync,readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createModels,fauxProvider,fauxAssistantMessage,fauxToolCall,Type} from '@earendil-works/pi-ai';
import {BACKGROUND_CONTEXT as context} from '../repos/pi/packages/agent/src/harness/context.ts';
import {NodeExecutionEnv} from '../repos/pi/packages/agent/src/harness/env/nodejs.ts';
import {JsonlSessionRepo} from '../repos/pi/packages/agent/src/harness/session/jsonl/repo.ts';
import {createAgentHarness} from '../repos/pi/packages/agent/src/harness/runtime/harness.ts';
const [mode,w]=process.argv.slice(2);const fresh=mode==='step'||mode==='control';
const repo=new JsonlSessionRepo({fileSystem:new NodeExecutionEnv({cwd:w}),sessionsRoot:join(w,'sessions')});
const session=fresh?await repo.create({id:'step-session',cwd:w},context):await repo.open(JSON.parse(readFileSync(join(w,'metadata.json'),'utf8')),context);
if(fresh)writeFileSync(join(w,'metadata.json'),JSON.stringify(session.metadata));
const faux=fauxProvider();const reply=(value)=>(request)=>{appendFileSync(join(w,'queries.jsonl'),JSON.stringify({mode,request})+'\n');return value;};
faux.setResponses(fresh?[reply(fauxAssistantMessage(fauxToolCall('effect',{}, {id:'one-call'}),{stopReason:'toolUse'})),reply(fauxAssistantMessage('CONTROL_FINAL'))]:[reply(fauxAssistantMessage('CONTINUED_FROM_SAVED_STEP'))]);
const models=createModels();models.setProvider(faux.provider);
const tool={name:'effect',label:'finite effect',description:'Append exactly one fixture effect',parameters:Type.Object({}),replay:'unsafe',execute:async()=>{appendFileSync(join(w,'effects.txt'),'effect\n');return {content:[{type:'text',text:'SAVED_EFFECT_RESULT_雪'}],details:{}};}};
const created=await createAgentHarness({session,models,model:faux.getModel(),tools:[tool]},context);const h=created.harness;const lane=await h.lane('main',context);
if(mode!=='control')h.hooks.on('after_tool',()=>({terminate:true}),{id:'external-single-step-policy'});
const out={mode,pid:process.pid,oldResult:await lane.getResult('first',context)??null};
if(mode!=='inspect'){
 const id=mode==='continue'?'second':'first';out.admission=await lane.accept({kind:'prompt',operationId:id,prompt:mode==='continue'?'Continue from the saved tool result':'Run the fixture effect'},context);
 out.driven=await lane.drive({operationId:id},context);out.result=await lane.getResult(id,context);
}
out.firstResult=await lane.getResult('first',context)??null;out.entries=await lane.findEntries(undefined,context);out.providerCalls=faux.state.callCount;console.log(JSON.stringify(out));process.exit(0);
