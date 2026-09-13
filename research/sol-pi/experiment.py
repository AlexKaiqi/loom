from pathlib import Path
import datetime,hashlib,json,subprocess,sys,shutil
ROOT=Path(__file__).resolve().parents[2];D=ROOT/"research/sol-pi";B=D/"evidence"/sys.argv[1]
B.mkdir(parents=True,exist_ok=False);W=B/"workspace";W.mkdir()
node="/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node"
def sha(x):return hashlib.sha256(x).hexdigest()
original="".join("MIDDLE_ORACLE_雪\n" if i==600 else f"row-{i:04d} 雪 evidence fixture\n" for i in range(1200))
sources=[ROOT/"research/repos/sol-pi"/x for x in ["src/sol-pi/extensions/observation-pack/index.ts","src/sol-pi/extensions/observation-pack/observation.ts","tests/helpers.ts"]]
r={"started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"protocol_sha256":sha((D/"protocol.json").read_bytes()),"source_sha256":{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sources},"commands":[]}
for x in ["protocol.json","worker.mts","experiment.py"]:shutil.copy2(D/x,B/x)
def run(name,mode):
 env={"PATH":str(Path(node).parent)+":/usr/bin:/bin","LANG":"C.UTF-8","PI_CODING_AGENT_DIR":str(W/"empty-config")}
 cmd=[node,str(D/"worker.mts"),mode,str(W)]
 p=subprocess.run(cmd,cwd=W,env=env,text=True,capture_output=True,timeout=30)
 (B/(name+"-stdout.json")).write_text(p.stdout);(B/(name+"-stderr.txt")).write_text(p.stderr)
 r["commands"].append({"name":name,"command":cmd,"cwd":str(W),"exit_code":p.returncode})
 if p.returncode:raise RuntimeError(name+" worker failed")
 return json.loads(p.stdout)
def full(t):return next(m["content"][0]["text"] for m in t if m["role"]=="toolResult")
def recalled(x):return "".join(p["content"][0]["text"].split("\n",2)[2] for p in x["pages"])
try:
 created=run("create","create")
 raw_path=Path(created["sessionFile"]);raw_initial=raw_path.read_bytes();(B/"session-before.jsonl").write_bytes(raw_initial)
 blob=W/"sessions"/"sol-pi"/created["sessionId"]/"observation-pack"/"objects"/(created["id"]+".txt")
 archived=blob.read_bytes();(B/"original-tool-output.txt").write_bytes(original.encode())
 recall=run("restart-recall","recall")
 changed=bytearray(archived);changed[0]=ord("X") if changed[0]!=ord("X") else ord("Y");blob.write_bytes(changed)
 corruption=run("corrupted-recall","recall")
 projection=run("corrupted-project","project")
 missing=run("missing","missing")
 p=created["projections"];third=full(p[2])
 checks={"normal_first_two_full":full(p[0])==original and full(p[1])==original,
 "projection_only":len(third.encode())<len(original.encode()) and created["id"] in third and "MIDDLE_ORACLE" not in third and raw_initial==raw_path.read_bytes(),
 "archive_exact":archived==original.encode(),"fresh_process_recall_exact":recalled(recall)==original and recall["sessionId"]==created["sessionId"],
 "corrupt_projection_retains_original":all(full(p)==original for p in projection["projections"]) and "hash mismatch" in (B/"corrupted-project-stderr.txt").read_text(),
 "unknown_id_rejects":"error" in missing,"observer_rejects_corrupt_hash":sha(changed)!=sha(original.encode()),
 "source_unchanged":all(sha(p.read_bytes())==r["source_sha256"][str(p.relative_to(ROOT))] for p in sources)}
 integrity_rejects="error" in corruption
 r["checks"]=checks;r["recall_integrity"]={"rejected":integrity_rejects,"returned_sha256":sha(recalled(corruption).encode()) if "pages" in corruption else None,"expected_sha256":sha(original.encode())}
 r["finding"]="RECALL_INTEGRITY_GAP" if not integrity_rejects and recalled(corruption).encode()==bytes(changed) else "RECALL_REJECTED_OR_OTHER"
 r["status"]="OBSERVED" if all(checks.values()) else "INVESTIGATE"
 (B/"session-after.jsonl").write_bytes(raw_path.read_bytes())
except Exception as e:r["status"]="INVALID";r["error"]=repr(e)
r["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
(B/"run.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(r,ensure_ascii=False));sys.exit(0 if r["status"]=="OBSERVED" else 1)
