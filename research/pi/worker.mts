import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createModels, fauxProvider, fauxAssistantMessage, fauxToolCall, Type } from "@earendil-works/pi-ai";
import { BACKGROUND_CONTEXT as context } from "../repos/pi/packages/agent/src/harness/context.ts";
import { NodeExecutionEnv } from "../repos/pi/packages/agent/src/harness/env/nodejs.ts";
import { JsonlSessionRepo } from "../repos/pi/packages/agent/src/harness/session/jsonl/repo.ts";
import { createAgentHarness } from "../repos/pi/packages/agent/src/harness/runtime/harness.ts";
const [mode,workspace,flavor="normal"]=process.argv.slice(2);
const repository=new JsonlSessionRepo({fileSystem:new NodeExecutionEnv({cwd:workspace}),sessionsRoot:join(workspace,"sessions")});
let session;
if(mode==="create"||mode==="crash"||mode==="policy"){
 session=await repository.create({id:"fixture-session",cwd:workspace},context);
 writeFileSync(join(workspace,"metadata.json"),JSON.stringify(session.metadata));
}else{
 const metadata=JSON.parse(readFileSync(join(workspace,"metadata.json"),"utf8"));
 session=await repository.open(metadata,context);
}
const faux=fauxProvider();
const response=(text)=>()=>{appendFileSync(join(workspace,"queries.jsonl"),JSON.stringify({text})+"\n");return fauxAssistantMessage(text);}
faux.setResponses(mode==="crash"?[
 ()=>{appendFileSync(join(workspace,"queries.jsonl"),JSON.stringify({text:"tool-request"})+"\n");return fauxAssistantMessage(fauxToolCall("effect",{}, {id:"fixed-call"}),{stopReason:"toolUse"});}
]:[response("FIXED_ANSWER_雪"),response("POLICY_SECOND_雪"),response("THIRD_BOUND")]);
const models=createModels();models.setProvider(faux.provider);
const tools=[{name:"effect",label:"effect fixture",description:"append one effect",parameters:Type.Object({}),replay:flavor==="safe"?"safe":"unsafe",
 execute:async()=>{appendFileSync(join(workspace,"effects.txt"),"effect\n");if(mode==="crash")process.kill(process.pid,"SIGKILL");return {content:[{type:"text",text:"EFFECT_RETURNED"}],details:{}};}}];
const created=await createAgentHarness({session,models,model:faux.getModel(),tools},context);
const harness=created.harness;const lane=await harness.lane("main",context);
let policyCalls=0;
if(mode==="policy")harness.hooks.on("before_run_end",()=>++policyCalls===1?{followUp:"EXTERNAL_POLICY_CONTINUE"}:undefined,{id:"external-policy"});
const out={mode,flavor,opened:created.open,metadata:session.metadata,before:await lane.inspectExecution(context)};
if(mode==="create"||mode==="crash"||mode==="policy"){
 out.admission=await lane.accept({kind:"prompt",operationId:"fixture-operation",prompt:"FIXED_PROMPT"},context);
 if(mode!=="create")out.drive=await lane.drive({operationId:"fixture-operation"},context);
}else if(mode==="drive"){
 out.drive=await lane.drive({operationId:"fixture-operation"},context);
}else if(mode==="reaccept"){
 try{out.admission=await lane.accept({kind:"prompt",operationId:"fixture-operation",prompt:flavor==="changed"?"CHANGED_PROMPT":"FIXED_PROMPT"},context);}
 catch(e){out.admissionError={message:e.message,cause:e.cause?.message};}
}
out.result=await lane.getResult("fixture-operation",context)??null;
out.after=await lane.inspectExecution(context);
out.entries=await lane.findEntries(undefined,context);
out.providerCalls=faux.state.callCount;
out.policyCalls=policyCalls;
writeFileSync(join(workspace,"last-observation.json"),JSON.stringify(out));
console.log(JSON.stringify(out));
process.exit(0);
