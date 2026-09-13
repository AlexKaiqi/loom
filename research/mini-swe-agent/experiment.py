from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/"research/mini-swe-agent"
BATCH=D/"evidence"/sys.argv[1]
BATCH.mkdir(parents=True,exist_ok=False)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
sources=[ROOT/"research/repos/mini-swe-agent"/p for p in (
"src/minisweagent/agents/default.py","src/minisweagent/environments/local.py","src/minisweagent/models/test_models.py")]
manifest={"started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"protocol_sha256":sha(D/"protocol.json"),
"script_sha256":{p.name:sha(p) for p in [D/"experiment.py",D/"worker.py"]},"source_sha256":{str(p.relative_to(ROOT)):sha(p) for p in sources},
"python":sys.version,"records":[]}
def observed(w):
    trajectory=w/"trajectory.json"
    return {"effects":(w/"effects.txt").read_text().splitlines() if (w/"effects.txt").exists() else [],
    "queries":[json.loads(x) for x in (w/"queries.jsonl").read_text().splitlines()] if (w/"queries.jsonl").exists() else [],
    "trajectory":json.loads(trajectory.read_text()) if trajectory.exists() else None}
def run(name,mode,workspace):
    workspace.mkdir(parents=True,exist_ok=True)
    config=workspace/"empty-config";config.mkdir(exist_ok=True)
    env={"PATH":str(Path(sys.executable).parent)+":/usr/bin:/bin","LANG":"C.UTF-8",
    "PYTHONPATH":str(ROOT/"research/repos/mini-swe-agent/src"),"MSWEA_GLOBAL_CONFIG_DIR":str(config),"MSWEA_SILENT_STARTUP":"1"}
    command=[sys.executable,str(D/"worker.py"),mode,str(workspace)]
    p=subprocess.run(command,cwd=workspace,env=env,text=True,capture_output=True,timeout=15)
    (BATCH/(name+"-stdout.txt")).write_text(p.stdout)
    (BATCH/(name+"-stderr.txt")).write_text(p.stderr)
    result={"name":name,"command":command,"returncode":p.returncode,"observed":observed(workspace)}
    (BATCH/(name+"-raw.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    manifest["records"].append({"name":name,"returncode":p.returncode})
    return result
def normal_ok(r,effects,queries,submission):
    o=r["observed"];t=o["trajectory"]
    return r["returncode"]==0 and len(o["effects"])==effects and len(o["queries"])==queries and t is not None and t["info"]["submission"]==submission and any("OBSERVED_UTF8_雪" in str(m["content"]) for m in t["messages"])
try:
    a=run("normal","normal",BATCH/"normal")
    b=run("external","external",BATCH/"external")
    c=run("crash","crash",BATCH/"crash")
    before=c["observed"]
    retry=run("retry","normal",BATCH/"crash")
    mutant=json.loads(json.dumps(a));mutant["observed"]["effects"].append("unreported effect")
    checks={"normal_actual_loop":normal_ok(a,1,2,"done"),"external_stopping_policy":normal_ok(b,1,1,"policy-stop"),
    "crash_effect_without_saved_trajectory":c["returncode"]==-9 and len(before["effects"])==1 and len(before["queries"])==1 and before["trajectory"] is None,
    "retry_is_reexecution":normal_ok(retry,2,3,"done"),"observer_rejects_extra_effect":not normal_ok(mutant,1,2,"done"),
    "upstream_unchanged":all(sha(p)==manifest["source_sha256"][str(p.relative_to(ROOT))] for p in sources)}
    manifest["checks"]=checks
    manifest["finding"]="DEFAULT_SAVE_BOUNDARY_GAP" if checks["crash_effect_without_saved_trajectory"] else "UNEXPECTED"
    manifest["status"]="OBSERVED" if all(checks.values()) else "INVESTIGATE"
except Exception as e:
    manifest["status"]="INVALID";manifest["error"]=repr(e)
finally:
    manifest["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (BATCH/"run.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(manifest,ensure_ascii=False))
sys.exit(0 if manifest["status"]=="OBSERVED" else 1)
