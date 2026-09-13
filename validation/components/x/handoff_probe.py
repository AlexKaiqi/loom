"""Finite existing-facility calibration of external handoff; never X product."""
from pathlib import Path
import base64,copy,hashlib,http.client,json,os,socket,subprocess,sys,time
from fixtures import create
from collector import Collector,ENV
from f_handoff import Handoff,saved
from oracle import EvidenceError
ROOT=Path(__file__).resolve().parents[3]
def require(x,m):
 if not x:raise AssertionError(m)
def rejected(fn):
 try:fn()
 except (EvidenceError,ValueError,FileNotFoundError) as e:return {'rejected':True,'error':str(e)}
 return {'rejected':False}
def main():
 out=Path(sys.argv[1]);out.mkdir();results={'kind':'FIXTURE_CALIBRATION_NOT_X_COMPONENT','controls':[]}
 def control(name,fn):
  try:value=fn();row={'id':name,'pass':value is True,'observed':value}
  except Exception as e:row={'id':name,'pass':False,'error':repr(e)}
  results['controls'].append(row);saved(out/'assessment.json',results)
 # Missing and forged F provenance must fail before Docker/candidate import.
 from source_closure import verify_f
 eq=ROOT/'f-source-equivalence.json';before=eq.read_bytes()
 def missing():
  eq.rename(ROOT/'f-source-equivalence.saved')
  try:return rejected(lambda:verify_f(ROOT))['rejected']
  finally:(ROOT/'f-source-equivalence.saved').rename(eq)
 control('missing-F-copy-equivalence',missing)
 def forged():
  obj=json.loads(before);obj['implementation'][0]['sha256']='0'*64;eq.write_text(json.dumps(obj))
  try:return rejected(lambda:verify_f(ROOT))['rejected']
  finally:eq.write_bytes(before)
 control('fake-F-source-reference',forged)
 child=subprocess.run([sys.executable,'-B','-c','import lore_files,json;from pathlib import Path;print(json.dumps({"file":str(Path(lore_files.__file__).resolve())}))'],cwd=ROOT,capture_output=True,text=True,env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'})
 saved(out/'source-child.json',{'pid_source':'per-PID audit','exit':child.returncode,'stdout':child.stdout,'stderr':child.stderr})
 control('actual-child-imports-copied-F',lambda:child.returncode==0 and Path(json.loads(child.stdout)['file']).is_relative_to(ROOT))
 for edited in (False,True):
  dest=out/('edited' if edited else 'unchanged');dest.mkdir();fx=create(dest/'fixture',{'initial':{'script':'effect'}},{'domain':'task'});handoff=Handoff(fx,dest);c=Collector(dest,fx);cid=None;volume='lore-x-probe-'+fx['request']['execution_id'];frames={}
  try:
   c.run(['docker','volume','create','--label','lore.x.execution_id='+fx['request']['execution_id'],'--driver','local','--opt','type=tmpfs','--opt','device=tmpfs','--opt','o=size=2m,nr_inodes=128,uid=1000,gid=1000,mode=0700,nosuid,nodev',volume])
   # Trusted fixture import has only readonly host archive and one private writable volume.
   c.helper(['--user','1000:1000','--mount','type=bind,src='+handoff.base['archive_path']+',dst=/base.tar,readonly','--mount','type=volume,src='+volume+',dst=/work,volume-nocopy',ENV['image'],'tar','--numeric-owner','-xpf','/base.tar','-C','/work'])
   cid=c.run(['docker','create',*c.options(),'--label','lore.x.execution_id='+fx['request']['execution_id'],'--user','0:0','--mount','type=volume,src='+volume+',dst=/work,volume-nocopy',ENV['image'],'sleep','60'])[1].decode().strip();c.run(['docker','start',cid])
   endpoint=json.loads(c.run(['docker','context','inspect'])[1])[0]['Endpoints']['docker']['Host'];require(endpoint.startswith('unix://'),'Unix Engine endpoint')
   class Unix(http.client.HTTPConnection):
    def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(endpoint[7:])
   def api(path,obj):
    h=Unix('localhost',timeout=5);h.request('POST','/v1.48'+path,json.dumps(obj).encode(),{'Content-Type':'application/json'});z=h.getresponse();by=z.read(1048577);h.close();n=c.serial;c.serial+=1;saved(dest/f'raw-{n:04d}.request.json',{'path':path,'body':obj});(dest/f'raw-{n:04d}.response').write_bytes(by);require(z.status in (200,201),'Engine response '+str(z.status));return json.loads(by) if by else None
   script=base64.b64decode(fx['request']['script_base64']).decode();eid=api('/containers/'+cid+'/exec',{'AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'User':'1000:1000','Cmd':['python','-c',script]})['Id'];api('/exec/'+eid+'/start',{'Detach':True,'Tty':False})
   deadline=time.monotonic()+5
   while c.exec_inspect(eid)['Running']:
    require(time.monotonic()<deadline,'bounded effect completion');time.sleep(.02)
   require(c.exec_inspect(eid)['ExitCode']==0,'actual harmless effect exit')
   c.run(['docker','pause',cid]);binding={'container_id':cid,'exec_id':eid,'volume_id':volume,'object_generation':1,'freeze_generation':1,'domain':'task'}
   parsed,_=c.export(volume);rawpath=next(q for q in dest.glob('*.independent.tar') if hashlib.sha256(q.read_bytes()).hexdigest()==parsed['sha256']);checkpoint=fx['state']/'checkpoint.tar';checkpoint.write_bytes(rawpath.read_bytes());ref={'path':str(checkpoint),'sha256':parsed['sha256'],'size':parsed['size']};response={'binding':binding,'artifacts':{'checkpoint':ref}}
   frames['prepared']=c.capture(response,binding,'prepared');handoff.prepared(frames['prepared'])
   if edited:(fx['target']/'human-edit').write_bytes(b'actual-human-edit');fx['human_edit']=True
   frames['sealed']=copy.deepcopy(frames['prepared'])
   control(('edited-' if edited else 'unchanged-')+'still-running-rejected',lambda:rejected(lambda:handoff.validate(frames,c))['rejected'])
   wrong=copy.deepcopy(frames);wrong['sealed']['api']['binding']['object_generation']=2
   control(('edited-' if edited else 'unchanged-')+'wrong-generation-rejected',lambda:rejected(lambda:handoff.validate(wrong,c))['rejected'])
   wrong=copy.deepcopy(frames);wrong['sealed']['api']['artifacts']['checkpoint']['sha256']='0'*64
   control(('edited-' if edited else 'unchanged-')+'fake-checkpoint-rejected',lambda:rejected(lambda:handoff.validate(wrong,c))['rejected'])
   c.run(['docker','kill',cid]);frames['sealed']=c.capture(response,binding,'sealed');answer=handoff.validate(frames,c);saved(dest/'handoff-response.json',answer)
   if edited:
    observed=json.loads((handoff.out/'installation.json').read_text());control('actual-F-BASE_CHANGED-keeps-two-roots-human',lambda:answer.get('error',{}).get('original_code')=='BASE_CHANGED' and observed['before']==observed['after'] and observed['human_bytes_hex']==b'actual-human-edit'.hex())
   else:control('actual-F-no-edit-installs',lambda:answer['installation']['status']=='installed_pending_confirmation' and (fx['target']/'effect').read_bytes()==b'one\n')
  except Exception as exc:results['controls'].append({'id':('edited' if edited else 'unchanged')+'-facility-sequence','pass':False,'error':repr(exc)})
  finally:
   if cid:c.run(['docker','rm','-f',cid],check=False)
   c.run(['docker','volume','rm',volume],check=False);saved(out/'assessment.json',results)
 results['status']='PASS' if all(x['pass'] for x in results['controls']) and len(results['controls'])==11 else 'FAIL';saved(out/'assessment.json',results);print(json.dumps({'status':results['status'],'controls':results['controls']}));return 0 if results['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
