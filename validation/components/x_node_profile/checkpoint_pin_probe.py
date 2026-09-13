"""One existing checkpoint query, actual open FD, concurrent original release; no transport state."""
from pathlib import Path
import concurrent.futures,copy,importlib,os,threading
from artifacts import file_fact,require,save

def run(e,old,receipt):
    module=e.rpc.argv[e.rpc.argv.index('-m')+1]
    candidate=importlib.import_module(module)
    entered=threading.Event();proceed=threading.Event();observed={}
    def hook(label,binding):
        if label!='checkpoint_read_open_before_close':return
        observed['binding']=copy.deepcopy(binding);entered.set()
        require(proceed.wait(5),'original read pin release deadline')
    e.rpc.stop()  # Paused object remains; transfer the original single journal-owner role.
    store=candidate.ExecutionStore(e.fx.state,checkpoint=hook,trusted_config=str(e.fx.config_path),trusted_config_sha256=file_fact(e.fx.config_path)[0]['sha256'])
    def start(fn):
        result=concurrent.futures.Future()
        def target():
            try:result.set_result(fn())
            except BaseException as exc:result.set_exception(exc)
        thread=threading.Thread(target=target,daemon=True);thread.start();return result,thread
    def state():return{str(p.relative_to(e.fx.state)):file_fact(p)[0]['sha256']for p in e.fx.state.rglob('*')if p.is_file()}
    before=state();fact,raw=file_fact(old['ref']['path']);old_stat=Path(old['ref']['path']).stat()
    query,qt=start(lambda:store.query_checkpoint(e.binding['execution_id'],e.fx.authority,old['ref']))
    try:
        require(entered.wait(3)and not query.done(),'same original checkpoint query did not hold real read boundary')
        require(observed['binding']['execution_id']==e.binding['execution_id']and observed['binding']['object_generation']==e.binding['object_generation'],'read hook changed original execution')
        fds=[]
        for p in Path('/proc/self/fd').iterdir():
            try:
                st=p.stat()
                if (st.st_dev,st.st_ino)==(old_stat.st_dev,old_stat.st_ino):
                    require(os.pread(int(p.name),len(raw)+1,0)==raw,'actual held FD bytes differ');fds.append({'fd':p.name,'dev':st.st_dev,'ino':st.st_ino})
            except FileNotFoundError:pass
        require(fds,'no real original archive FD held by candidate query')
        release,rt=start(lambda:store.release_checkpoint(e.binding['execution_id'],e.fx.authority,'read-pin-rejected-release',old['ref'],receipt))
        try:release.result(timeout=2)
        except Exception as exc:require(getattr(exc,'code',None)=='INCOMPLETE_OBSERVATION','release during real read pin did not reject precisely')
        else:raise ValueError('release reclaimed archive during original read')
        require(file_fact(old['ref']['path'])[0]==fact and Path(old['ref']['path']).read_bytes()==raw and state()==before,'read-pinned rejection changed original inode/bytes/slot')
        proceed.set();returned=query.result(timeout=3)
        require(returned['checkpoint']['original_full_ref']==old['ref'],'same original query returned another checkpoint')
        require(state()==before,'read-only original query rewrote authoritative state')
        save(e.out/'actual-checkpoint-read-pin.json',{'candidate_module':module,'same_store':True,'same_query_returned':returned,'actual_open_fds':fds,'original':fact,'state_before':before,'state_after':state(),'rejection':'INCOMPLETE_OBSERVATION'})
    finally:
        proceed.set();qt.join(timeout=3)
        fd=getattr(store.journal,'owner_fd',None)
        if fd is not None:os.close(fd);store.journal.owner_fd=None
        e.rpc.start()
