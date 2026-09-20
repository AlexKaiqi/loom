// Independent test peer for the documented newline JSON-RPC wire contract.
import net from 'node:net';
import {readFileSync,writeFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {createHash} from 'node:crypto';
export function createWorkerConnection(role) {
 const socket=new net.Socket({fd:3,readable:true,writable:true});
 const handlers=new Map(),requests=new Map();let counter=0,pending='';let ready=false;
 const request=(method,params)=>new Promise((resolve,reject)=>{const id='fixture-'+(++counter);requests.set(id,{resolve,reject});socket.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n')});
 handlers.set('session.hello',p=>{
  if(ready||p.protocol_version!=='loom/1'||p.peer_role!==role)throw new Error('handshake');
  ready=true;
  return {protocol_version:'loom/1',schema_version:1,role,max_frame_bytes:4194304,capabilities:[role+'/1','context.feedback/1','userspace.binding/1']};
 });
 handlers.set('policy.resume',p=>request('model.resume',{protocol_version:'loom/1',schema_version:1,checkpoint_id:p.checkpoint_id,request_key:'resume:'+p.checkpoint_id}));
 const handoff=async p=>{const cp=await request('checkpoint.commit',{protocol_version:'loom/1',schema_version:1,content_version:p.content_version,previous_checkpoint_id:p.previous_checkpoint_id,resource_copies:p.resource_copies});return request('round.handoff',{protocol_version:'loom/1',schema_version:1,checkpoint_id:cp.checkpoint_id,handled_input_ids:p.claimed_input_ids,intent:'wait'})};
 handlers.set('policy.finish',handoff);
 socket.on('data',data=>{
  pending+=data.toString('utf8');
  for(let pos;(pos=pending.indexOf('\n'))>=0;){
   const line=pending.slice(0,pos);pending=pending.slice(pos+1);const request=JSON.parse(line);
   if(request.id===undefined)continue;
   if(!request.method){const saved=requests.get(request.id);requests.delete(request.id);if(saved){if(request.error)saved.reject(new Error('host error'));else saved.resolve(request.result)}continue;}
   Promise.resolve().then(()=>{const p=request.params;if(p?.turn_ref){const raw=readFileSync(p.turn_path);if(String(raw.length)!==p.turn_ref.size_bytes||createHash('sha256').update(raw).digest('hex')!==p.turn_ref.sha256)throw new Error('turn reference');p.turn=JSON.parse(raw)}return handlers.get(request.method)(p)}).then(result=>socket.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\n'),()=>socket.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32001,message:'fixture rejected'}})+'\n'));
  }
 });
 socket.on('end',()=>process.exit(0));
 return {onRequest:(name,handler)=>handlers.set(name,handler),listen:()=>{},request,handoff,
  publish:async(p,result)=>{if(!result)return null;const name=randomUUID()+'.json';writeFileSync(p.output_directory+'/'+name,JSON.stringify(result));const record_ref=await request('record.put',{protocol_version:'loom/1',schema_version:1,media_type:'application/vnd.loom.projection+json',path:name});const published=await request('projection.publish',{protocol_version:'loom/1',schema_version:1,record_ref,content_version:p.content_version,harness_ref:p.harness_ref,view_id:p.view_id});return p.model_operation==='model.start'?request('model.start',{protocol_version:'loom/1',schema_version:1,projection_ref:published.projection_ref,request_key:'advance:'+p.view_id}):published}
 };
}
