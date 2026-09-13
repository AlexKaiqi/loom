"""Direct fixed XN12 driver; missing/failed/omitted actions are never PASS."""
from pathlib import Path
import argparse,json,sys,time,traceback
from artifacts import canonical,save
from fixtures import dependencies
from case_context import Context
from case_actions import CASES
ROOT=Path(__file__).resolve().parents[3]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--component-json');ap.add_argument('--case');a=ap.parse_args()
 out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
 suite=json.loads((ROOT/'design/g3/x-node-profile/cases-inputs.json').read_text())['cases']
 expected=['XN'+str(i).zfill(2)for i in range(1,13)]
 if [x['id']for x in suite]!=expected or sorted(CASES)!=expected:raise SystemExit('fixed twelve-case inventory differs')
 selected=[x for x in suite if a.case is None or x['id']==a.case]
 result={'status':'INCOMPLETE','type':'FORMAL_INCREMENT_RUN'if a.case is None else 'PARTIAL_DIAGNOSTIC','expected_case_ids':[x['id']for x in selected],'rows':[],'started':time.time()}
 def persist():(out/'assessment.json').write_bytes(canonical(result)+b'\n')
 if not a.component_json or not selected:
  result.update(status='MISSING_COMPONENT'if not a.component_json else 'MISSING_CASE',actual_runs=0);persist();return 4
 argv=json.loads(a.component_json)
 if not isinstance(argv,list)or not argv or not Path(argv[0]).is_file():result.update(status='MISSING_COMPONENT',actual_runs=0);persist();return 4
 deps=dependencies(out/'shared')
 for case in selected:
  row={'case_id':case['id'],'status':'INCOMPLETE','started':time.time()};result['rows'].append(row);ctx=None
  try:
   ctx=Context(case,argv,out/('case-'+case['id']),deps);CASES[case['id']](ctx);ctx.complete()
   if time.time()-row['started']>120:raise ValueError('original whole-case120sec deadline exceeded')
   row.update(status='PASS',actual_negative_variants=ctx.marked)
  except Exception as exc:
   row.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc(),actual_negative_variants=ctx.marked if ctx else [])
  finally:
   if ctx:
    try:ctx.finish()
    except Exception as exc:row.update(status='FAIL',cleanup_error=repr(exc))
   row['finished']=time.time();persist()
 result.update(actual_runs=len(result['rows']),finished=time.time())
 result['status']='PASS'if [x['case_id']for x in result['rows']]==result['expected_case_ids']and all(x['status']=='PASS'for x in result['rows'])else 'FAIL';persist()
 print(json.dumps({'status':result['status'],'actual_runs':result['actual_runs'],'failed':[{'case_id':x['case_id'],'error':x.get('error')}for x in result['rows']if x['status']!='PASS']}));return 0 if result['status']=='PASS'else 1
if __name__=='__main__':raise SystemExit(main())
