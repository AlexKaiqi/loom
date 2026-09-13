"""Bounded startup-source calibration; does not modify original workload/protocol."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);a=ap.parse_args()
 if not a.batch.replace('-','').isalnum():raise ValueError('fresh batch name')
 out=ROOT/'validation/system/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);rows=[]
 sources=[ROOT/'validation/system'/n for n in ['throughput_protocol.json','throughput_oracle.py','throughput_controls.py','throughput_guard_protocol.json','throughput_guard_controls.py']]+[ROOT/'design/g3/system/throughput-workload.json']
 original={str(f):sha(f) for f in sources}
 for mode in ['normal','missing-sha','wrong-sha','missing-file']:
  home=out/mode;home.mkdir();ws=home/'workspace'
  for f in sources:
   q=ws/f.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(f.read_bytes())
  protocol=ws/'validation/system/throughput_protocol.json';obj=json.loads(protocol.read_text())
  if mode=='missing-sha':del obj['workload']['sha256'];save(protocol,obj)
  if mode=='wrong-sha':obj['workload']['sha256']='0'*64;save(protocol,obj)
  if mode=='missing-file':(ws/'design/g3/system/throughput-workload.json').unlink()
  copied={str(f):sha(f) for f in ws.rglob('*') if f.is_file()};save(home/'before.json',{'original':original,'copied_after_explicit_fault':copied,'mode':mode})
  argv=[sys.executable,'-B',str(ws/'validation/system/throughput_controls.py'),'--copied-output',str(home/'control-output')]
  with (home/'stdout').open('wb') as stdout,(home/'stderr').open('wb') as stderr:
   process=subprocess.run(argv,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws/'validation/system'),'PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout,stderr=stderr,timeout=20)
  result=json.loads((home/'control-output/result.json').read_text());unchanged=all(Path(k).is_file() and sha(Path(k))==v for k,v in copied.items()) and all(sha(Path(k))==v for k,v in original.items())
  accepted=process.returncode==0 and result['status']=='PASS' and [x['id'] for x in result['controls']]==[f'TH{i:02}' for i in range(1,18)] and all(x['status']=='PASS' for x in result['controls'])
  refused=process.returncode==2 and result['status']=='REJECTED_SOURCE' and result['controls']==[]
  bound=result['actual_oracle_import']==str(ws/'validation/system/throughput_oracle.py') and result['actual_oracle_sha256']==sha(ws/'validation/system/throughput_oracle.py')
  row={'id':mode,'status':'PASS' if unchanged and bound and (accepted if mode=='normal' else refused) else 'FAIL','actual_exit':process.returncode,'actual_status':result['status'],'controls_attempted':len(result['controls']),'source_unchanged':unchanged,'actual_oracle_import_bound':bound,'result_path':str(home/'control-output/result.json'),'result_sha256':sha(home/'control-output/result.json')};rows.append(row)
 result={'status':'PASS' if len(rows)==4 and all(x['status']=='PASS' for x in rows) else 'FAIL','scope':'STARTUP_GUARD_PREPARATION_ONLY','rows':rows};save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
