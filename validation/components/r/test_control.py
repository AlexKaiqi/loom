"""Preregistered R component cases. Missing SUT is ERROR, never a skipped test."""
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from oracle import exact_binding, exact_identity_counts, fair_prefix, responsibility
from reference_context_fixture import save_context,matches_context

MODULE=os.environ.get("LORE_CONTROL_MODULE","lore.control")

class ControlContract(unittest.TestCase):
    def setUp(self):
        evidence=os.environ.get("LORE_R_EVIDENCE_DIR")
        if not evidence:raise RuntimeError("explicit persistent LORE_R_EVIDENCE_DIR required; use run_contract.py")
        label=getattr(self,"fixture_label",self._testMethodName)
        self.root=Path(evidence)/label;self.root.mkdir(parents=True,exist_ok=False)
        self.db=self.root/"control.sqlite";self.addCleanup(self.preserve_raw)
        self.surface=self.root/"surface";self.surface.mkdir()
        self.workspace=self.root/"workspace";self.workspace.mkdir()
        self.authority={"admin":{"namespaces":["n1","n2","n3"],"roles":["admin","submit","runtime"]},"alice":{"namespaces":["n1","n2"],"roles":["submit"]},"bob":{"namespaces":["n1"],"roles":["submit"]},"eve":{"namespaces":[],"roles":[]}}
        self.refroot=self.root/"originals";self.refroot.mkdir();self.refs={}
        for key,kind,owner in [("h1","harness","F"),("h2","harness","F"),("i1","input","E"),("i2","input","E"),("r1","tool_result","X"),("r2","tool_result","X"),("a1","answer","S"),("stop","stopped","X"),("f1","file_version","F"),("cond","code","F"),("ev1","event","E"),("cond2","code","F"),("ev2","event","E"),("f2","file_version","F"),("f_other","file_version","F"),("stop_other","stopped","X"),("stop_wrong_base","stopped","X"),("published_other_exec","file_version","F"),("published_other_base","file_version","F")]:
            raw=("original:"+key).encode();(self.refroot/key).write_bytes(raw)
            self.refs[key]={"owner":owner,"id":key,"kind":kind,"sha256":hashlib.sha256(raw).hexdigest()}
        for key,execution,base in [("stop","exec1","f1"),("stop_other","exec-other","f1"),("stop_wrong_base","exec1","f_other")]:
            self.refs[key].update(execution_id=execution,resource_id="s1",base_ref=self.refs[base])
        self.refs["f2"].update(execution_id="exec1",resource_id="s1",base_ref=self.refs["f1"])
        self.refs["published_other_exec"].update(execution_id="exec-other",resource_id="s1",base_ref=self.refs["f1"])
        self.refs["published_other_base"].update(execution_id="exec1",resource_id="s1",base_ref=self.refs["f_other"])
        self.refs["ev1"].update(request_id="event-request",namespace="n1",source="alice")
        for key in ("f1","f2","f_other"):
            save_context(self.refroot,self.refs[key],"base",{"resource_id":"s1"})
        save_context(self.refroot,self.refs["a1"],"stop",{"parent_id":"op1","source_ref":self.refs["a1"],"harness_ref":self.refs["h1"]})
        self.mod=importlib.import_module(MODULE)
        self.store=self.new_store()
        self.addCleanup(lambda:self.store.close())
    def preserve_raw(self):
        facts={"root":str(self.root),"db_exists":self.db.exists(),"files":{}}
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.name not in {"raw-final.json","raw.sql"}:
                try:facts["files"][str(path.relative_to(self.root))]={"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
                except OSError as exc:facts["files"][str(path.relative_to(self.root))]={"unreadable":repr(exc)}
        if self.db.exists():
            try:
                with sqlite3.connect("file:"+str(self.db)+"?mode=ro",uri=True) as db:
                    (self.root/"raw.sql").write_text("\n".join(db.iterdump()))
            except sqlite3.Error as exc:facts["sql_export_error"]=repr(exc)
        (self.root/"raw-final.json").write_text(json.dumps(facts,indent=2))

    def checker(self,ref,purpose,expected=None):
        if purpose=="input" and (isinstance(expected,dict) and "invocation_id" in expected or isinstance(ref,dict) and "path" in ref):
            from input_fixture import check_input_ref
            return check_input_ref(ref,expected,self.root)
        if not isinstance(ref,dict) or ref.get("id") not in self.refs:return False
        key=ref["id"]
        if ref!=self.refs[key] or hashlib.sha256((self.refroot/key).read_bytes()).hexdigest()!=ref["sha256"]:return False
        kinds={"stop":{"answer","stop_reason"},"result":{"tool_result","answer"},"harness":{"harness"},"stopped":{"stopped"},"published":{"file_version"},"condition":{"code"}}
        if purpose in {"base","stop"}:
            return (purpose not in kinds or ref["kind"] in kinds[purpose]) and matches_context(self.refroot,ref,purpose,expected)
        return (purpose not in kinds or ref["kind"] in kinds[purpose]) and all(ref.get(k)==v for k,v in (expected or {}).items())
    def new_store(self,**kw):
        return self.mod.ControlStore(self.db,authority=self.authority,reference_checker=self.checker,**kw)
    def req(self,id="op1",ns="n1",**payload):
        base={"input_ref":self.refs["i1"],"harness_ref":self.refs["h1"],"source_ref":None};base.update(payload)
        return {"id":id,"namespace":ns,"kind":"probe","payload":base}
    def expect_error(self,code,fn,*args,**kwargs):
        try:fn(*args,**kwargs)
        except Exception as exc:self.assertEqual(getattr(exc,"code",None),code,repr(exc))
        else:self.fail("expected contract rejection "+code)
    def register(self,id="s1",path=None,harness=None,kind="surface"):
        return self.store.register("admin","reg-"+id,id,"n1",kind,str(path or self.surface),harness or self.refs["h1"],{"alice":["read","write"],"admin":["read","write"]})
    def sql(self,query,args=()):
        with sqlite3.connect(self.db) as c:return c.execute(query,args).fetchall()
    def result_ready(self):
        self.store.accept("alice",self.req()); c=self.store.claim("worker",100)
        self.store.save_result("op1",c["token"],self.refs["r1"]);return c
    def test_R01_full_binding(self):
        request=self.req();self.store.accept("alice",request);self.store.accept("alice",copy.deepcopy(request))
        original={"principal":"alice",**request}
        actual=self.store.query("alice","op1")
        exact_binding({k:actual[k] for k in original},original)
        for field,value in [("source_ref",self.refs["r1"]),("harness_ref",self.refs["h2"]),("input_ref",self.refs["i2"])]:
            changed=copy.deepcopy(request);changed["payload"][field]=value
            self.expect_error("conflict",self.store.accept,"alice",changed)
        for field,value in [("kind","other"),("namespace","n2")]:
            changed=copy.deepcopy(request);changed[field]=value
            self.expect_error("conflict",self.store.accept,"alice",changed)
        self.expect_error("conflict",self.store.accept,"bob",request)
        self.assertEqual(self.sql("select count(*) from requests where id='op1'")[0][0],1)
        self.assertEqual(json.loads(self.sql("select payload_json from requests where id='op1'")[0][0]),request["payload"])
    def test_R02_ack_restart(self):
        self.store.accept("alice",self.req());self.store.close();self.store=self.new_store()
        self.assertEqual(self.store.query("alice","op1")["payload"],self.req()["payload"])
        self.assertEqual(self.sql("select id from requests"),[("op1",)])
        # SIGKILL cases use crash_worker.py; this case is the same immutable ACK baseline.
    def test_R03_invalid_and_unauthorized(self):
        self.expect_error("denied",self.store.accept,"eve",self.req())
        self.expect_error("denied",self.store.accept,"eve",self.req(principal="admin",user="root",origin="runtime"))
        self.expect_error("invalid",self.store.accept,"alice",self.req(id="../bad"))
        self.expect_error("invalid",self.store.accept,"alice",self.req(value=float("nan")))
        nested={}
        for _ in range(40):nested={"x":nested}
        self.expect_error("invalid",self.store.accept,"alice",self.req(value=nested))
        self.expect_error("invalid",self.store.accept,"alice",self.req(value="X"*262145))
        self.assertEqual(self.sql("select count(*) from requests")[0][0],0)
        self.store.close();self.store=self.new_store(request_limit_bytes=4096)
        edge=self.req(id="edge",value="")
        n=4096-len(json.dumps({"principal":"alice",**edge},sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode())
        edge["payload"]["value"]="X"*n
        self.assertEqual(len(json.dumps({"principal":"alice",**edge},sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()),4096)
        self.store.accept("alice",edge)
        over=copy.deepcopy(edge);over["id"]="over";over["payload"]["value"]+="X"
        self.expect_error("invalid",self.store.accept,"alice",over)
    def test_R04_registration_is_not_launch(self):
        self.register();(self.surface/"notes.md").write_text("ordinary content")
        actual=self.store.resolve("alice","n1","s1","write")
        self.assertEqual((actual["dev"],actual["ino"]),(self.surface.stat().st_dev,self.surface.stat().st_ino))
        self.assertEqual(self.store.pending(),[])
    def test_R05_invalid_identity_and_ambiguity(self):
        self.register();self.expect_error("denied",self.store.resolve,"eve","n1","s1","write")
        self.expect_error("not_found",self.store.resolve,"alice","n1",str(self.root/"outside"),"write")
        old=self.root/"old";self.surface.rename(old)
        self.expect_error("stale",self.store.resolve,"alice","n1","s1","write")
        self.surface.mkdir()
        self.expect_error("stale",self.store.resolve,"alice","n1","s1","write")
        self.surface.rmdir();old.rename(self.surface)
        sub=self.surface/"sub";sub.mkdir();self.register("nested",sub)
        self.expect_error("ambiguous",self.store.resolve,"alice","n1",str(sub),"write")
        self.assertEqual(self.store.resolve("alice","n1","nested","write")["ino"],sub.stat().st_ino)
    def test_R06_explicit_registration_changes(self):
        reg=self.register();revision=reg["revision"]
        req=self.req(resource_id="s1",resource_revision=revision);req["kind"]="invocation"
        self.store.accept("alice",req)
        self.store.rebind("admin","rebind-1","s1",revision,self.refs["h2"])
        self.assertEqual(self.store.query("alice","op1")["payload"]["harness_ref"],self.refs["h1"])
        self.expect_error("stale",self.store.rebind,"admin","rebind-2","s1",revision,self.refs["h1"])
        current=self.store.resolve("alice","n1","s1","write")
        new_request=self.req(id="new-binding",resource_id="s1",resource_revision=current["revision"],harness_ref=self.refs["h2"]);new_request["kind"]="invocation"
        self.store.accept("alice",new_request)
        self.assertEqual(self.store.query("alice","new-binding")["payload"]["harness_ref"],self.refs["h2"])
        bad=copy.deepcopy(new_request);bad["id"]="stale-binding";bad["payload"]["harness_ref"]=self.refs["h1"]
        self.expect_error("stale",self.store.accept,"alice",bad)
        new=self.root/"moved";self.surface.rename(new)
        self.store.relocate("admin","move-1","s1",str(new),current["revision"])
        self.expect_error("not_found",self.store.resolve,"alice","n1",str(self.surface),"write")
        current=self.store.resolve("alice","n1","s1","write")
        self.store.unregister("admin","unreg-1","s1",current["revision"])
        self.expect_error("not_found",self.store.resolve,"alice","n1","s1","write")
        self.assertEqual(self.store.query("alice","op1")["payload"],req["payload"])
    def test_R07_duplicate_batch(self):
        for _ in range(4):
            for i in range(12):self.store.accept("alice",self.req(id=f"d{i}"))
        exact_identity_counts([row[0] for row in self.sql("select id from requests")],[f"d{i}" for i in range(12)])
        # Three actual four-process contention batches are mandatory in concurrency.py.
    def test_R08_fair_claim(self):
        for namespace in ("n1","n2","n3"):
            for i in range(12):self.store.accept("admin",self.req(id=f"{namespace}-{i}",ns=namespace))
        seen=[];by_ns={n:[] for n in ("n1","n2","n3")}
        for i in range(36):
            c=self.store.claim(f"worker-{i%4}",100);seen.append(c["namespace"]);by_ns[c["namespace"]].append(c["id"])
        for start in range(len(seen)-2):fair_prefix(seen[start:start+3],["n1","n2","n3"])
        for namespace, ids in by_ns.items():self.assertEqual(ids,[f"{namespace}-{i}" for i in range(12)])
    def test_R09_expiry_is_reconcile(self):
        self.store.accept("alice",self.req());a=self.store.claim("a",100);b=self.store.claim("b",131)
        self.assertEqual(b["id"],"op1");self.assertEqual(b["mode"],"reconcile");self.assertNotEqual(a["token"],b["token"])
        self.expect_error("stale",self.store.save_result,"op1",a["token"],self.refs["r1"])
    def test_R10_result_is_pending_decision(self):
        c=self.result_ready();row=self.store.query("alice","op1")
        self.assertEqual(row["phase"],"decide");self.assertEqual(row["result_ref"],self.refs["r1"])
        self.assertIn("op1",[x["id"] for x in self.store.pending()])
        self.expect_error("reference_invalid",self.store.save_result,"op1",c["token"],{"owner":"X","id":"missing"})
        self.expect_error("conflict",self.store.save_result,"op1",c["token"],self.refs["r2"])
    def test_R11_decision_full_association(self):
        c=self.result_ready();body={"successors":[self.req(id="next")]}
        self.expect_error("conflict",self.store.accept_decision,"op1",c["token"],"wrong-source",self.refs["r2"],self.refs["h1"],body)
        self.expect_error("conflict",self.store.accept_decision,"op1",c["token"],"wrong-harness",self.refs["r1"],self.refs["h2"],body)
        self.store.accept_decision("op1",c["token"],"decision1",self.refs["r1"],self.refs["h1"],body)
        for source,harness,changed in [(self.refs["r2"],self.refs["h1"],body),(self.refs["r1"],self.refs["h2"],body),(self.refs["r1"],self.refs["h1"],{"successors":[self.req(id="wrong")]})]:
            self.expect_error("conflict",self.store.accept_decision,"op1",c["token"],"decision1",source,harness,changed)
        self.store.close();self.store=self.new_store();got=self.store.query_decision("decision1")
        self.assertEqual(got["body"],body);self.assertEqual(got["source_ref"],self.refs["r1"])
        self.assertEqual(json.loads(self.sql("select body_json from decisions where id='decision1'")[0][0]),body)
    def test_R12_handoff_persists_before_close(self):
        c=self.result_ready();body={"successors":[self.req(id="next")]}
        self.store.accept_decision("op1",c["token"],"decision1",self.refs["r1"],self.refs["h1"],body)
        before=[x["id"] for x in self.store.pending()];self.store.apply_decision("op1","decision1");self.store.apply_decision("op1","decision1")
        after=[x["id"] for x in self.store.pending()]
        responsibility([{"old":int("op1" in before),"successor":int("next" in before),"saved_stop":0},{"old":int("op1" in after),"successor":int("next" in after),"saved_stop":0}])
        self.assertNotIn("op1",after);self.assertEqual(self.sql("select count(*) from requests where id='next'")[0][0],1)
    def test_R13_stop_needs_original_answer(self):
        self.store.accept("alice",self.req());c=self.store.claim("worker",100)
        self.store.save_result("op1",c["token"],self.refs["a1"])
        self.expect_error("reference_invalid",self.store.accept_decision,"op1",c["token"],"bad",self.refs["a1"],self.refs["h1"],{"stop_ref":self.refs["r1"]})
        self.store.accept_decision("op1",c["token"],"stop1",self.refs["a1"],self.refs["h1"],{"stop_ref":self.refs["a1"]})
        self.store.apply_decision("op1","stop1");self.assertEqual(self.store.pending(),[])
        self.store.accept("alice",self.req(id="new-series"));self.assertEqual(len(self.store.pending()),1)
    def test_R14_static_wait_and_matching_identity(self):
        self.register();self.store.acquire("s1","exec1",self.refs["f1"]);self.store.release("s1","exec1",self.refs["stop"],self.refs["f2"]);c=self.result_ready();wait={"id":"w1","namespace":"n1","target":"s1","harness_ref":self.refs["h1"],"condition_ref":self.refs["cond"],"start_sequence":1,"filters":{},"refs":[self.refs["f1"]],"release_refs":[self.refs["stop"]]}
        self.store.accept_decision("op1",c["token"],"wait1",self.refs["r1"],self.refs["h1"],{"wait":wait});self.store.apply_decision("op1","wait1")
        self.assertEqual(self.store.waits()[0]["start_sequence"],1);self.assertIsNone(self.store.claim("worker",200))
        event=self.refs["ev1"];successor=self.req(id="wake1")
        self.expect_error("conflict",self.store.satisfy_wait,"w1",event,successor,self.refs["cond2"])
        self.store.satisfy_wait("w1",event,successor,self.refs["cond"]);self.store.satisfy_wait("w1",event,successor,self.refs["cond"])
        self.expect_error("conflict",self.store.satisfy_wait,"w1",event,self.req(id="wrong-wake"),self.refs["cond"])
        self.expect_error("conflict",self.store.satisfy_wait,"w1",self.refs["ev2"],successor,self.refs["cond"])
        self.assertEqual(self.sql("select count(*) from requests where id='wrong-wake'")[0][0],0)
        self.assertEqual(self.sql("select count(*) from requests where id='wake1'")[0][0],1)
    def test_R15_writer_not_released_by_lease(self):
        self.register();self.store.accept("alice",self.req(resource_id="s1"));old=self.store.claim("old-worker",100)
        self.store.acquire("s1","exec1",self.refs["f1"])
        recovered=self.store.claim("new-worker",131)
        self.assertEqual(recovered["mode"],"reconcile");self.assertNotEqual(old["token"],recovered["token"])
        self.expect_error("busy",self.store.acquire,"s1","exec2",self.refs["f1"])
        self.expect_error("reference_invalid",self.store.release,"s1","exec1",{"cancel_requested":True},self.refs["f1"])
        self.assertEqual(self.sql("select execution_id from holders where resource_id='s1'"),[("exec1",)])
    def test_R16_validated_release_and_stale_holder(self):
        self.register();self.store.acquire("s1","exec1",self.refs["f1"])
        for bad in ("stop_other","stop_wrong_base"):
            self.assertTrue(self.checker(self.refs[bad],"stopped"))
            self.expect_error("reference_invalid",self.store.release,"s1","exec1",self.refs[bad],self.refs["f2"])
        self.assertEqual(self.sql("select execution_id from holders where resource_id='s1'"),[("exec1",)])
        for bad in ("published_other_exec","published_other_base"):
            self.assertTrue(self.checker(self.refs[bad],"published"))
            self.expect_error("reference_invalid",self.store.release,"s1","exec1",self.refs["stop"],self.refs[bad])
        self.assertEqual(self.sql("select execution_id from holders where resource_id='s1'"),[("exec1",)])
        self.store.release("s1","exec1",self.refs["stop"],self.refs["f2"])
        self.store.acquire("s1","exec2",self.refs["f2"])
        self.expect_error("stale",self.store.release,"s1","exec1",self.refs["stop"],self.refs["f2"])
        self.assertEqual(self.sql("select execution_id from holders where resource_id='s1'"),[("exec2",)])
    def test_R17_pause_keeps_original_query(self):
        self.store.accept("alice",self.req());c=self.store.claim("worker",100)
        self.store.pause("op1",c["token"],"transport reply missing",{"owner":"X","id":"original-execution"})
        self.store.close();self.store=self.new_store();row=self.store.query("alice","op1")
        self.assertEqual(row["phase"],"paused");self.assertEqual(row["query_ref"]["id"],"original-execution")
        self.assertIn("op1",[x["id"] for x in self.store.pending()]);self.assertIsNone(self.store.claim("new-worker",200))
        self.register("w2",self.workspace,kind="workspace")
        self.store.accept("alice",self.req(id="other-resource",resource_id="w2"))
        other=self.store.claim("other-worker",200)
        self.assertEqual(other["id"],"other-resource");self.assertEqual(other["mode"],"execute")
        self.assertEqual(self.store.query("alice","op1")["phase"],"paused")
    def test_R19_controlled_install_identity(self):
        self.register();self.store.acquire("s1","exec1",self.refs["f1"])
        old=self.store.resolve("alice","n1","s1","write")
        staged=self.root/"staged";staged.mkdir();(staged/"notes.md").write_text("prepared")
        staged_root={"path":str(staged),"dev":staged.stat().st_dev,"ino":staged.stat().st_ino}
        staged_ref={"owner":"F","id":"stage1","kind":"staged","root":staged_root,"sha256":"fixture-stage-version"}
        stage_original=self.refroot/"stage1-original"
        stage_original.write_bytes(json.dumps({"root":staged_root,"notes_sha256":hashlib.sha256((staged/"notes.md").read_bytes()).hexdigest()},sort_keys=True).encode())
        staged_ref["sha256"]=hashlib.sha256(stage_original.read_bytes()).hexdigest()
        save_context(self.refroot,staged_ref,"staged",{"resource_id":"s1","execution_id":"exec1","base_ref":self.refs["f1"]})
        installation=[]
        def staged_checker(ref,purpose,expected=None):
            if ref==staged_ref and purpose=="staged":
                return stage_original.is_file() and hashlib.sha256(stage_original.read_bytes()).hexdigest()==ref["sha256"] and matches_context(self.refroot,ref,purpose,expected)
            if installation and ref==installation[0] and purpose=="installation":
                now=self.surface.stat();current=ref["current"]
                return (now.st_dev,now.st_ino)==(current["dev"],current["ino"]) and all(ref.get(k)==v for k,v in (expected or {}).items())
            return self.checker(ref,purpose,expected)
        self.store.close();self.store=self.mod.ControlStore(self.db,authority=self.authority,reference_checker=staged_checker)
        self.store.prepare_install("admin","install1","s1","exec1",old["revision"],self.refs["f1"],staged_ref)
        self.expect_error("pending_reconcile",self.store.resolve,"alice","n1","s1","write")
        self.expect_error("reference_invalid",self.store.confirm_install,"install1",{"owner":"F","id":"invented"})
        retired=self.root/"retired";self.surface.rename(retired);staged.rename(self.surface)
        # Two ordinary renames are a controlled F fixture, not an atomic-install proof.
        installation.append({"owner":"F","id":"install1","kind":"installation","request_id":"install1","resource_id":"s1","execution_id":"exec1","base_ref":self.refs["f1"],"status":"installed_pending_confirmation","current":{"path":str(self.surface),"dev":self.surface.stat().st_dev,"ino":self.surface.stat().st_ino},"retired":{"path":str(retired),"dev":retired.stat().st_dev,"ino":retired.stat().st_ino},"version_ref":staged_ref})
        self.store.confirm_install("install1",installation[0]);self.store.confirm_install("install1",installation[0])
        current=self.store.resolve("alice","n1","s1","write")
        self.assertEqual((current["dev"],current["ino"]),(staged_root["dev"],staged_root["ino"]))
        self.assertEqual(current["revision"],old["revision"]+1)
        self.assertEqual(self.sql("select execution_id from holders where resource_id='s1'"),[("exec1",)])
        self.assertEqual((retired.stat().st_dev,retired.stat().st_ino),(old["dev"],old["ino"]))

    def test_R20_facility_receipt_not_parent_completion(self):
        from receipt_cases import exercise
        exercise(self)

    def test_R21_input_binding_and_eligibility(self):
        from input_cases import exercise
        exercise(self,MODULE)

    def test_R22_restore_plan_and_partial_receipts(self):
        from restore_cases import exercise
        exercise(self,MODULE)

    def test_R18_corrupt_store_not_silent_empty(self):
        self.store.accept("alice",self.req());self.store.close()
        self.db.write_bytes(b"corrupted original sqlite")
        self.expect_error("storage_error",self.new_store)
        self.assertEqual(self.db.read_bytes(),b"corrupted original sqlite")

if __name__=="__main__":unittest.main()
