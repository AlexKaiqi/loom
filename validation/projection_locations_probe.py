"""Two finite external-projection checks; no Engine/provider or tool execution."""
import argparse,copy,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NODE="/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node"
LOADER=ROOT/"research/repos/pi/node_modules/tsx/dist/loader.mjs"
SOURCE=("harnesses/minimal/projection.mts","lore_session/node/common.mts",
        "validation/history_input_projection.mts","validation/projection_locations_probe.py",
        "design/g4/projection-locations-001/contract.md","design/g4/projection-locations-001/history.json")
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n")
def main():
 p=argparse.ArgumentParser();p.add_argument("--batch",required=True);a=p.parse_args()
 if not a.batch or any(not(c.isalnum() or c in "-_") for c in a.batch):p.error("fresh batch required")
 out=ROOT/"validation/projection-locations-evidence"/a.batch;out.mkdir(parents=True,exist_ok=False)
 source=out/"source";hashes={n:digest(ROOT/n) for n in SOURCE}
 for n in SOURCE:
  target=source/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,target)
 save(out/"sources.json",hashes)
 fixture=out/"fixture";fixture.mkdir();surface=fixture/"surface";surface.mkdir()
 (surface/"template.md").write_text("LOCATION_GOAL {{notes.md}}")
 (surface/"notes.md").write_text("ORIGINAL_NOTES")
 (fixture/"events.jsonl").write_text("ORIGINAL_EVENT")
 (fixture/"feedback.txt").write_text("ORIGINAL_FEEDBACK")
 history=json.loads((source/"design/g4/projection-locations-001/history.json").read_text())
 values=[]
 for name,runtime,workspace in (("PLOC01","/input/surface","/workspace"),
   ("PLOC02","/private/harness-source/runtime-label","/private/harness-source/workspace-label")):
  values.append(dict(name=name,input=dict(paths=dict(surface=str(surface),events=str(fixture/"events.jsonl"),
    feedback=str(fixture/"feedback.txt"),runtime=runtime,workspace=workspace),history_views=history)))
 save(out/"input.json",values)
 command=[NODE,"--import",str(LOADER),str(source/"validation/history_input_projection.mts"),str(out/"input.json"),str(out/"actual.json")]
 run=subprocess.run(command,capture_output=True,timeout=20,env={"PATH":str(Path(NODE).parent)+":/usr/bin:/bin","LANG":"C.UTF-8"})
 (out/"stdout").write_bytes(run.stdout);(out/"stderr").write_bytes(run.stderr)
 save(out/"process.json",dict(argv=command,returncode=run.returncode))
 actual=json.loads((out/"actual.json").read_text()) if (out/"actual.json").exists() else []
 checks=[]
 for index,row in enumerate(values):
  current=actual[index] if index<len(actual) else {}
  blocks=json.loads(current["text"])["context_blocks"] if current.get("ok") else []
  text="\n".join(blocks);catalog=[json.loads(x)["history_views"] for x in blocks if x.startswith("{") and "history_views" in x]
  checks.append(dict(id=row["name"],checks={
   "actual_projection_process":run.returncode==0 and current.get("ok") is True,
   "both_explicit_work_cwds":"runtime: cwd=/work" in text and "workspace: cwd=/work" in text,
   "separate_environments_and_relative_files":"separate" in text and "relative" in text,
   "input_sources_are_not_working_directories":"read-only input" in text and "not Shell working directories" in text,
   "history_runtime_only_readonly":"/input/history/" in text and "runtime shell only" in text and "Read-only history" in text,
   "no_metadata_misdeclared_as_shell_cwd":"runtime=/input/surface" not in text and "workspace=/workspace" not in text and "/private/harness-source/" not in text,
   "original_blocks_catalog_preserved":all(x in text for x in ("LOCATION_GOAL","ORIGINAL_NOTES","ORIGINAL_EVENT","ORIGINAL_FEEDBACK")) and catalog==[history],
   "metadata_labels_do_not_change_shell_instructions":index==0 or current.get("text")==actual[0].get("text")}))
 same=all(digest(ROOT/n)==h and digest(source/n)==h for n,h in hashes.items())
 result=dict(status="PASS" if len(checks)==2 and all(all(x["checks"].values()) for x in checks) and same else "FAIL",
    cases=checks,source_unchanged=same,scope="Actual copied Node projection only; no model, Engine, tools or expanded permissions")
 save(out/"result.json",result);print(json.dumps(result));return 0 if result["status"]=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())
