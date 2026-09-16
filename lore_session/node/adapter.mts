import {pathToFileURL} from 'node:url';
import {dirname} from 'node:path';
import {loadPi,OriginalSession,bindingFor} from './session.mts';
import {callbacks,queryPending} from './callbacks.mts';
import {BoundaryError,requireValue,equal,hash,readFile} from './common.mts';
export async function run(config:any,request:any,transport:any){
 const binding=bindingFor(config,request),op=binding.operation_id;
 const pi=await loadPi(config.pi_root);const store=await new OriginalSession(config,pi).open(request.action==='accept');
 let observed=await store.inspect(op);
 if(observed.binding!==null)requireValue(equal(observed.binding,binding),'conflict','original complete binding differs');
 else requireValue(request.action==='accept','conflict','original binding missing');
 const stateKind=store.checkState(observed,op);
 const output=(extra:any)=>({type:'result',operation_id:op,...extra,
  ...(observed.result?{operation_result_ref:observed.boundary?.operation_result_ref??store.locator(op,observed.result)}:{})});
 if(request.action==='export_read'){
  requireValue(observed.binding!==null,'conflict','read requires original accepted binding');
  const descriptor=(Object.values(config.input.original_refs??{}) as any[]).find(d=>equal(d.source_ref,request.read_ref));
  requireValue(descriptor,'integrity_mismatch','unregistered original read reference');
  const raw=readFile(descriptor.path,dirname(descriptor.path));requireValue(hash(raw)===descriptor.sha256&&raw.length===descriptor.bytes,'integrity_mismatch','original read bytes differ');
  return output({boundary_kind:'accepted',read_result_ref:{path:descriptor.path,sha256:hash(raw),bytes:raw.length}});
 }
 const pending=await queryPending(observed,binding,transport);
 if(pending)return output(pending);
 if(request.action==='query')return output(observed.boundary??{boundary_kind:observed.result?'paused_reconciliation_required':'accepted',...(observed.result?{error:{code:'proposal_not_saved'}}:{})});
 if(request.action==='accept'&&observed.binding!==null&&(stateKind==='accepted'||stateKind==='result'))return output(observed.boundary??{boundary_kind:'accepted'});
 if(request.action==='drive'&&stateKind==='result'&&observed.boundary)return output(observed.boundary);
 requireValue(!observed.lane?.inbox?.length,'paused_unknown','queued work is outside this explicit action');
 let pauseResolve:(v:any)=>void;const paused=new Promise<any>(resolve=>{pauseResolve=resolve;});
 const delegates=callbacks(pi,store,binding,transport,value=>pauseResolve(value));
 const policyModule=await import(pathToFileURL(config.harness_entry).href);
 if(request.action==='accept'){
  requireValue(!observed.lane?.currentOperationId,'lane_busy','another original operation is active');
  // Registration precedes any policy decision (m01-real-2026-09-14v/w revision):
  // a policy-level step-budget stop below must leave the binding as a recorded
  // fact so the confirm descriptor and facts chain reference this operation.
  if(observed.binding===null)await store.set('lore.s.binding',op,binding);
 }
 const policy=await policyModule.create({pi,store,binding,...delegates});
 if(request.action==='accept'){
  const accepted=await policy.lane.accept({kind:'prompt',operationId:op,prompt:policy.prompt},pi.context);
  requireValue(accepted.ok,'invalid_request','Pi rejected original acceptance');
  observed=await store.inspect(op);requireValue(observed.meta&&observed.state,'session_corrupt','accepted original missing');
  return output({boundary_kind:'accepted'});
 }
 requireValue(observed.binding!==null&&stateKind!=='binding_only','invalid_request','explicit accept required before drive');
 if(!observed.result){
  const driven=policy.lane.drive({operationId:op},pi.context).then(async()=>{await policy.afterDrive();return {complete:true};});
  const outcome=await Promise.race([driven,paused]);
  if(!outcome.complete)return output(outcome);
 }
 observed=await store.inspect(op);requireValue(observed.result,'paused_unknown','original operation has no saved result');
 const locator=store.locator(op,observed.result);const boundary={...policy.decide(observed.result,store.raw(),locator),operation_result_ref:locator};
 await store.set('lore.s.boundary',op,boundary);observed=await store.inspect(op);
 return output(boundary);
}
