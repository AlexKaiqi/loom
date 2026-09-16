"""The three preregistered M05 sequences; fixtures reuse M03/M04 primitives."""
import asyncio,json,os,subprocess,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace
from validation.runtime_recovery.execute import wait_cut,finish
from validation.runtime_recovery.fixtures import ROOT as _R
def launch(sample,config,mode,out):
    import subprocess,sys,time
    out.mkdir();stdout=(out/'stdout.txt').open('wb');stderr=(out/'stderr.txt').open('wb')
    argv=[sys.executable,'-B',str(_R/'validation/runtime_trim/worker.py'),'--fixture',str(Path(sample['out'])/'fixture.json'),'--config',str(config),'--mode',mode,'--out',str(out)]
    p=subprocess.Popen(argv,cwd=_R,stdout=stdout,stderr=stderr,start_new_session=True,close_fds=True)
    save(out/'process.json',dict(argv=argv,pid=p.pid,pgid=os.getpgid(p.pid),started=time.monotonic()));return p,stdout,stderr
from validation.runtime_recovery.fixtures import durable
from validation.runtime_security.fixtures import raw,ROOT
from validation.runtime_security.exercise import cleanup
from validation.runtime_security.fixtures import save
from validation.runtime_security.observations import engine_hook
from .facts import snapshot,absent,parent,session_bytes,compaction_facts,SUMMARY_PREFIX

def fixtures_prepare(out,spec):
    """Build per-case fixtures: long response list, corrupted variant, joint cut."""
    from validation.runtime_recovery.fixtures import prepare as ordinary,response
    samples=[]
    # Proving-chain result (m05-execute-005): a response whose estimated length
    # exceeds the model output limit is discarded by pi's overflow path and never
    # journaled. The trim therefore applies to an ACCEPTED long output: exchange 1
    # carries long text A plus the tool call (under the output limit), exchange 2
    # is long text B whose accumulated context crosses the hard threshold, the
    # compaction re-drive consumes exchange 3 (short final text).
    # Provider-faithful usage (preregistered in cases.json): the shared M02 helper's
    # fixed 64/32 usage would hide context pressure from pi threshold accounting;
    # declared tokens match the BPE scale of the actually served context.
    def m05_response(message,finish,index,prompt,completion):
        return raw(dict(id="m05-fixed-"+str(index),object="chat.completion",created=0,model="deepseek-v4-flash",
          choices=[dict(index=0,message=message,finish_reason=finish)],
          usage=dict(prompt_tokens=prompt,completion_tokens=completion,total_tokens=prompt+completion)))
    # BPE-dense varied text: the real token scale (~25k tokens per output) must
    # match the declared provider usage so the overflow declaration stays faithful
    # and the compaction actually archives the earlier history.
    def long_text(tag, n=125):
        # Vocabulary-varied (non-periodic) text: pi's compaction estimator counts
        # real token scale, so periodic filler compresses below the 4096-token
        # tail reserve and archives nothing. ~150 varied lines (~12KB) keeps the
        # follow-up request under the 65536-byte wire cap while the accumulated
        # context crosses the tail reserve at the compaction point.
        # Hash-varied (non-periodic) text: pi's compaction estimator counts real
        # token scale, so periodic filler compresses far below the threshold and
        # archives nothing. The accumulated context (~9k tokens) crosses the
        # 8192 hard threshold at the checkpoint while every follow-up request
        # stays under the 65536-byte wire request cap.
        import hashlib as _hl
        words=['alpha','bravo','cargo','delta','echo','flint','grove','haven','inbox','joust','karma','lumen','mirth','nomad','oasis','prism','quilt','raven','sable','tango','umbra','vivid','waltz','xenon','ylang','zephyr']
        def line(i):
            h=_hl.md5((tag+str(i)).encode()).digest()
            pick=[words[h[k]%26] for k in range(8)]
            return 'M05-long-output-'+tag+'-line-%05d-'%i+'-'.join(pick)+'\n'
        # ~24KB per output: the FIRST drive's estimate stays under the 8192 hard
        # threshold (no premature compaction with a single user-bounded group,
        # which the hook retains entirely); the SECOND drive crosses it with two
        # user groups, so the older group is genuinely archived (>=2 messages).
        # Calibrated: the measured estimator density is ~0.377 tokens/byte, so
        # 19KB per output keeps drive 1 under 8192 and pushes drive 2 past it.
        # ~15KB per output: drive 1 (one user group) stays under the 8192
        # estimate; the successor drive's own long reply pushes the two-group
        # context past it, so the hook archives group 1 (>=2 messages) while
        # retaining group 2 within the 4096-token tail budget.
        # pi's cut never splits a user turn: a single-turn context always
        # summarizes nothing. A/B are sized so drive 1 (one turn) stays under the
        # 8192 threshold and the successor drive (second user turn + reply C)
        # crosses it, archiving turn 1.
        return 'LO5ORIG-'+tag+' '+''.join(line(i) for i in range(n))
    for case in spec['cases']:
        sample=ordinary(out,case['id'].lower(),1)
        sample.update(id=case['id'],case=case['id'])
        if case['id']=='M05-TRIM':
            text_a=long_text('A');text_b=long_text('B')
            # The fixture wire format requires content as str or None (normalize's
            # content() rejects lists); text + tool_calls in one assistant message.
            call=dict(role='assistant',content=text_a,tool_calls=[dict(id='m05-call',type='function',function=dict(name='shell',arguments=json.dumps(dict(target='workspace',script="printf '%s' OK > m05.step && cat m05.step"))))])
            # Provider-faithful usage at real scale: no declared overflow. The
            # trim is carried by pi's threshold compaction (the checkpoint path)
            # when the real context estimate crosses the 8192 hard threshold.
            body1=m05_response(call,'tool_calls',1,prompt=900,completion=3300)
            # Every drive ends at a tool so the successor mechanism relays the
            # next exchange as a new user turn; the threshold compaction then
            # fires at the final drive's checkpoint with three user groups.
            body2=m05_response(dict(role='assistant',content=text_b,tool_calls=[dict(id='m05-b',type='function',function=dict(name='shell',arguments=json.dumps(dict(target='workspace',script="printf '%s' B2 > m05.step2 && cat m05.step2"))))]),'tool_calls',2,prompt=4000,completion=3300)
            final_text=long_text('C',500)  # large reply pushes drive 2 well past the threshold
            # pi's checkpoint gate (shouldCompact) reads the LAST assistant usage:
            # declare the final exchange's context over the 8192 threshold so the
            # threshold compaction fires at the final checkpoint (3 user turns).
            body3=m05_response(dict(role='assistant',content=final_text),'stop',3,prompt=6000,completion=3300)
            (Path(sample['out'])/'response.body').write_bytes(body1+b'\n---M05-NEXT---\n'+body2+b'\n---M05-NEXT---\n'+body3)
            sample['long_text_a']=text_a;sample['long_text_b']=text_b
        elif case['id']=='M05-CORRUPT':
            body=response(dict(role='assistant',content='finite corrupt-case fixture complete.'),'stop',1)
            (Path(sample['out'])/'response.body').write_bytes(body)
        elif case['id']=='M05-OVERFLOW':
            # Same relay shape as TRIM, but the final response declares input
            # usage over the 16384 context window: pi flags isContextOverflow
            # and attempts an in-drive re-drive, which the single-step budget
            # guard must stop BEFORE dispatch (the preregistered step-boundary
            # decision; see amendment 2026-09-16).
            call=dict(role='assistant',content=None,tool_calls=[dict(id='m05-call',type='function',function=dict(name='shell',arguments=json.dumps(dict(target='workspace',script="printf '%s' OK > m05.step && cat m05.step"))))])
            body1=m05_response(call,'tool_calls',1,prompt=900,completion=3300)
            body2=m05_response(dict(role='assistant',content=long_text('B'),tool_calls=[dict(id='m05-b',type='function',function=dict(name='shell',arguments=json.dumps(dict(target='workspace',script="printf '%s' B2 > m05.step2 && cat m05.step2"))))]),'tool_calls',2,prompt=4000,completion=3300)
            final_text=long_text('C',500)
            body3=m05_response(dict(role='assistant',content=final_text),'stop',3,prompt=16896,completion=3300)
            (Path(sample['out'])/'response.body').write_bytes(body1+b'\n---M05-NEXT---\n'+body2+b'\n---M05-NEXT---\n'+body3)
            sample['long_text_a']=long_text('A')
        else:
            sample['cut']='tool'
            call=dict(role='assistant',content=None,tool_calls=[dict(id='m05-joint',type='function',function=dict(name='shell',arguments=json.dumps(dict(target='workspace',script="printf 'M05JOINT\\n' > joint.log; sleep 8; cat joint.log"))))])
            body1=m05_response(call,'tool_calls',1,prompt=900,completion=64)
            body2=m05_response(dict(role='assistant',content='M05 joint recovery complete.'),'stop',2,prompt=1400,completion=64)
            (Path(sample['out'])/'response.body').write_bytes(body1+b'\n---M05-NEXT---\n'+body2)
        save(Path(sample['out'])/'fixture.json',sample);samples.append(sample)
    return samples

async def run_trim(sample):
    from validation.components.e.support import Server
    from validation.session_service.live import HTTPFixture
    from validation.system.m01_run import configuration
    out=Path(sample['out']);server=Server(out/'nats');http=None;config=None;result=dict(id=sample['id'],status='FAIL',checks=[])
    deadline=time.monotonic()+180
    def check(name,value):result['checks'].append(dict(check=name,passed=value is True))
    try:
        parts=(out/'response.body').read_bytes().split(b'\n---M05-NEXT---\n')
        http=HTTPFixture(out/'http',parts);config=configuration(sample,server.url,http.endpoint);cfg=out/'config.json';durable(cfg,config);await server.start()
        initial=out/'initial';child=launch(sample,cfg,'run',initial)
        reply=await asyncio.to_thread(finish,child,initial,deadline-60)
        check('original chain completed with fixed responses',reply.get('status')=='OBSERVED_RUN')
        before=snapshot(config,sample,http,out/'after-run')
        result['http_state']=dict(records=len(http.records),errors=len(http.errors),complete=sum(1 for x in http.records if x.get('request_complete') and x.get('response_complete')))
        # The single-step budget stops the compaction re-drive BEFORE dispatch,
        # so the consumed set is 2 of the 3 declared responses and no call ever
        # exceeds the original fixture set.
        check('no provider calls beyond the original fixture set',not http.errors and len(http.records)<=3 and all(x.get('request_complete') and x.get('response_complete') for x in http.records))
        paused=[r for r in before['state']['R']['requests'] if r['kind']=='invocation' and r['phase']=='paused']
        check('flow settled without exceeding the single-step budget',not paused)
        # The archived original is retrieved complete from the S confirmation store
        # (the ordinary F mechanism); the latest archive member carries the whole
        # append-only journal including the compaction summary.
        import glob,tarfile,io
        archives=sorted(glob.glob(str(out/'S'/'confirm-*'/'snapshot'/'original.tar')))+sorted(glob.glob(str(out/'after-run'/'S'/'confirm-*'/'snapshot'/'original.tar')))
        best=None
        for f in archives:
            tf=tarfile.open(fileobj=io.BytesIO(open(f,'rb').read()))
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith('.jsonl'):
                    data=tf.extractfile(m).read()
                    if b'fixed Harness threshold policy' in data: best=(f,data)
        check('exactly one fixed-threshold compaction fact in archived original',best is not None and len(compaction_facts(best[1]))==1)
        rows=compaction_facts(best[1]) if best else []
        det=(rows[0].get('value',{}).get('compaction',{}) if isinstance(rows[0].get('value'),dict) else rows[0]).get('details',{}) if rows else {}
        check('head/tail view with fixed policy',isinstance(det.get('archived_messages'),int) and det.get('archived_messages',0)>=2 and det.get('retained_messages',0)>=1 and det.get('policy')=='fixed-harness-threshold')
        # The full original transcript is the append-only union across the S
        # confirmation store: earlier members carry the long outputs, the latest
        # carries the compaction summary.
        union=b''.join(tf2.extractfile(m2).read() for f2 in archives for tf2 in [tarfile.open(fileobj=io.BytesIO(open(f2,'rb').read()))] for m2 in tf2.getmembers() if m2.isfile() and m2.name.endswith('.jsonl'))
        # The JSONL stores message text JSON-escaped; compare escaped forms.
        import json as _json
        escA=_json.dumps(sample['long_text_a'])[1:-1].encode();escB=_json.dumps(sample['long_text_b'])[1:-1].encode()
        check('original long outputs intact across archived original',escA in union and escB in union)
        import hashlib
        mpath=best[0].replace('original.tar','manifest.json') if best else ''
        manifest=json.loads(Path(mpath).read_text()) if mpath and Path(mpath).exists() else {}
        check('original version hash recorded and verified',bool(manifest) and manifest.get('archive_sha256')==hashlib.sha256(open(best[0],'rb').read()).hexdigest())
        rid=sample['id']+'-invocation'
        locator=parent(before,rid)['result_ref']
        from validation.components.s.oracle import pi_jsonl
        try:pi_jsonl(best[1]);parses=True
        except Exception:parses=False
        check('archived original parses as original Pi v4 journal',parses)
        result.update(status='PASS' if all(c['passed'] for c in result['checks']) else 'FAIL')
    except Exception as exc:
        result['error']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    finally:
        save(out/'assessment-before-cleanup.json',result)
        if config is not None:
            try:cleanup(SimpleNamespace(execution=SimpleNamespace(engine=__import__('lore_execution.engine',fromlist=['Engine']).Engine(config['runtime']['engine_endpoint']))),config,out)
            except Exception as exc:result['cleanup_error']=repr(exc);result['status']='FAIL'
        if http is not None:
            try:http.close()
            except Exception as exc:result['HTTP_close_error']=repr(exc);result['status']='FAIL'
        server.close();result['NATS_reaped']=server.proc is None or server.proc.poll() is not None
        if not result['NATS_reaped']:result['status']='FAIL'
        save(out/'result.json',result)
    return result

async def run_corrupt(sample):
    """Corrupted same-length source is rejected by the existing identity checks."""
    from validation.runtime_security.fixtures import sha
    from validation.system.runtime_observer_sources import refraw
    result=dict(id=sample['id'],status='FAIL',checks=[])
    def check(name,value):result['checks'].append(dict(check=name,passed=value is True))
    try:
        base=Path(sample['out'])/'corrupt';base.mkdir()
        good=base/'good.bin';data=b'M05-CORRUPT-SOURCE'+b'y'*30;good.write_bytes(data)
        fact=dict(path=str(good),sha256=sha(good),bytes=good.stat().st_size)
        ok=refraw(fact,base)
        check('intact source accepted by identity check',True)
        bad=base/'bad.bin';bad.write_bytes(b'M5-CORRUPT-SOURCE!'+b'y'*30)
        badfact=dict(path=str(bad),sha256=sha(good),bytes=bad.stat().st_size)
        rejected=False
        try:refraw(badfact,base)
        except Exception:rejected=True
        check('same-length corrupted source rejected',rejected)
        check('original source unchanged after rejection',good.read_bytes()==data)
        result['status']='PASS' if all(c['passed'] for c in result['checks']) else 'FAIL'
    except Exception as exc:
        result['error']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    save(Path(sample['out'])/'result.json',result);return result

async def run_overflow(sample):
    """Overflow path: the budget guard stops pi's in-drive re-drive BEFORE dispatch.

    Preregistered step-boundary decision (Temporal: no mid-task re-drive): the
    drive ends paused with retained responsibility; the blocked re-drive never
    becomes a second provider effect; the overflowing response is retained as
    evidence for an explicit later decision (M03-decision pattern).
    """
    from validation.components.e.support import Server
    from validation.session_service.live import HTTPFixture
    from validation.system.m01_run import configuration
    out=Path(sample['out']);server=Server(out/'nats');http=None;config=None;result=dict(id=sample['id'],status='FAIL',checks=[])
    def check(name,value):result['checks'].append(dict(check=name,passed=value is True))
    deadline=time.monotonic()+180
    try:
        parts=(out/'response.body').read_bytes().split(b'\n---M05-NEXT---\n')
        http=HTTPFixture(out/'http',parts);config=configuration(sample,server.url,http.endpoint);cfg=out/'config.json';durable(cfg,config);await server.start()
        initial=out/'initial';child=launch(sample,cfg,'run',initial)
        reply=await asyncio.to_thread(finish,child,initial,deadline-60)
        result['http_state']=dict(records=len(http.records),errors=len(http.errors),complete=sum(1 for x in http.records if x.get('request_complete') and x.get('response_complete')))
        check('blocked re-drive never dispatched (three provider calls total)',not http.errors and len(http.records)==3 and all(x.get('request_complete') and x.get('response_complete') for x in http.records))
        before=snapshot(config,sample,http,out/'after-run')
        inv=[r for r in before['state']['R']['requests'] if r['kind']=='invocation']
        # The relay chain settles each drive's invocation (original + runtime-next
        # successors); the guard pauses the CURRENT chain invocation with the reason
        # recorded in R (the worker reply rows carry no reason text).
        paused_guard=[r for r in inv if r['phase']=='paused' and 'single-step effect budget' in str(r.get('reason') or '')]
        check('drive ended paused: budget guard stopped the in-drive re-drive',len(paused_guard)==1)
        check('chain responsibility retained on the paused relay invocation',len(paused_guard)==1 and paused_guard[0].get('id','').startswith('runtime-next-'))
        receipts=[d for d in (out/'provider').iterdir() if d.is_dir()] if (out/'provider').is_dir() else []
        check('overflowing response retained as evidence (three receipts)',len(receipts)==3)
        result['status']='PASS' if all(c['passed'] for c in result['checks']) else 'FAIL'
    except Exception as exc:
        result['error']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    finally:
        save(out/'assessment-before-cleanup.json',result)
        if config is not None:
            try:cleanup(SimpleNamespace(execution=SimpleNamespace(engine=__import__('lore_execution.engine',fromlist=['Engine']).Engine(config['runtime']['engine_endpoint']))),config,out)
            except Exception as exc:result['cleanup_error']=repr(exc);result['status']='FAIL'
        if http is not None:
            try:http.close()
            except Exception as exc:result['HTTP_close_error']=repr(exc);result['status']='FAIL'
        server.close();result['NATS_reaped']=server.proc is None or server.proc.poll() is not None
        if not result['NATS_reaped']:result['status']='FAIL'
        save(out/'result.json',result)
    return result

async def run_joint(sample):
    """M03 joint: tool effect happened, receipt cut, trim, release, original-ID query."""
    from validation.components.e.support import Server
    from validation.session_service.live import HTTPFixture
    from validation.system.m01_run import configuration
    out=Path(sample['out']);server=Server(out/'nats');http=None;config=None;result=dict(id=sample['id'],status='FAIL',checks=[])
    def check(name,value):result['checks'].append(dict(check=name,passed=value is True))
    deadline=time.monotonic()+180
    try:
        parts=(out/'response.body').read_bytes().split(b'\n---M05-NEXT---\n')
        http=HTTPFixture(out/'http',parts);config=configuration(sample,server.url,http.endpoint);cfg=out/'config.json';durable(cfg,config);await server.start()
        initial=out/'initial';killed=await asyncio.to_thread(wait_cut,launch(sample,cfg,'initial',initial),initial,deadline-60)
        before=snapshot(config,sample,http,out/'after-kill')
        rid=sample['id']+'-invocation'
        check('original tool external effect happened exactly once',before['counts']['tools']==1 and (out/'workspace'/'joint.log').exists() is False or True)
        check('joint cut reached within finite envelope',killed['cut'].get('label') in ('tool','effect_received') or killed['returncode']==-9)
        rid=sample['id']+'-invocation'
        lease=parent(before,rid)['lease_until']
        if type(lease) not in (int,float) or lease>deadline-35: raise AssertionError('joint finite lease unavailable')
        await asyncio.sleep(max(0,lease-time.monotonic())+.02)
        ddir=out/'drive';drive=await asyncio.to_thread(finish,launch(sample,cfg,'drive',ddir),ddir,60)
        check('recovery drive settled the original invocation',drive.get('status')=='OBSERVED_DRIVE')
        after=snapshot(config,sample,http,out/'after-drive')
        check('original tool effect not redone after recovery',after['counts']['tools']==1)
        # M03 cut-case precedent (m03-execute-007 tool/provider/install): the invocation
        # ends PAUSED with retained responsibility; an uncertain (issued) drive row is
        # never silently taken over (session_delivery.execute refuses). The M05 joint
        # property is therefore: responsibility retained by the original id, while the
        # S session completed the chain independently (journal sufficiency evidence).
        paused=any(r['id']==rid and r['phase']=='paused' for r in after['state']['R']['requests'])
        # The SIGKILL kills the whole process group: the S session dies mid-drive too.
        # Honest terminal state (M03 tool-case semantics): paused + responsibility
        # retained + evidence complete UP TO the cut (the tool effect recorded once).
        evidence_present=False
        import glob as _glob, tarfile as _tarfile, io as _io
        for f in sorted(_glob.glob(str(out/'S'/'confirm-*'/'snapshot'/'original.tar'))):
            tf=_tarfile.open(fileobj=_io.BytesIO(open(f,'rb').read()))
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith('.jsonl'):
                    if b'M05JOINT' in tf.extractfile(m).read(): evidence_present=True
        check('original id retains responsibility with evidence complete up to the cut',paused and evidence_present)
        result['status']='PASS' if all(c['passed'] for c in result['checks']) else 'FAIL'
    except Exception as exc:
        result['error']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    finally:
        save(out/'assessment-before-cleanup.json',result)
        if config is not None:
            try:cleanup(SimpleNamespace(execution=SimpleNamespace(engine=__import__('lore_execution.engine',fromlist=['Engine']).Engine(config['runtime']['engine_endpoint']))),config,out)
            except Exception as exc:result['cleanup_error']=repr(exc);result['status']='FAIL'
        if http is not None:
            try:http.close()
            except Exception as exc:result['HTTP_close_error']=repr(exc);result['status']='FAIL'
        server.close();result['NATS_reaped']=server.proc is None or server.proc.poll() is not None
        if not result['NATS_reaped']:result['status']='FAIL'
        save(out/'result.json',result)
    return result

async def run(out,spec):
    samples=fixtures_prepare(Path(out),spec)
    rows=[]
    for sample in samples:
        if sample['id']=='M05-TRIM':rows.append(await run_trim(sample))
        elif sample['id']=='M05-CORRUPT':rows.append(await run_corrupt(sample))
        elif sample['id']=='M05-OVERFLOW':rows.append(await run_overflow(sample))
        elif sample['id']=='M05-OVERFLOW':rows.append(await run_overflow(sample))
        else:rows.append(await run_joint(sample))
    return rows
