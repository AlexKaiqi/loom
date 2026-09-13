"""Candidate SDK execution; invocation roles split across fresh Python processes."""
import asyncio,json,sys,dataclasses
from agentfs_sdk import AgentFS,AgentFSOptions
async def main():
 mode,path=sys.argv[1:3]
 async with await AgentFS.open(AgentFSOptions(path=path)) as a:
  if mode=="seed":
   for name,value in {"/surface/template":"T0","/workspace/untracked-block":"B0","/workspace/artifact":"REPORT0"}.items(): await a.fs.write_file(name,value)
   await a.kv.set("input_version","R0")
  elif mode=="first-edit": await a.fs.write_file("/surface/template","T1")
  elif mode=="second-edit":
   await a.fs.write_file("/workspace/untracked-block","B1")
   await a.fs.write_file("/workspace/artifact","REPORT1")
   await a.kv.set("input_version","R1")
  elif mode=="record-effect":
   await a.tools.record("external-effect",started_at=1,completed_at=2,parameters={"operation":"op1"},result={"effect_count":1})
  elif mode!="inspect": raise ValueError(mode)
  values={name:await a.fs.read_file(name) for name in ["/surface/template","/workspace/untracked-block","/workspace/artifact"]}
  calls=await a.tools.get_by_name("external-effect")
  print(json.dumps({"mode":mode,"database":path,"values":values,"input_version":await a.kv.get("input_version"),"tool_records":[dataclasses.asdict(x) for x in calls]},sort_keys=True))
asyncio.run(main())
