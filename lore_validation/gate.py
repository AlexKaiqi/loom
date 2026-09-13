"""Finite external acceptance gate for fixed evidence and trusted local checkers."""
from pathlib import Path
from copy import deepcopy
from .validation import ValidationError,digest,fail,finite,ids,indexed,local_dir,strict_json,verify_file
LEVELS={'ANALYZED','MODELED','COMPONENT','INTEGRATION','SYSTEM'}

def baseline(workspace,path,submission):
 plan,raw=strict_json(path)
 if type(plan) is not dict or plan.get('schema')!='lore-validation-baseline/v1':fail('unsupported baseline')
 if submission.get('baseline_sha256')!=digest(raw):fail('baseline changed','version_mismatch')
 verify_file(workspace,plan['requirements_source']);source,_=strict_json(Path(workspace)/plan['requirements_source']['path'])
 if type(source) is not list:fail('requirements source is not a list')
 required=ids([r.get('id') if type(r) is dict else None for r in source],'original requirements')
 mappings=plan.get('requirements')
 if type(mappings) is not dict or set(mappings)!=required:fail('original requirements coverage differs')
 runs=indexed(plan.get('runs'),'baseline runs');checks=indexed(plan.get('checks'),'baseline checks')
 for rid,run in runs.items():ids(run.get('cases'),'cases for '+rid)
 for requirement,covered in mappings.items():
  if not ids(covered,'checks for '+requirement)<=set(checks):fail('unknown required check')
 for check in checks.values():
  if check.get('run_id') not in runs or check.get('level') not in LEVELS:fail('invalid check run or evidence type')
 if set(c['run_id'] for c in checks.values())!=set(runs):fail('unverified extra run')
 bindings=plan.get('bindings')
 if type(bindings) is not list or not bindings:fail('missing current version bindings')
 ids([r.get('path') if type(r) is dict else None for r in bindings],'bound files')
 bound=[verify_file(workspace,ref) for ref in bindings]
 return plan,digest(raw),runs,checks,bound

def observe(run,directory,expected_level,observers):
 name=run.get('observer')
 if type(name) is not str or not callable(observers.get(name)):fail('missing trusted observer','missing')
 try:actual=deepcopy(observers[name](deepcopy(run),directory))
 except Exception as e:fail('independent observer failed: '+str(e),'observation_failed')
 if type(actual) is not dict:fail('missing actual observed run','observation_failed')
 finite(actual)
 if actual.get('run_id')!=run['id'] or actual.get('level')!=expected_level:fail('run identity/evidence level mismatch','observation_failed')
 expected=ids(run['cases'],'run cases')
 for field in ['started','finished']:
  if ids(actual.get(field),'actual '+field)!=expected:fail('actual cases differ','observation_failed')
 if actual.get('skipped')!=[] or type(actual.get('skipped')) is not list:fail('skipped or missing execution','observation_failed')
 if type(actual.get('exit_code')) is not int or actual['exit_code']!=0:fail('actual runner did not exit zero','observation_failed')
 artifacts=actual.get('artifacts')
 if type(artifacts) is not dict or not artifacts:fail('actual artifacts missing','observation_failed')
 for ref in artifacts.values():verify_file(directory,ref)
 return actual

def verify_check(spec,actual,directory,checkers):
 name=spec.get('checker')
 if type(name) is not str or not callable(checkers.get(name)):fail('missing trusted checker','missing')
 try:result=deepcopy(checkers[name](deepcopy(spec),deepcopy(actual),directory))
 except Exception as e:fail('independent checker failed: '+str(e),'check_failed')
 if type(result) is not dict:fail('checker result absent','check_failed')
 finite(result)
 assertions=result.get('assertions');indexed(assertions,'actual assertions')
 if result.get('passed') is not True or any(a.get('passed') is not True for a in assertions):fail('independent assertion failed','check_failed')
 if type(result.get('facts')) is not dict:fail('original checker facts absent','check_failed')
 return {'id':spec['id'],'passed':True,'assertions':assertions,'facts':result['facts']}

def audit(workspace,baseline_path,evidence_root,submission_path,observers,checkers):
 result={'status':'FAIL','checks':[],'requirements':{},'runs':{},'failures':[],'baseline_sha256':None,'bindings':[]}
 try:
  submitted,_=strict_json(submission_path)
  if type(submitted) is not dict or submitted.get('schema')!='lore-validation-submission/v1':fail('unsupported submission')
  plan,baseline_digest,runs,checks,bound=baseline(workspace,baseline_path,submitted)
  result.update(baseline_sha256=baseline_digest,requirements=plan['requirements'],bindings=bound)
  offered=indexed(submitted.get('runs'),'submitted runs')
  if set(offered)!=set(runs):fail('submitted run coverage differs')
  directories={rid:local_dir(evidence_root,offered[rid]['evidence_dir']) for rid in runs}
  for rid,spec in runs.items():
   levels={c['level'] for c in checks.values() if c['run_id']==rid}
   if len(levels)!=1:fail('mixed evidence levels in one raw run')
   try:result['runs'][rid]=observe(spec,directories[rid],next(iter(levels)),observers)
   except ValidationError as e:result['failures'].append({'run_id':rid,'code':e.code,'message':str(e)})
  for cid,spec in checks.items():
   rid=spec['run_id']
   if rid not in result['runs']:
    result['failures'].append({'check_id':cid,'code':'observation_failed','message':'mandatory raw run did not validate'});continue
   try:result['checks'].append(verify_check(spec,result['runs'][rid],directories[rid],checkers))
   except ValidationError as e:result['failures'].append({'check_id':cid,'code':e.code,'message':str(e)})
  # Recheck current inputs and original artifacts after callbacks; report tampering as failure.
  baseline(workspace,baseline_path,submitted)
  for rid,actual in result['runs'].items():
   for ref in actual['artifacts'].values():verify_file(directories[rid],ref)
  if not result['failures'] and len(result['checks'])==len(checks) and len(result['runs'])==len(runs):result['status']='PASS'
 except ValidationError as e:result['failures'].append({'code':e.code,'message':str(e)})
 except (KeyError,TypeError,ValueError,OSError) as e:result['failures'].append({'code':'invalid','message':'missing or invalid acceptance data: '+str(e)})
 return result
