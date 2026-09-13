import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {canonical,hash} from '../../lore_session/node/common.mts';
const [fixturePath,resultPath,candidate,control]=process.argv.slice(2);
const fixture=JSON.parse(readFileSync(fixturePath,'utf8'));
const module=await import(pathToFileURL(candidate).href);
const clone=(v:any)=>JSON.parse(JSON.stringify(v));
const fullHarness={owner:'F',kind:'file',path:'runtime/index.mts',version_ref:{resource_id:'harness',domain:'surface',git_ref:'fixture-fixed-runtime'},sha256:'a'.repeat(64)};
const version=(id:string,n:number)=>({resource_id:id,domain:id==='surface'?'surface':'workspace',git_ref:'fixture-v'+n,archive_sha256:String(n).repeat(64).slice(0,64),manifest_sha256:String(n+1).repeat(64).slice(0,64),profile:'host-v1'});
function input(target='runtime'){
 const binding=clone(fixture.binding),source=clone(fixture.tool_source),original=clone(fixture.original),boundary=clone(fixture.tool_boundary);
 const selector={namespace:binding.session_scope.namespace,source:'trusted-fixture',start_sequence:1,filters:{names:['notice']},page_size:4,surface_ref:version('surface',1),previous_session_ref:{owner:'S',kind:'prior-fixture'},execution_targets:[{resource_id:'surface',version_ref:version('surface',1),retained:'surface-field'},{resource_id:'workspace',version_ref:version('workspace',2),retained:'workspace-field'}]};
 const payload={resource_id:'surface',resource_revision:1,harness_ref:fullHarness,input_ref:null,input_binding:selector,session_ref:selector.previous_session_ref,source_result_ref:binding.source_result_ref,capability_ref:{owner:'F',kind:'fixture-capability'}};
 const invocation={id:binding.operation_id,namespace:binding.session_scope.namespace,principal:'trusted-fixture',kind:'invocation',payload};
 const execution_id='fixture-s-drive';
 const context={invocation,node_binding:clone(binding),input:{selector:clone(selector),range:{start_sequence:1,end_sequence:4,high_water:20,next_sequence:5}},execution_id,continuation_session_ref:{owner:'S',kind:'confirmation',confirmation_request_id:'s-'+hash(canonical([execution_id,'s-service-final'])),session_scope:clone(binding.session_scope)}};
 const resource=target==='runtime'?'surface':'workspace',n=resource==='surface'?2:3;
 const tool=original.entries.findLast((r:any)=>r.type==='message'&&r.message.role==='toolResult');
 const native=original.entries.findLast((r:any)=>r.type==='message'&&r.message.role==='assistant');native.message.content[0].arguments.target=target;
 const publication={R_intent:{request_id:'fixture-install',resource_id:resource,execution_id:tool.message.details.result_ref.execution_id,expected_revision:n-1,base_ref:version(resource,n-1)},F_query:{request_id:'fixture-install',status:'installed_pending_confirmation',version_ref:version(resource,n)},installation_ref:{request_id:'fixture-install',status:'installed_pending_confirmation',version_ref:version(resource,n)},registration:{id:resource,namespace:invocation.namespace,kind:resource==='surface'?'surface':'workspace',revision:n,path:'/fixture/'+resource},release:{resource_id:resource,execution_id:tool.message.details.result_ref.execution_id,released:true}};
 tool.message.details.publication_ref=publication;
 return {boundary,original,binding,source,context,publication};
}
const factoryInput=input();const factoryRoot=join(dirname(resultPath),'minimal-factory');mkdirSync(factoryRoot);
const surface=join(factoryRoot,'surface');mkdirSync(surface);writeFileSync(join(surface,'template.md'),'{{goal.md}}');writeFileSync(join(surface,'goal.md'),'Original minimal factory fixture.');
writeFileSync(join(factoryRoot,'events.jsonl'),'');writeFileSync(join(factoryRoot,'feedback.txt'),'');
const lane={fixture:'NO_PI_ENGINE'},registered:any[]=[],pi={context:{},async createAgentHarness(options:any){registered.push(options);return {harness:{async lane(){return lane;},events:{on(...args:any[]){registered.push(args[0]);}},hooks:{on(...args:any[]){registered.push(args[0]);}}}};}};
const store={config:{runtime_context:factoryInput.context,model:{provider:'fixture',id:'fixture'},input:{paths:{surface,events:join(factoryRoot,'events.jsonl'),feedback:join(factoryRoot,'feedback.txt'),runtime:'/runtime',workspace:'/workspace'}}},raw(){return factoryInput.original;},session:{fixture:'NO_PI_ENGINE'}};
const wrapped=await module.create({pi,store,binding:factoryInput.binding,models:{},tool:()=>{throw Error('no tool dispatch in policy probe');}});
let fn=module.decideControl;
if(typeof fn!=='function')throw Error('actual external decideControl export is missing');
if(control==='always-green'){const a=input();const fixed=fn(a.boundary,a.original,a.binding,a.source,a.context);fn=()=>clone(fixed);}
const checks:any[]=[];const outputs:any={};
function call(a:any){return fn(a.boundary,a.original,a.binding,a.source,a.context);}
function check(id:string,run:()=>any){try{run();checks.push({id,passed:true});}catch(e:any){checks.push({id,passed:false,error:String(e.stack??e)});}}
function rejected(a:any){let error:any;try{call(a);}catch(e){error=e;}assert.equal(error?.code,'invalid_input','only declared context rejection counts');}
check('HP01-surface-publication',()=>{
 const a=input(),r=call(a);outputs.HP01=r;
 assert.equal(r.boundary_kind,'tool_feedback_saved');assert.equal(r.decision_proposal.continue,true);
 assert.deepEqual(r.decision_proposal.harness_ref,a.binding.harness_ref);assert.deepEqual(r.decision_proposal.input_ref,a.binding.input_ref);
 const c=r.decision_proposal.control;assert.equal(c.parent_id,a.context.invocation.id);assert.deepEqual(c.harness_ref,fullHarness);
 assert.deepEqual(Object.keys(c.body),['successors']);assert.equal(c.body.successors.length,1);
 const n=c.body.successors[0];assert.notEqual(n.id,a.context.invocation.id);assert.equal(n.namespace,a.context.invocation.namespace);assert.equal(n.kind,'invocation');
 const p=n.payload;assert.equal(p.resource_revision,2);assert.equal(p.input_ref,null);assert.deepEqual(p.harness_ref,fullHarness);assert.deepEqual(p.source_result_ref,a.source);
 assert.deepEqual(p.session_ref,a.context.continuation_session_ref);assert.deepEqual(p.input_binding.previous_session_ref,p.session_ref);
 assert.equal(p.input_binding.start_sequence,5);assert.notEqual(p.input_binding.start_sequence,21);
 assert.deepEqual(p.input_binding.surface_ref,version('surface',2));assert.deepEqual(p.input_binding.execution_targets[1],a.context.input.selector.execution_targets[1]);
 assert.deepEqual(p.input_binding.execution_targets[0],{...a.context.input.selector.execution_targets[0],version_ref:version('surface',2)});
 for(const k of ['namespace','source','filters','page_size'])assert.deepEqual(p.input_binding[k],a.context.input.selector[k]);assert.ok(!('principal'in p));
});
check('HP02-workspace-publication',()=>{
 const a=input('workspace'),r=call(a);outputs.HP02=r;const p=r.decision_proposal.control.body.successors[0].payload;
 assert.equal(p.resource_revision,1);assert.deepEqual(p.input_binding.surface_ref,version('surface',1));assert.deepEqual(p.input_binding.execution_targets[0],a.context.input.selector.execution_targets[0]);
 assert.deepEqual(p.input_binding.execution_targets[1],{...a.context.input.selector.execution_targets[1],version_ref:version('workspace',3)});
});
check('HP03-original-answer',()=>{
 const a=input();a.boundary=clone(fixture.answer_boundary);a.source=clone(fixture.answer_source);
 // This pure control uses the original answer association; it makes no new owner assertion.
 a.binding=clone(fixture.answer_binding);a.context.node_binding=clone(a.binding);a.context.invocation.id=a.binding.operation_id;
 a.context.invocation.namespace=a.binding.session_scope.namespace;a.context.input.selector.namespace=a.binding.session_scope.namespace;
 a.context.invocation.payload.input_binding=clone(a.context.input.selector);a.context.continuation_session_ref.session_scope=clone(a.binding.session_scope);
 const r=call(a);outputs.HP03=r;assert.equal(r.boundary_kind,'answer_saved');assert.deepEqual(r.decision_proposal.final,a.boundary.decision_proposal.final);
 assert.deepEqual(r.decision_proposal.control.body,{stop_ref:{owner:'S',kind:'runtime-policy-stop',confirmation_ref:a.context.continuation_session_ref,operation_id:a.binding.operation_id,source_result_ref:a.source}});
});
check('HP04-no-policy-remains-unsettled',()=>{
 const a=input();a.boundary={boundary_kind:'blocked_invalid'};assert.deepEqual(call(a),a.boundary);
});
check('HP05-related-invalid-contexts',()=>{
 const mutations=[(a:any)=>a.context.invocation.id='wrong-parent',(a:any)=>a.context.continuation_session_ref.session_scope.session_generation++,
 (a:any)=>a.context.continuation_session_ref.confirmation_request_id='s-wrong',(a:any)=>a.context.node_binding.harness_ref.sha256='f'.repeat(64),
 (a:any)=>a.context.input.range.next_sequence=21,(a:any)=>a.publication.registration.namespace='wrong-namespace',
 (a:any)=>a.publication.R_intent.execution_id='wrong-execution',(a:any)=>a.publication.release.released=false,
 (a:any)=>{delete a.original.entries.findLast((r:any)=>r.type==='message'&&r.message.role==='toolResult').message.details.publication_ref;}];
 for(const mutate of mutations){const a=input();mutate(a);rejected(a);}
});
check('HP06-stable-complete-decision-no-mutation',()=>{
 const a=input(),before=canonical(a),r=call(a),r2=call(a);assert.equal(canonical(a),before);assert.deepEqual(r,r2);
 assert.equal(wrapped.lane,lane);assert.equal(registered.length,4);assert.deepEqual(registered.slice(1),['entry_added','before_tool','after_tool']);
 assert.deepEqual(wrapped.decide(factoryInput.original.values['pi.result'][factoryInput.binding.operation_id],factoryInput.original,factoryInput.source),r);
 const b=input('workspace'),other=call(b);assert.notEqual(r.decision_proposal.decision_id,other.decision_proposal.decision_id);assert.notEqual(r.decision_proposal.control.body.successors[0].id,other.decision_proposal.control.body.successors[0].id);
});
writeFileSync(resultPath,JSON.stringify({status:checks.every(x=>x.passed)?'PASS':'FAIL',tests_run:checks.length,scope:'PURE_POLICY_NO_ENGINE_NO_PROVIDER_NO_OWNER_GRANT',checks,outputs},null,2)+'\n');
process.exitCode=checks.every(x=>x.passed)?0:1;
