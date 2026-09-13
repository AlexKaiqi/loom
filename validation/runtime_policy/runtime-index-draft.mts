// External policy only: delegate the existing minimal lane, then form an original R body.
import {create as createMinimal} from '../minimal/index.mts';
import {canonical,equal,hash,requireValue} from '../../lore_session/node/common.mts';
const copy=(v:any)=>JSON.parse(canonical(v));
const require=(value:any,message:string)=>requireValue(value,'invalid_input',message);
function contextFor(binding:any,context:any){
 require(context&&context.invocation&&context.input,'fixed Runtime context required');
 const parent=context.invocation,selector=context.input.selector,range=context.input.range;
 require(parent.kind==='invocation'&&parent.id===binding.operation_id&&parent.namespace===binding.session_scope.namespace&&
  typeof parent.principal==='string'&&equal(context.node_binding,binding),'Runtime parent or original compact binding differs');
 require(selector&&equal(selector,parent.payload.input_binding)&&selector.namespace===parent.namespace&&selector.source===parent.principal&&
  equal(parent.payload.source_result_ref,binding.source_result_ref),'original accepted selector/source differs');
 require(range&&range.start_sequence===selector.start_sequence&&Number.isSafeInteger(range.end_sequence)&&
  Number.isSafeInteger(range.high_water)&&range.end_sequence<=range.high_water&&
  range.next_sequence===(range.end_sequence>=range.start_sequence?range.end_sequence+1:range.start_sequence),
  'original fixed input next sequence differs');
 require(typeof context.execution_id==='string'&&context.execution_id.length>0,'original drive execution identity missing');
 const reference={owner:'S',kind:'confirmation',confirmation_request_id:'s-'+hash(canonical([context.execution_id,'s-service-final'])),session_scope:binding.session_scope};
 require(equal(context.continuation_session_ref,reference),'preallocated confirmation locator differs');
 require(parent.payload.harness_ref&&parent.payload.capability_ref,'complete original R references required');
 return {parent,selector,reference};
}
function currentMessages(original:any,operation:any){
 const result=original.values?.['pi.result']?.[operation];require(result?.operationId===operation,'original operation result missing');
 const byId=new Map(original.entries.map((e:any)=>[e.id,e])),entries:any[]=[],seen=new Set();let id=result.tipId;
 while(id&&id!==result.fromTipId){
  require(!seen.has(id),'original result path cycles');seen.add(id);
  const entry:any=byId.get(id);require(entry,'original result path missing');entries.unshift(entry);id=entry.parentId;
 }
 return entries.filter(e=>e.type==='message').map(e=>e.message);
}
function publishedTargets(original:any,binding:any,selector:any,parent:any){
 const messages=currentMessages(original,binding.operation_id),tools=messages.filter(m=>m.role==='toolResult');
 require(tools.length===1&&tools[0].details?.publication_ref,'original tool publication is missing');
 const tool=tools[0],pub=tool.details.publication_ref,registration=pub.registration,intent=pub.R_intent;
 const assistant=messages.findLast(m=>m.role==='assistant');const calls=assistant?.content?.filter((p:any)=>p.type==='toolCall')??[];
 require(calls.length===1&&calls[0].id===tool.toolCallId,'original native tool association differs');
 require(intent&&registration&&pub.F_query&&pub.installation_ref&&pub.release&&
  intent.execution_id===tool.details.result_ref.execution_id&&intent.resource_id===registration.id&&
  registration.namespace===parent.namespace&&['surface','workspace'].includes(registration.kind)&&
  Number.isSafeInteger(intent.expected_revision)&&registration.revision===intent.expected_revision+1,
  'original publication resource/execution/revision differs');
 require(calls[0].arguments.target===(registration.kind==='surface'?'runtime':'workspace'),'native target differs from published domain');
 require(pub.F_query.request_id===intent.request_id&&pub.installation_ref.request_id===intent.request_id&&
  pub.F_query.status==='installed_pending_confirmation'&&['installed_pending_confirmation','confirmed'].includes(pub.installation_ref.status)&&
  equal(pub.F_query.version_ref,pub.installation_ref.version_ref)&&
  pub.release.resource_id===registration.id&&pub.release.execution_id===intent.execution_id&&pub.release.released===true,
  'original publication is not a complete matching confirmation/release');
 const version=pub.F_query.version_ref;require(version.resource_id===registration.id&&version.domain===registration.kind,'published F version domain differs');
 const selected=selector.execution_targets.filter((t:any)=>t.resource_id===registration.id);
 require(selected.length===1&&equal(selected[0].version_ref,intent.base_ref),'publication base is not an accepted execution target');
 const targets=selector.execution_targets.map((t:any)=>t.resource_id===registration.id?{...copy(t),version_ref:copy(version)}:copy(t));
 if(registration.kind==='surface')require(registration.id===parent.payload.resource_id&&parent.payload.resource_revision===intent.expected_revision&&equal(selector.surface_ref,intent.base_ref),'publication is not the original Surface');
 return {targets,registration,version};
}
export function decideControl(boundary:any,original:any,binding:any,source:any,runtime_context:any){
 const output=copy(boundary),proposal=output.decision_proposal;
 if(!proposal)return output; // Incomplete/invalid minimal output remains an unsettled boundary.
 const {parent,selector,reference}=contextFor(binding,runtime_context);
 require(equal(proposal.source_result_ref,source)&&equal(proposal.harness_ref,binding.harness_ref)&&
  equal(proposal.input_ref,binding.input_ref)&&source.operation_id===binding.operation_id&&
  equal(source.session_scope,binding.session_scope),'original policy source/compact association differs');
 let body:any;
 if(boundary.boundary_kind==='answer_saved'&&proposal.final&&!('continue'in proposal)){
  body={stop_ref:{owner:'S',kind:'runtime-policy-stop',confirmation_ref:reference,operation_id:binding.operation_id,source_result_ref:source}};
 }else{
  require(boundary.boundary_kind==='tool_feedback_saved'&&proposal.continue===true&&!('final'in proposal),'minimal policy has no complete handoff');
  const published=publishedTargets(original,binding,selector,parent),payload=copy(parent.payload);
  payload.input_ref=null;payload.source_result_ref=copy(source);payload.session_ref=copy(reference);
  payload.input_binding={...copy(selector),start_sequence:runtime_context.input.range.next_sequence,
   previous_session_ref:copy(reference),execution_targets:published.targets};
  if(published.registration.kind==='surface'){
   payload.resource_revision=published.registration.revision;payload.input_binding.surface_ref=copy(published.version);
  }
  const id='runtime-next-'+hash(canonical([parent.id,source,payload]));
  require(id!==parent.id,'successor must have a new original identity');
  body={successors:[{id,namespace:parent.namespace,kind:'invocation',payload}]};
 }
 proposal.control={parent_id:parent.id,harness_ref:copy(parent.payload.harness_ref),body};
 proposal.decision_id='runtime-'+hash(canonical([binding,source,proposal.control]));
 return output;
}
export async function create(args:any){
 require(args.store.config.runtime_context,'fixed Runtime context required');
 const context=copy(args.store.config.runtime_context);contextFor(args.binding,context);
 const minimal=await createMinimal(args);
 return {...minimal,decide(result:any,original:any,source:any){
  return decideControl(minimal.decide(result,original,source),original,args.binding,source,context);
 }};
}
