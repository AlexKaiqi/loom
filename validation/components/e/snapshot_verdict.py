"""Fixed inventories for two independent frozen E validation entries."""
ORIGINAL=['E'+str(i).zfill(2) for i in range(1,16)]
OBSERVATION=['EO'+str(i).zfill(2) for i in range(1,11)]
def original(value):
 return value.get('case_ids')==ORIGINAL and value.get('tests_run')==15 and value.get('preparation_tests')==9 and not any(value.get(k) for k in ['errors','failures','skipped','expected_failures','unexpected_successes'])
def observation(value):
 control=value.get('preparation_controls',{});rows=value.get('cases',[]);checks=control.get('checks',[])
 return value.get('case_ids')==OBSERVATION and value.get('tests_run')==10 and not any(value.get(k) for k in ['errors','failed_checks','skipped']) and control.get('status')=='PASS' and len(checks)==5 and all(r.get('passed') is True for r in checks) and [r.get('id') for r in rows]==OBSERVATION and all(r.get('status')=='PASS' for r in rows) and value.get('cleanup',{}).get('owned_nats_reaped') is True
