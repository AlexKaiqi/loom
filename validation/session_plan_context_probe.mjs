import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {create,decideControl} from '../harnesses/runtime/index.mts';
const [input,output]=process.argv.slice(2);const {config:original,request}=JSON.parse(readFileSync(input));
const context=original.runtime_context,binding=context.node_binding;
const source={owner:'S',operation_id:binding.operation_id,session_scope:binding.session_scope,result_sha256:'a'.repeat(64)};
const boundary={boundary_kind:'answer_saved',decision_proposal:{final:{content:[{type:'text',text:'finite context check'}]},source_result_ref:source,harness_ref:binding.harness_ref,input_ref:binding.input_ref}};
const result=decideControl(boundary,{entries:[],values:{}},binding,source,context);
assert.deepEqual(result.decision_proposal.control.body.stop_ref.confirmation_ref,context.continuation_session_ref);
// No Pi/Engine: exercise actual Runtime.create and minimal.create with inert public backend.
// Only container file paths are mapped to their exact original F materializations for host reading.
const config=structuredClone(original),mounts=Object.fromEntries(request.readonly_mounts.map(m=>[m.target,m.source.path]));
for(const [k,p] of Object.entries(config.input.paths)){
 const prefix=Object.keys(mounts).sort((a,b)=>b.length-a.length).find(base=>p===base||p.startsWith(base+'/'));
 if(prefix)config.input.paths[k]=mounts[prefix]+p.slice(prefix.length);
}
for(const row of Object.values(config.input.original_refs??{}))row.path=mounts['/input']+row.path.slice('/input'.length);
const registrations=[],lane={};
const pi={context:{},createAgentHarness:async()=>({harness:{lane:async()=>lane,events:{on:n=>registrations.push(n)},hooks:{on:n=>registrations.push(n)}}})};
const made=await create({pi,store:{config,session:{},raw:()=>({values:{}})},binding,models:{},tool:()=>{throw Error('no dispatch permitted');}});
assert.equal(made.lane,lane);assert.deepEqual(registrations,['entry_added','before_tool','after_tool']);
writeFileSync(output,JSON.stringify({status:'PASS',scope:'ACTUAL_RUNTIME_CREATE_AND_DECIDE_WITH_NO_PI_BACKEND',result,registrations}));
