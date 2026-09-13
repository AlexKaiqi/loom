"""Seventeen preregistered small controls; copies its actual executable oracle first."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def run_controls(out):
    import throughput_oracle as oracle
    from throughput_oracle import expected_result,verify_report,Workload,OracleInvalid
    out=Path(out);out.mkdir(exist_ok=False);rows=[]
    def eq(a,b):
        if a!=b:raise AssertionError((a,b))
    def denied(fn):
        try:fn()
        except OracleInvalid:return
        raise AssertionError('invalid source/report accepted')
    encode=lambda obj:json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
    spec=Workload(jobs=2,seed_base=0,rounds=2);source={'schema_version':1,'job_index':0,'seed':0,'rounds':2};report={**source,'result':1196435763};raw=encode(source);digest=hashlib.sha256(raw).hexdigest()
    def verify(value=report,input_bytes=raw,input_hash=digest,index=0):
        return verify_report(encode(value) if isinstance(value,dict) else value,input_bytes,job_index=index,input_sha256=input_hash,workload=spec)
    def grouped_noninteger():
        for field in report:
            for value in [True,1.0,'1',None]:denied(lambda f=field,v=value:verify({**report,f:v}))
        for field in source:
            changed=encode({**source,field:1.0});denied(lambda b=changed:verify(input_bytes=b,input_hash=hashlib.sha256(b).hexdigest()))
    def missing_json():
        for value in [None,b'',b'{',b'{"schema_version":1,"schema_version":1,"job_index":0,"seed":0,"rounds":2,"result":1196435763}']:
            denied(lambda v=value:verify(v))
    def altered_source():
        changed=encode({**source,'seed':1});denied(lambda:verify(input_bytes=changed,input_hash=hashlib.sha256(changed).hexdigest()))
    cases=[
      ('TH01',lambda:eq(expected_result(123,0),123)),
      ('TH02',lambda:eq(expected_result(7,1),1025555898)),
      ('TH03',lambda:eq(expected_result(0,2),1196435763)),
      ('TH04',lambda:eq(expected_result(1,2),1586005468)),
      ('TH05',lambda:[eq(expected_result(19,n,multiplier=1,increment=0),19+n*(n-1)//2) for n in [0,1,2,7,37]]),
      ('TH06',lambda:[eq(expected_result(23,n,multiplier=0,increment=13),13+n-1) for n in [1,2,17]]),
      ('TH07',lambda:eq(verify()['expected_result'],1196435763)),
      ('TH08',lambda:denied(lambda:verify({**report,'seed':1}))),
      ('TH09',lambda:denied(lambda:verify({**report,'rounds':3}))),
      ('TH10',lambda:denied(lambda:verify({**report,'result':0}))),
      ('TH11',lambda:denied(lambda:verify({**report,'PASS':True}))),
      ('TH12',grouped_noninteger),('TH13',missing_json),
      ('TH14',lambda:denied(lambda:verify(input_hash='0'*64))),
      ('TH15',altered_source),
      ('TH16',lambda:denied(lambda:verify(index=1))),
      ('TH17',lambda:denied(lambda:verify_report({'status':'PASS'},raw,job_index=0,input_sha256=digest,workload=spec))),
    ]
    protocol=json.loads((ROOT/'validation/system/throughput_protocol.json').read_text())
    workload_path=ROOT/'design/g3/system/throughput-workload.json'
    try:actual_workload_sha=sha(workload_path)
    except OSError:actual_workload_sha=None
    declared=protocol.get('workload',{}).get('sha256')
    if not isinstance(declared,str) or actual_workload_sha is None or declared!=actual_workload_sha:
        save(out/'result.json',{'status':'REJECTED_SOURCE','scope':'PREPARATION_STARTUP_GUARD','controls':[],
             'actual_oracle_import':str(Path(oracle.__file__).resolve()),'actual_oracle_sha256':sha(Path(oracle.__file__)),
             'declared_workload_sha256':declared,'actual_workload_sha256':actual_workload_sha,
             'reason':'workload_source_missing_or_mismatch'})
        return 2
    if [x[0] for x in cases]!=[x['id'] for x in protocol['controls']]:raise ValueError('original control inventory differs')
    original_spec=oracle.load_workload(ROOT/'design/g3/system/throughput-workload.json')
    if original_spec!=Workload():raise ValueError('formal workload defaults differ from frozen source')
    for id,fn in cases:
        row={'id':id,'status':'FAIL'}
        try:fn();row['status']='PASS'
        except Exception as exc:row['error']={'type':type(exc).__name__,'message':str(exc)}
        rows.append(row)
    result={'status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL','scope':'PREPARATION_ONLY_NO_TASK_WORKLOAD','controls':rows,'actual_oracle_import':str(Path(oracle.__file__).resolve()),'actual_oracle_sha256':sha(Path(oracle.__file__)),'workload_source_sha256':sha(ROOT/'design/g3/system/throughput-workload.json'),'formal_rounds_read_not_executed':original_spec.rounds,'runtime_or_candidate_imported':False,'limits':'Small independent vectors and strict raw-byte checker only; no F historical-link resolution, original authority provenance or system performance claim.'}
    save(out/'result.json',result);return 0 if result['status']=='PASS' else 1

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--batch');ap.add_argument('--copied-output');a=ap.parse_args()
    if a.copied_output:return run_controls(a.copied_output)
    if not a.batch or not a.batch.replace('-','').isalnum():raise ValueError('fresh batch required')
    out=ROOT/'validation/system/evidence'/a.batch;out.mkdir(parents=True,exist_ok=False);ws=out/'workspace';bindings=[]
    paths=[ROOT/'validation/system'/name for name in ['throughput_protocol.json','throughput_oracle.py','throughput_controls.py']]+[ROOT/'design/g3/system/throughput-workload.json']
    for original in paths:
        dest=ws/original.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original.read_bytes());bindings.append({'original':str(original),'copy':str(dest),'sha256':sha(original)})
    argv=[sys.executable,'-B',str(ws/'validation/system/throughput_controls.py'),'--copied-output',str(out/'controls')];env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(ws/'validation/system'),'PYTHONDONTWRITEBYTECODE':'1'};before={'argv':argv,'environment':env,'bindings':bindings,'started':time.time()};save(out/'before.json',before)
    with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
        process=subprocess.run(argv,cwd=ws,env=env,stdout=stdout,stderr=stderr,timeout=20)
    child=json.loads((out/'controls/result.json').read_text());unchanged=all(sha(Path(row[k]))==row['sha256'] for row in bindings for k in ['original','copy']);bound=child['actual_oracle_import']==str(ws/'validation/system/throughput_oracle.py') and child['actual_oracle_sha256']==sha(ws/'validation/system/throughput_oracle.py')
    result={'status':'PASS' if process.returncode==0 and child['status']=='PASS' and unchanged and bound and len(child['controls'])==17 else 'FAIL','scope':'COPY_BOUND_PREPARATION_ONLY','actual_exit':process.returncode,'source_unchanged':unchanged,'actual_oracle_import_bound':bound,'controls':len(child['controls']),'before_sha256':sha(out/'before.json'),'child_result_sha256':sha(out/'controls/result.json'),'finished':time.time()};save(out/'result.json',result);print(json.dumps(result));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
