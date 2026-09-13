import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { SessionManager } from "../repos/sol-pi/node_modules/@earendil-works/pi-coding-agent/dist/core/session-manager.js";
import { createObservationPackExtension } from "../repos/sol-pi/src/sol-pi/extensions/observation-pack/index.ts";
import { FakePi, fakeContext } from "../repos/sol-pi/tests/helpers.ts";

const [mode, workspace] = process.argv.slice(2);
const sha = x => createHash("sha256").update(x).digest("hex");
const text = Array.from({length:1200}, (_,i)=> i===600 ? "MIDDLE_ORACLE_雪\n" : "row-"+String(i).padStart(4,"0")+" 雪 evidence fixture\n").join("");
let session;
if(mode==="create"){
 mkdirSync(join(workspace,"sessions"),{recursive:true});
 session=SessionManager.create(workspace,join(workspace,"sessions"),{id:"sol-mechanism"});
 session.appendMessage({role:"user",content:"fixture",timestamp:1});
 session.appendMessage({role:"assistant",content:[{type:"text",text:"fixed"}],api:"faux",provider:"faux",model:"faux",stopReason:"stop",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},timestamp:2});
 session.appendMessage({role:"toolResult",toolName:"bash",toolCallId:"fixture-call",content:[{type:"text",text}],isError:false,timestamp:3});
 writeFileSync(join(workspace,"session-path.txt"),session.getSessionFile());
}else{session=SessionManager.open(readFileSync(join(workspace,"session-path.txt"),"utf8"));}
const pi=new FakePi(session);
createObservationPackExtension()(pi.asExtensionApi());
const context=fakeContext(session);
const messages=session.getEntries().filter(e=>e.type==="message").map(e=>e.message);
const id="obs_"+sha("bash\0fixture-call\0"+sha(text)).slice(0,24);
const out={mode,sessionId:session.getSessionId(),sessionFile:session.getSessionFile(),id};
if(mode==="create"||mode==="project"){
 out.projections=[];
 for(let i=0;i<3;i++)out.projections.push(await pi.emitContext(messages,context));
 out.entries=session.getEntries();
}else{
 try{
  const pages=[];let offset=0;
  for(let i=0;i<32;i++){
   const result=await pi.tool("obs_recall").execute("recall", {id:mode==="missing"?"obs_000000000000000000000000":id,offset},undefined,undefined,context);
   pages.push(result);
   if(result.details.eof)break;
   if(result.details.nextOffset<=offset)throw new Error("fixture detected non-advancing offset");
   offset=result.details.nextOffset;
  }
  out.pages=pages;
 }catch(error){out.error={message:error.message,code:error.code};}
}
console.log(JSON.stringify(out));
