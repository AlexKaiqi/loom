import { Codex } from "../repos/codex/sdk/typescript/src/codex.ts";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
const mode=process.argv[2], dir=process.argv[3];
const log=resolve(dir, `${mode}-child.jsonl`);
const client=new Codex({codexPathOverride:resolve("research/codex/fixture-cli.py"),env:{PATH:"/usr/bin:/bin",FIXTURE_MODE:mode,FIXTURE_LOG:log}});
const thread=mode==="resume"?client.resumeThread("fixed-thread"):client.startThread();
const ac=new AbortController();
let timer:ReturnType<typeof setInterval>|undefined;
if(mode==="abort")timer=setInterval(()=>{if(existsSync(log)&&readFileSync(log,"utf8").includes('started'))ac.abort();},20);
try {
 const result=await thread.run("fixed-prompt",{signal:ac.signal});
 console.log(JSON.stringify({mode,outcome:"returned",id:thread.id,result}));
} catch(e) {console.log(JSON.stringify({mode,outcome:"rejected",id:thread.id,error:{name:e.name,message:e.message}}));}
finally {if(timer)clearInterval(timer);}
