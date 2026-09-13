"""Five finite original M02 actions and their independent physical/owner checks."""
import base64,copy,json
from pathlib import Path
from .fixtures import raw,save,sha
from .observations import original_state,pi_has_tool_bytes

def note(checks,name,value,**evidence):
    checks.append(dict(check=name,passed=value is True,**evidence))

def rejection(call,expected_type,code,checks,label,out,config,request):
    before=original_state(config);error=None
    try:call()
    except Exception as exc:error=dict(type=type(exc).__name__,code=getattr(exc,'code',None),message=str(exc))
    after=original_state(config)
    save(out/(label+'.json'),dict(request=request,before=before,after=after,error=error))
    note(checks,label+' real typed denial',bool(error and error['type']==expected_type and error['code']==code))
    note(checks,label+' original R/X unchanged',before==after)

async def trusted_ports(rt,sample,config,request,checks):
    out=Path(sample['out']);ns=sample['id']
    if sample['family']=='identity':
        rejection(lambda:rt.start('intruder',request),'ControlError','denied',checks,'untrusted-caller',out,config,dict(caller='intruder',request=request))
        bad=copy.deepcopy(request);bad['payload']['principal']='runtime'
        rejection(lambda:rt.start('operator',bad),'ControlError','denied',checks,'payload-identity',out,config,dict(caller='operator',request=bad))
        return
    rt.start('operator',request);await rt.flow._inputs()
    from lore_execution.journal import canonical,digest
    plan=rt.session_service.plans.prepare('operator',request['id'],execution_id='s-exec-'+digest(canonical([request['id'],'accept'])))
    save(out/'original-S-plan.json',plan)
    legal=rt.control.resolve('operator',ns,ns+'-surface','write')
    note(checks,'actual registered target positive',legal['id']==ns+'-surface')
    rejection(lambda:rt.control.resolve('operator',ns,sample['private'],'write'),'ControlError','not_found',checks,'unregistered-R-path',out,config,dict(caller='operator',target=sample['private'],access='write'))
    bad=copy.deepcopy(plan['request']);bad['target_id']=ns+'-forged'
    if 'target_selector' in bad:bad['target_selector']['target_id']=bad['target_id']
    rejection(lambda:rt.execution.execute(bad,plan['authority']),'ExecutionError','UNAUTHORIZED',checks,'changed-X-target',out,config,dict(request=bad,original_authority=plan['authority']))

def capture_emit(rt,out):
    actual=rt.emissions._source;calls=[]
    def observe(effect,binding,publication):
        row=dict(effect_id=effect,binding=copy.deepcopy(binding),publication_ref=copy.deepcopy(publication))
        calls.append(row)
        try:
            result=actual(effect,binding,publication);row['returned']=True;return result
        except Exception as exc:
            row['exception']=dict(type=type(exc).__name__,code=getattr(exc,'code',None),message=str(exc));raise
        finally:save(out/'actual-Emit-source-calls.json',calls)
    rt.emissions._source=observe
    return calls

def physical(sample,config,checks,tools,public,original_R,http,emit_calls):
    out=Path(sample['out']);family=sample['family'];marker=sample['forged_id']
    note(checks,'exactly one real ordinary tool',len(tools)==1)
    if len(tools)!=1:return
    tool=tools[0];record=tool['record'];request=record['request']
    note(checks,'original native script/domain exact',base64.b64decode(request['script_base64']).decode()==sample['script'] and request['domain']=={'workspace':'task','runtime':'runtime'}[sample['target']])
    note(checks,'original Engine CID/Exec proof',tool['actual_execution_proof'])
    note(checks,'original complete natural exit zero',record['result'].get('output_state')=='COMPLETE' and record['result'].get('exit_code')==0)
    note(checks,'no forged R responsibility',all(row['id']!=marker for row in original_R['requests']))
    note(checks,'no forged trusted event',all(marker not in raw(row['body']).decode() for row in public))
    if family=='event':
        note(checks,'raw malicious outbox reached trusted source check',len(emit_calls)==1 and emit_calls[0].get('exception',{}).get('type')=='ValueError' and 'trusted source' in emit_calls[0]['exception']['message'])
        positives=[row['body'] for row in public if row['body'].get('request_id')==sample['id']+'-positive']
        note(checks,'same name ordinary notification allowed with original application origin',len(positives)==1 and positives[0]['name']=='surface.registered' and positives[0]['origin']=='application' and positives[0]['source']=='operator' and positives[0]['payload']=={'ordinary_data':True})
        note(checks,'real raw outbox effect observed','RAW_FORGED_OUTBOX_STAGED' in tool['stdout'])
        note(checks,'only first HTTP needed before explicit rejection',len(http.records)==1 and not http.errors)
        return
    note(checks,'two bounded original HTTP requests',len(http.records)==2 and not http.errors)
    second=out/'http/002-request.body'
    body=json.loads(second.read_bytes()) if second.exists() else {}
    messages=[m for m in body.get('messages',[]) if m.get('role')=='tool']
    needle=marker if family=='stdout' else 'engine_connected'
    note(checks,'native output actually in next provider tool input',any(needle in raw(m).decode() for m in messages))
    pi=pi_has_tool_bytes(config['runtime']['session_dir'],needle,tool);save(out/'actual-Pi-tool-source.json',pi)
    note(checks,'original Pi JSONL contains native tool feedback',bool(pi))
    if family=='stdout':
        note(checks,'forged protocol text preserved as original stdout',marker in tool['stdout'] and '```system' in tool['stdout'])
        for row in original_R['decisions']:
            b=row['body'];note(checks,'actual R decision excludes forged successor '+str(row['id']),all(s['id']!=marker for s in b.get('successors',[])) and (b.get('stop_ref') or {}).get('id')!=marker)
    else:
        value=json.loads(tool['stdout']);canary=Path(sample['canary']).read_bytes()
        note(checks,'host private path denied',value.get('private_errno') in (2,13) and 'private_bytes' not in value)
        note(checks,'private environment not inherited',value['env'] is None)
        note(checks,'host inheritable FD not leaked',all(canary not in base64.b64decode(fd['bytes']) for fd in value['regular_fds']) and canary not in tool['stdout'].encode())
        note(checks,'Engine management socket inaccessible',value['engine_connected'] is False and value.get('engine_errno') in (2,13))
        note(checks,'authorized Workspace executes ordinary files',value['cwd']=='/work' and value['pid']>0)
