"""G3 finite public-API probe; not the product adapter or acceptance runner."""
from pathlib import Path
import subprocess,sys,json,hashlib,datetime,shutil
from oracle import pi_jsonl
ROOT=Path(__file__).resolve().parents[3]; HERE=Path(__file__).resolve().parent
out=HERE/"evidence"/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
node="/home/USER/.local/share/lore-tools/node-v24.21.0-linux-x64/bin/node"
tsx=ROOT/"research/repos/pi/node_modules/tsx/dist/loader.mjs"
env={"PATH":str(Path(node).parent)+":/usr/bin:/bin","LANG":"C.UTF-8","TSX_TSCONFIG_PATH":str(ROOT/"research/pi/tsconfig.json")}
result={"scope":"G3_PUBLIC_API_PREPARATION_ONLY","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"inputs":{},"runs":[],"checks":{},"errors":[]}
for p in [ROOT/"design/g3/s/preparation-protocol.json",HERE/"probe-public.py",HERE/"probe-public.mts",HERE/"oracle.py"]:
 result["inputs"][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest();shutil.copy2(p,out/p.name)
def run(mode,work,expected=0,label=None):
 work.mkdir(exist_ok=True);label=label or mode
 cmd=[node,"--import",str(tsx),str(HERE/"probe-public.mts"),mode,str(work)]
 p=subprocess.run(cmd,cwd=work,env=env,text=True,capture_output=True,timeout=30)
 (out/(label+".stdout")).write_text(p.stdout);(out/(label+".stderr")).write_text(p.stderr)
 result["runs"].append({"mode":mode,"work":str(work),"argv":cmd,"exit_code":p.returncode,"expected_exit":expected})
 if p.returncode!=expected:raise RuntimeError(label+" unexpected exit "+str(p.returncode)+": "+p.stderr[:500])
 return json.loads(p.stdout) if p.stdout.strip() else None
def load(p):return pi_jsonl(p.read_bytes())
def count(p):return len(p.read_text().splitlines()) if p.exists() else 0
try:
 single=run("single",out/"single-state")
 single_before=(out/"single-state/single-final.jsonl").read_bytes()
 query=run("query",out/"single-state",label="saved-query")
 multi=run("multi",out/"multi-state")
 run("pending",out/"pending-state",17)
 pending_files=list((out/"pending-state").glob("provider-intent-*.jsonl"))
 pending=load(pending_files[0]);reserved=pending["values"]["pi.op.state"]["op-1"]["responseEntryId"]
 pending_query=run("query",out/"pending-state",label="pending-query")
 recovery=run("recover",out/"pending-state")
 control=run("control",out/"control-state")
 intent=load(next((out/"single-state").glob("provider-intent-*.jsonl")))
 tool=load(out/"single-state/tool-intent-0.jsonl");recovered=load(out/"pending-state/recover-final.jsonl")
 multi_raw=load(out/"multi-state/multi-final.jsonl")
 assistant=[e for e in recovered["entries"] if e.get("message",{}).get("role")=="assistant"]
 result["checks"]={
 "public_binding_retained":single["binding"]=={"harness":"h1","input":"in1","source":None}==query["binding"],
 "original_provider_intent":intent["values"]["pi.op.state"]["op-1"]["at"]=="assistant.effect_pending",
 "original_assistant_before_tool":tool["counts"]["assistant"]==1 and tool["assistant_stop_reasons"]==["toolUse"],
 "single_saved_boundary":single["providerCalls"]==1 and count(out/"single-state/effects.jsonl")==1 and single["result"] is not None,
 "saved_query_zero_calls_exact_bytes":query["providerCalls"]==0 and query["result"]==single["result"] and query["pid"]!=single["pid"] and (out/"single-state/query-final.jsonl").read_bytes()==single_before,
 "multi_whole_batch_blocked":multi["providerCalls"]==1 and count(out/"multi-state/effects.jsonl")==0 and multi_raw["assistant_tool_call_counts"]==[2] and multi["result"] is not None,
 "pending_query_no_call_no_fabricated_result":pending_query["providerCalls"]==0 and pending_query["result"] is None,
 "pending_recovery_original_id_no_new_provider":recovery["providerCalls"]==0 and len(assistant)==1 and assistant[0]["id"]==reserved and assistant[0]["message"]["stopReason"]=="error" and "interrupted" in assistant[0]["message"].get("errorMessage","").lower(),
 "control_can_execute_batch_and_continue":control["providerCalls"]==2 and count(out/"control-state/effects.jsonl")==2}
 if not all(result["checks"].values()):raise AssertionError("one or more preregistered predictions failed")
except Exception as error:result["errors"].append(repr(error))
result["status"]="OBSERVED_PREPARATION" if not result["errors"] else "INVESTIGATE"
(out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if not result["errors"] else 1)
