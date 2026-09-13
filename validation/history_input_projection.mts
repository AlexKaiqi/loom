import {readFileSync,writeFileSync} from 'node:fs';
import {project} from '../harnesses/minimal/projection.mts';
const [input,output]=process.argv.slice(2);const cases=JSON.parse(readFileSync(input,'utf8'));
const results=cases.map((item:any)=>{try{return {name:item.name,ok:true,text:project(item.input)};}catch(error){return {name:item.name,ok:false,error:String(error)};}});
writeFileSync(output,JSON.stringify(results));
