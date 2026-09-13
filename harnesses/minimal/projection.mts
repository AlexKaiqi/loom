import {join,dirname,resolve} from 'node:path';
import {readFile,requireValue,hash,canonical} from '../../lore_session/node/common.mts';
export function project(input:any){
 const paths=input.paths;const surface=resolve(paths.surface);
 let text=readFile(join(surface,'template.md'),surface,32768).toString('utf8');
 let count=0;
 text=text.replace(/\{\{([^{}]+)\}\}/g,(_all:string,name:string)=>{
  requireValue(++count<=32&&/^[a-zA-Z0-9_.\/-]+$/.test(name),'invalid_input','bounded ordinary block name required');
  return readFile(resolve(surface,name),surface,32768).toString('utf8');
 });
 const events=readFile(paths.events,dirname(paths.events),32768).toString('utf8');
 const feedback=readFile(paths.feedback,dirname(paths.feedback),32768).toString('utf8');
 const blocks=[text,'Fixed event view:\n'+events,'Prior feedback:\n'+feedback,
  'Shell target runtime: cwd=/work, containing its authorized Surface working copy. '+
  'Shell target workspace: cwd=/work, containing its authorized Workspace working copy. '+
  'These are separate environments; use relative ordinary file names in the selected target. '+
  'Harness read-only input sources used to render this context are not Shell working directories. '+
  'Read-only history catalog: /input/history/... is available in the runtime shell only; use the exact published catalog path. '+
  'Inspect needed files with ordinary tools.'];
 const history=input.history_views??[];
 requireValue(Array.isArray(history)&&history.length<=1,'invalid_input','bounded original history catalog required');
 for(const row of history){
  const version=row.version_ref;
  requireValue(row&&Object.keys(row).sort().join(',')==='read_path,version_ref'&&version&&
   Object.keys(version).sort().join(',')==='archive_sha256,domain,git_ref,manifest_sha256,profile,resource_id'&&
   version.domain==='workspace'&&version.profile==='host-v1'&&typeof version.resource_id==='string'&&version.resource_id.length>0&&
   typeof version.git_ref==='string'&&/^refs\/lore\/versions\/[A-Za-z0-9_-]+$/.test(version.git_ref)&&
   ['archive_sha256','manifest_sha256'].every(k=>typeof version[k]==='string'&&/^[0-9a-f]{64}$/.test(version[k]))&&
   row.read_path==='/input/history/'+hash(canonical(version)),
   'invalid_input','history path differs from complete original Workspace version');
 }
 if(history.length){
  blocks.push("This Step's Workspace snapshot is in history_views below. "+
   'Published changes appear in the next Step. Earlier tool paths describe older inputs; '+
   'the catalog alone does not mean the goal is complete.');
  blocks.push(JSON.stringify({history_views:history}));
 }
 for(const descriptor of Object.values(input.original_refs??{}) as any[]){
  const raw=readFile(descriptor.path,dirname(descriptor.path));
  requireValue(raw.length===descriptor.bytes&&hash(raw)===descriptor.sha256,'integrity_mismatch','original projection source differs');
  const head=Math.min(78,raw.length),tail=Math.max(head,raw.length-44);
  const retained_ranges=tail===head?[[0,raw.length]]:[[0,head],[tail,raw.length]];
  blocks.push(JSON.stringify({clipped:tail>head,owner:'F',read_path:descriptor.read_path,source_ref:descriptor.source_ref,
   source_sha256:descriptor.sha256,source_bytes:raw.length,retained_ranges,
   fragments:retained_ranges.map(([a,b])=>new TextDecoder('utf-8',{fatal:true}).decode(raw.subarray(a,b)))}));
 }
 return JSON.stringify({context_blocks:blocks});
}
