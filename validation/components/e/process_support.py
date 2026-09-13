import asyncio
import os
from pathlib import Path
import signal
import time
from support import PYTHON,ROOT,save
async def spawn_worker(fixture,label,config):
    config=dict(config);config["reply"]=str(fixture.root/(label+"-reply.json"))
    path=fixture.root/(label+"-request.json");save(path,config)
    output=(fixture.root/(label+"-stdout.log")).open("wb")
    error=(fixture.root/(label+"-stderr.log")).open("wb")
    process=await asyncio.create_subprocess_exec(str(PYTHON),str(ROOT/"validation/components/e/worker.py"),str(path),stdout=output,stderr=error,env=os.environ.copy())
    return process,output,error,config
async def wait_marker(process,marker,seconds=8):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if marker.exists():return
        if process.returncode is not None:raise AssertionError("SUT exited before actual requested cut")
        await asyncio.sleep(.02)
    raise TimeoutError("actual SUT checkpoint not reached")
async def stop_worker(items,kill=True):
    process,output,error,config=items
    try:
        if kill and process.returncode is None:process.send_signal(signal.SIGKILL)
        rc=await asyncio.wait_for(process.wait(),3)
        save(Path(config["reply"]).with_suffix(".exit.json"),{"pid":process.pid,"returncode":rc,"requested_SIGKILL":kill})
        if kill and rc!=-9:raise AssertionError("required SIGKILL did not occur")
        if not kill and rc!=0:raise AssertionError("SUT worker failed; see stderr")
        return config
    finally:
        if process.returncode is None:process.kill();await process.wait()
        output.close();error.close()
