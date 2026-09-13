"""Actual SUT subprocess. A ready fault marker is fsynced before the parent SIGKILL."""
import asyncio
import json
import os
from pathlib import Path
import sys
from fixture import sut_modules,AUTHORITY,reference_checker
from support import save
async def main(config):
    em,rm=sut_modules();root=Path(config["root"])
    async def checkpoint(label,record):
        if label==config.get("cut"):
            path=Path(config["marker"])
            with path.open("x") as output:
                json.dump({"label":label,"record":record,"pid":os.getpid()},output);output.flush();os.fsync(output.fileno())
            await asyncio.Event().wait()
    store=rm.ControlStore(config["db"],authority=AUTHORITY,reference_checker=reference_checker(root,config["observer_url"]))
    service=em.EventService(config["server_url"],store,config["profile"],checkpoint=checkpoint)
    try:
        await service.start()
        if config["action"]=="submit":
            result=await service.submit(**config["args"])
        elif config["action"]=="query":
            result=await service.query(**config["args"])
        elif config["action"]=="lookup":
            result=await service.lookup_input(**config["args"])
        elif config["action"]=="prepare":
            result=await service.prepare_input(**config["args"],input_context=config["input_context"])
        else:raise ValueError("unknown worker action")
        save(config["reply"],{"result":result})
        print(json.dumps({"completed":True}))
    finally:await service.close();store.close()
if __name__=="__main__":
    config=json.loads(Path(sys.argv[1]).read_text())
    asyncio.run(asyncio.wait_for(main(config),15))
