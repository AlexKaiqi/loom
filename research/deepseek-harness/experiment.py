from pathlib import Path
import datetime,hashlib,json,subprocess,sys,shutil
ROOT=Path(__file__).resolve().parents[2];D=ROOT/"research/deepseek-harness";REPO=ROOT/"research/repos/deepseek-harness"
B=D/"evidence"/sys.argv[1];B.mkdir(parents=True,exist_ok=False);W=B/"workspace";W.mkdir()
node="/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sources=[REPO/x for x in ["packages/core/session/src/repair.ts","packages/core/agent-loop/src/index.ts","packages/core/agent-loop/src/agent.ts","packages/session/session-persistence-jsonl/src/storage.ts","packages/session/session-persistence-jsonl/src/lease.ts","native/system/packages/linux-x64/bin/glibc/system.node"]]
r={"started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"protocol_sha256":sha(D/"protocol.json"),"sources":{str(p.relative_to(ROOT)):sha(p) for p in sources},"commands":[]}
for x in ["protocol.json","experiment.py","experiment.spec.ts","test.config.mts"]:shutil.copy2(D/x,B/x)
def run(phase):
 env={"PATH":str(Path(node).parent)+":/usr/bin:/bin","LANG":"C.UTF-8","LORE_RESEARCH_WORKSPACE":str(W),"LORE_RESEARCH_PHASE":phase,"CI":"1"}
 cmd=[node,str(REPO/"node_modules/vitest/vitest.mjs"),"run","--config",str(D/"test.config.mts"),"--reporter=json","--outputFile",str(B/(phase+"-vitest.json"))]
 p=subprocess.run(cmd,cwd=REPO,env=env,text=True,capture_output=True,timeout=60)
 (B/(phase+"-stdout.txt")).write_text(p.stdout);(B/(phase+"-stderr.txt")).write_text(p.stderr)
 r["commands"].append({"phase":phase,"command":cmd,"cwd":str(REPO),"exit_code":p.returncode})
 if (W/(phase+"-raw.json")).exists():shutil.copy2(W/(phase+"-raw.json"),B/(phase+"-raw.json"))
 target=B/(phase+"-physical");target.mkdir()
 for path in (W/"sessions").rglob("*.jsonl"):
  dest=target/path.relative_to(W/"sessions");dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
 if p.returncode:raise RuntimeError(phase+" candidate phase failed")
 return json.loads((W/(phase+"-raw.json")).read_text())
def text(x):return json.dumps(x,ensure_ascii=False)
try:
 normal=run("normal");resume=run("resume");seed=run("seed")
 for session_id,fragment in [("torn",'{"type":"assistant/incomplete"'),("corrupt",'{"invalid_complete":true}\n')]:
  files=list((W/"sessions"/"_no-cwd"/session_id).glob("*.jsonl"))
  if len(files)!=1:raise RuntimeError("expected exactly1 physical log for "+session_id)
  with files[0].open("a") as f:f.write(fragment)
 repair=run("repair")
 prefix=normal["events"];sessions=repair["sessions"]
 checks={"normal_actual_loop":len(normal["requests"])==2 and "REAL_TOOL_OBSERVATION_雪" in text(normal["events"]) and "FIXED_FINAL_雪" in text(normal["events"]),
 "target_effect_once":(W/"effects.txt").read_text()=="effect\n",
 "live_writer_rejects":normal["conflict"]["rejected"] and "owned" in normal["conflict"]["message"],
 "resume_original_log":resume["before"]["id"]=="normal" and resume["before"]["requests"]==0 and resume["before"]["events"][:len(prefix)]==prefix and resume["before"]["messages"]==normal["messages"],
 "external_series_extension":len(resume["requests"])==1 and any(e["type"]=="request/header" and (e["data"].get("reason")=="series" or e["data"].get("startsSeries") is True) for e in resume["events"]),
 "not_started_classified":"TOOL_NOT_STARTED" in text(sessions["not-started"]) and "TOOL_OUTCOME_UNKNOWN" not in text(sessions["not-started"]),
 "unknown_classified":"TOOL_OUTCOME_UNKNOWN" in text(sessions["unknown"]) and any(e["type"]=="tool/result" and e.get("sourceEventSeqs")==[3] for e in sessions["unknown"]["events"]),
 "repair_preserves_prefix":all(sessions[k]["events"][:len(seed["prefixes"][k])]==seed["prefixes"][k] for k in ["not-started","unknown","torn"]),
 "repair_no_model_call":len(repair["requests"])==0,
 "torn_tail_recovered":"TOOL_OUTCOME_UNKNOWN" in text(sessions["torn"]),
 "complete_corruption_rejected":"error" in sessions["corrupt"],
 "source_unchanged":all(sha(p)==r["sources"][str(p.relative_to(ROOT))] for p in sources)}
 r["checks"]=checks;r["status"]="OBSERVED" if all(checks.values()) else "INVESTIGATE"
except Exception as e:r["status"]="INVALID";r["error"]=repr(e)
r["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
(B/"run.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(r,ensure_ascii=False));sys.exit(0 if r["status"]=="OBSERVED" else 1)
