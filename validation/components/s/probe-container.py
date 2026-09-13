"""Restricted container load probe, not product execution or durable Session bridge."""
from pathlib import Path
import subprocess,json,hashlib,datetime,sys
from oracle import pi_jsonl
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
out=HERE/"evidence"/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
image="python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"
node=Path("/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64")
result={"scope":"G3_RESTRICTED_LOAD_PREPARATION_ONLY","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"inputs":{},"runs":[],"checks":{},"errors":[]}
for p in [ROOT/"design/g3/s/container-preparation-protocol.json",HERE/"probe-container.py",HERE/"probe-public.mts",ROOT/"research/pi/tsconfig.json",ROOT/"research/docker-linux/seccomp.json"]:
 result["inputs"][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
wrapper="""from pathlib import Path
import subprocess,json,sys,os
mode=sys.argv[1]
env={"PATH":"/opt/node/bin:/usr/bin:/bin","HOME":"/work","LANG":"C.UTF-8","TSX_TSCONFIG_PATH":"/path/to/loom/research/pi/tsconfig.json"}
p=subprocess.run(["/opt/node/bin/node","--import","/path/to/loom/research/repos/pi/node_modules/tsx/dist/loader.mjs","/path/to/loom/validation/components/s/probe-public.mts",mode,"/work"],env=env,text=True,capture_output=True,timeout=30)
data={"exit":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"node":subprocess.run(["/opt/node/bin/node","--version"],capture_output=True,text=True).stdout,"ldd":subprocess.run(["ldd","/opt/node/bin/node"],capture_output=True,text=True).stdout,"files":{str(q.relative_to("/work")):q.read_text() for q in Path("/work").glob("*.jsonl")}}
print(json.dumps(data));sys.exit(p.returncode)
"""
def command(argv,**kwargs):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=45,**kwargs)
 return p
try:
 for mode in ["single","multi"]:
  argv=["docker","create","--network","none","--read-only","--cap-drop","ALL","--security-opt","no-new-privileges","--security-opt","seccomp="+str(ROOT/"research/docker-linux/seccomp.json"),"--user","1000:1000","--memory","512m","--memory-swap","512m","--pids-limit","64","--cpus","1","--shm-size","1m","--tmpfs","/tmp:rw,nosuid,nodev,size=64m,nr_inodes=4096,mode=1777","--tmpfs","/work:rw,nosuid,nodev,size=16m,nr_inodes=512,uid=1000,gid=1000,mode=0700"]
  for source,target in [(node,"/opt/node"),(ROOT/"research/repos/pi","/path/to/loom/research/repos/pi"),(ROOT/"research/pi/tsconfig.json","/path/to/loom/research/pi/tsconfig.json"),(HERE/"probe-public.mts","/path/to/loom/validation/components/s/probe-public.mts")]:
   argv+=["--mount",f"type=bind,src={source},dst={target},readonly"]
  argv +=[image,"python","-c",wrapper,mode]
  created=command(argv)
  if created.returncode:raise RuntimeError(created.stderr)
  cid=created.stdout.strip();entry={"mode":mode,"container_id":cid,"create_argv":argv};result["runs"].append(entry)
  try:
   before=command(["docker","inspect",cid]);(out/(mode+".inspect-before.json")).write_text(before.stdout)
   ran=command(["docker","start","--attach",cid]);(out/(mode+".stdout")).write_text(ran.stdout);(out/(mode+".stderr")).write_text(ran.stderr)
   after=command(["docker","inspect",cid]);(out/(mode+".inspect-after.json")).write_text(after.stdout)
   entry["cli_exit"]=ran.returncode
   data=json.loads(ran.stdout);entry["worker_exit"]=data["exit"];entry["node"]=data["node"];(out/(mode+".ldd.txt")).write_text(data["ldd"])
   final=pi_jsonl(data["files"][mode+"-final.jsonl"].encode())
   (out/(mode+".original.jsonl")).write_text(data["files"][mode+"-final.jsonl"])
   for key in ["provider.jsonl","effects.jsonl"]:(out/(mode+"."+key)).write_text(data["files"].get(key,""))
   observation=json.loads(data["stdout"]);entry["observation"]=observation
   provider=len(data["files"].get("provider.jsonl","").splitlines());effects=len(data["files"].get("effects.jsonl","").splitlines())
   result["checks"][mode+"_restricted_load"]=ran.returncode==0 and data["exit"]==0 and data["node"].strip()=="v24.21.0" and provider==1 and effects==(1 if mode=="single" else 0) and observation["result"] is not None and final["counts"]["assistant"]==1
  finally:
   removed=command(["docker","rm","--force",cid]);entry["cleanup_exit"]=removed.returncode
   if removed.returncode:raise RuntimeError("container cleanup failed "+cid)
 if not all(result["checks"].values()):raise AssertionError("restricted load prediction failed")
except Exception as error:result["errors"].append(repr(error))
result["status"]="OBSERVED_PREPARATION" if not result["errors"] else "INVESTIGATE"
(out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"status":result["status"],"checks":result["checks"],"errors":result["errors"]}))
raise SystemExit(0 if not result["errors"] else 1)
