from pathlib import Path
import subprocess,os,json,sys,shutil,hashlib,platform,datetime
base=Path(__file__).resolve().parent;out=base/"evidence"/sys.argv[1];out.mkdir(parents=True,exist_ok=False);fixture=out/"fixture";fixture.mkdir();home=fixture/"home";home.mkdir();db=fixture/"current.db"
env={"PATH":"/usr/bin:/bin","HOME":str(home),"LANG":"C.UTF-8"}; records=[]
def run(mode,path):
 cmd=[str(base/".venv/bin/python"),str(base/"experiment.py"),mode,str(path)]
 r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=45);n=len(records);(out/f"{n}.stdout.txt").write_text(r.stdout);(out/f"{n}.stderr.txt").write_text(r.stderr);records.append({"command":cmd,"exit_code":r.returncode});
 if r.returncode: raise RuntimeError("candidate execution failed; raw output retained")
 return json.loads(r.stdout)
try:
 seed=run("seed",db);shutil.copy2(db,fixture/"v0.db")
 first=run("first-edit",db);shutil.copy2(db,fixture/"mixed.db")
 run("second-edit",db)
 (fixture/"external-effects.json").write_text(json.dumps({"op1":1}))
 current=run("record-effect",db)
 restored=run("inspect",fixture/"v0.db"); mixed=run("inspect",fixture/"mixed.db")
 observations={"seed":seed,"current":current,"restored_fresh_process":restored,"uncoordinated_snapshot":mixed,"actual_external_effects":json.loads((fixture/"external-effects.json").read_text()),"scope":"actual candidate SDK and engine; explicit closed-connection byte snapshots; not a native snapshot API or host shell filesystem"}
 (out/"observations.json").write_text(json.dumps(observations,indent=2)+"\n")
finally:
 (out/"run.json").write_text(json.dumps({"time_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"platform":platform.platform(),"uid":os.getuid(),"protocol_sha256":hashlib.sha256((base/"protocol.json").read_bytes()).hexdigest(),"script_sha256":hashlib.sha256((base/"experiment.py").read_bytes()).hexdigest(),"commands":records},indent=2)+"\n")
print(json.dumps(observations,indent=2))
