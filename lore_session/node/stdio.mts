import {BoundaryError,requireValue,json} from './common.mts';
export class Stdio {
 private buffer=Buffer.alloc(0);private queue:any[]=[];private waiter:{resolve:(v:any)=>void,reject:(e:any)=>void}|undefined;private ended=false;
 constructor(private cap=1048576){
  process.stdin.on('data',(data:Buffer)=>{try{
   this.buffer=Buffer.concat([this.buffer,data]);requireValue(this.buffer.length<=this.cap,'invalid_request','control frame limit');
   let at:number;while((at=this.buffer.indexOf(10))>=0){const line=this.buffer.subarray(0,at);this.buffer=this.buffer.subarray(at+1);const value=json(line);
    if(this.waiter){const w=this.waiter;this.waiter=undefined;w.resolve(value);}else {requireValue(this.queue.length<2,'invalid_request','unsolicited frames');this.queue.push(value);}
   }
  }catch(error){this.fail(error);}});
  process.stdin.on('end',()=>{this.ended=true;if(this.waiter)this.fail(new BoundaryError('transport_unavailable','stdio ended before reply'));});
  process.stdin.on('error',error=>this.fail(error));
 }
 private fail(error:any){this.ended=true;if(this.waiter){const w=this.waiter;this.waiter=undefined;w.reject(error);}else this.queue=[{__error:error}];}
 async next(){if(this.queue.length){const item=this.queue.shift();if(item.__error)throw item.__error;return item;}requireValue(!this.ended,'transport_unavailable','input closed');return await new Promise<any>((resolve,reject)=>{this.waiter={resolve,reject};});}
 send(frame:any){const data=Buffer.from(JSON.stringify(frame)+'\n');requireValue(data.length<=this.cap,'output_limit','control output limit');process.stdout.write(data);}
 async ask(frame:any,replyType:string){this.send(frame);const reply=await this.next();requireValue(reply?.type===replyType&&reply.effect_id===frame.effect_id,'transport_unavailable','reply type/identity mismatch');
  for(const key of ['response_entry_id','invocation_id'])if(frame[key]!==undefined)requireValue(reply[key]===frame[key]||reply.error,'transport_unavailable','reply original '+key+' mismatch');
  return reply;
 }
}
