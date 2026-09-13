import {readFileSync} from 'node:fs';
import {isAbsolute} from 'node:path';
import {Stdio} from './stdio.mts';
import {run} from './adapter.mts';
import {json,requireValue,BoundaryError} from './common.mts';
const args=process.argv.slice(2);let request:any={};const transport=new Stdio();
try{
 requireValue(args.length===2&&args[0]==='--config'&&isAbsolute(args[1]),'invalid_request','fixed --config required');
 const config=json(readFileSync(args[1]));requireValue(config.schema==='lore.s.node/1','invalid_request','unknown trusted config');
 for(const key of ['pi_root','work_root','harness_entry'])requireValue(isAbsolute(config[key]),'invalid_request','absolute trusted paths required');
 for(const key of ['namespace','surface_id','session_id'])requireValue(typeof config.session_scope?.[key]==='string'&&config.session_scope[key].length>0,'invalid_request','complete trusted Session scope required');
 requireValue(Number.isSafeInteger(config.session_scope.session_generation)&&config.session_scope.session_generation>=1,'invalid_request','Session generation required');
 for(const key of ['apiKey','key','token','auth'])requireValue(!(key in config.model),'invalid_request','Node model is keyless');
 requireValue(!config.model.baseUrl||config.model.baseUrl==='http://localhost:0','invalid_request','Node never inherits a host provider URL');
 request=await transport.next();transport.send(await run(config,request,transport));process.exit(0);
}catch(error:any){
 transport.send({type:'result',operation_id:request.operation_id??null,boundary_kind:error?.code==='stopped_limit'?'stopped_limit':'blocked_invalid',error:{code:error instanceof BoundaryError?error.code:'session_corrupt',message:String(error.message??error)}});process.exit(0);
}
