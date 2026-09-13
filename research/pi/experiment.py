from pathlib import Path
import datetime,hashlib,json,subprocess,sys,shutil
ROOT=Path(__file__).resolve().parents[2];D=ROOT/"research/pi";B=D/"evidence"/sys.argv[1];B.mkdir(parents=True,exist_ok=False)
node="/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node"
tsx=ROOT/"research/repos/pi/node_modules/tsx/dist/loader.mjs"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sources=[ROOT/"research/repos/pi"/x for x in ["packages/agent/src/harness/runtime/lane.ts","packages/agent/src/harness/runtime/harness.ts","packages/agent/src/harness/runtime/restore.ts","packages/agent/src/harness/runtime/drive/tools.ts","packages/agent/src/harness/session/jsonl/storage.ts"]]
r={"started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"protocol_sha256":sha(D/"protocol.json"),"sources":{str(p.relative_to(ROOT)):sha(p) for p in sources},"commands":[]}
for x in ["protocol.json","experiment.py","worker.mts","tsconfig.json"]:shutil.copy2(D/x,B/x)
def lines(p):return p.read_text().splitlines() if p.exists() else []
def run(name,mode,w,flavor="normal",crash=False):
 w.mkdir(exist_ok=True)
 env={"PATH":str(Path(node).parent)+":/usr/bin:/bin","LANG":"C.UTF-8","TSX_TSCONFIG_PATH":str(D/"tsconfig.json")}
 cmd=[node,"--import",str(tsx),str(D/"worker.mts"),mode,str(w),flavor]
 p=subprocess.run(cmd,cwd=w,env=env,text=True,capture_output=True,timeout=30)
 (B/(name+"-stdout.json")).write_text(p.stdout);(B/(name+"-stderr.txt")).write_text(p.stderr)
 record={"name":name,"command":cmd,"exit_code":p.returncode,"queries":lines(w/"queries.jsonl"),"effects":lines(w/"effects.txt")}
 for f in (w/"sessions").rglob("*.jsonl"):
  target=B/(name+"-session.jsonl");shutil.copy2(f,target);record["session_snapshot"]=target.name
 (B/(name+"-target.json")).write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
 r["commands"].append(record)
 if crash:
  if p.returncode!=-9:raise RuntimeError(name+" did not reach kill boundary: "+str(p.returncode))
  return record
 if p.returncode:raise RuntimeError(name+" failed")
 return json.loads(p.stdout)
try:
 w=B/"normal";accept=run("accept","create",w);inspect=run("inspect","inspect",w)
 driven=run("drive","drive",w);queried=run("query-result","inspect",w)
 policy=run("external-policy","policy",B/"policy")
 duplicate=[]
 for flavor in ["same","changed"]:
  copied=B/("duplicate-"+flavor);shutil.copytree(w,copied)
  m=json.loads((copied/"metadata.json").read_text());m["path"]=str(copied/Path(m["path"]).relative_to(w));(copied/"metadata.json").write_text(json.dumps(m))
  duplicate.append(run("reaccept-"+flavor,"reaccept",copied,flavor))
 crashes={}
 for flavor in ["unsafe","safe"]:
  folder=B/flavor
  killed=run(flavor+"-crash","crash",folder,flavor,True)
  opened=run(flavor+"-inspect","inspect",folder,flavor)
  resumed=run(flavor+"-resume","drive",folder,flavor)
  crashes[flavor]={"killed":killed,"opened":opened,"resumed":resumed,"effects":lines(folder/"effects.txt"),"queries":lines(folder/"queries.jsonl")}
 def texts(x):return json.dumps(x["entries"],ensure_ascii=False)
 unsafe=crashes["unsafe"];safe=crashes["safe"]
 checks={"accept_without_effect":accept["admission"]["ok"] and accept["providerCalls"]==0 and accept["result"] is None,
 "restored_open_identity":inspect["before"]["current"]["id"]=="fixture-operation" and inspect["providerCalls"]==0 and inspect["result"] is None,
 "original_result_query":driven["result"] is not None and queried["result"]==driven["result"] and queried["providerCalls"]==0 and "FIXED_ANSWER_雪" in texts(queried),
 "external_policy":policy["providerCalls"]==2 and "EXTERNAL_POLICY_CONTINUE" in texts(policy) and "POLICY_SECOND_雪" in texts(policy),
 "unsafe_no_replay":len(unsafe["effects"])==1 and unsafe["opened"]["providerCalls"]==0 and "external outcome is unknown" in texts(unsafe["resumed"]) and "fixed-call" in texts(unsafe["resumed"]),
 "safe_label_failure_control":len(safe["effects"])==2,
 "source_unchanged":all(sha(p)==r["sources"][str(p.relative_to(ROOT))] for p in sources)}
 r["checks"]=checks
 r["duplicate_identity"]=[{"flavor":x["flavor"],"admission":x.get("admission"),"admissionError":x.get("admissionError"),"oldResult":x.get("result"),"current":x.get("after")} for x in duplicate]
 r["status"]="OBSERVED" if all(checks.values()) else "INVESTIGATE"
except Exception as e:r["status"]="INVALID";r["error"]=repr(e)
r["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
(B/"run.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:v for k,v in r.items() if k!="commands"},ensure_ascii=False));sys.exit(0 if r["status"]=="OBSERVED" else 1)
