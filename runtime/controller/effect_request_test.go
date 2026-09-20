package controller

import (
	"errors"
	"loom/runtime/authority"
	"loom/runtime/contracts"
	"loom/runtime/store"
	"loom/runtime/work"
	"os"
	"path/filepath"
	"testing"
)

func TestHarnessEffectRequestPersistsBindingBeforeDispatchAndDoesNotReplay(t *testing.T) {
	c, executor := toolAPIFixture(t)
	w, round := c.work, c.round
	executor.execute = func(req contracts.Request, callback func(contracts.Checkpoint) error) (contracts.Result, error) {
		effects, err := w.Control.Effects(round.ID)
		if err != nil {
			return contracts.Result{}, err
		}
		if len(effects) != 1 || effects[0].Kind != "tool.exec" || effects[0].DispatchState != "attempted" {
			return contracts.Result{}, errors.New("dispatch before responsibility")
		}
		facts, err := w.Events.Events(0)
		if err != nil {
			return contracts.Result{}, err
		}
		if len(facts) != 2 || facts[1].Kind != "effect.accepted" || object(facts[1].Payload["destination_binding"])["allocation_id"] == nil {
			return contracts.Result{}, errors.New("dispatch before fixed destination")
		}
		code := 0
		if err = callback(contracts.Checkpoint{Binding: executor.binding, Phase: "native_result", SandboxID: "sandbox", ExecutionID: "session/run", NativeResult: Object{"exit_code": 0}}); err != nil {
			return contracts.Result{}, err
		}
		return contracts.Result{Binding: executor.binding, OperationID: req.OperationID, Target: req.Target, State: "completed", ExitCode: &code, Released: true}, nil
	}
	ref, err := (store.Records{Directory: w.ArtifactsDir()}).Put([]byte(`{"script":"printf once","timeout":10}`), "application/json")
	if err != nil {
		t.Fatal(err)
	}
	c.allowRecord(ref)
	params := Object{"request_key": "one", "kind": "tool.exec", "environment": "sandbox", "target": "default", "payload_ref": ref}
	first, err := apiCall(c, "effect.request", params)
	if err != nil {
		t.Fatal(err)
	}
	if first.(Object)["accepted"] != true || executor.calls != 1 {
		t.Fatal(first, executor.calls)
	}
	// A new current provider cannot redirect or replay this stable request.
	c.runtime.Targets = map[string]contracts.TaskExecutor{}
	again, err := apiCall(c, "effect.request", params)
	if err != nil {
		t.Fatal(err)
	}
	one, _ := store.Canonical(first)
	two, _ := store.Canonical(again)
	if one != two || executor.calls != 1 {
		t.Fatal("idempotence or original binding lost", first, again)
	}
	different, err := (store.Records{Directory: w.ArtifactsDir()}).Put([]byte(`{"script":"changed"}`), "application/json")
	if err != nil {
		t.Fatal(err)
	}
	c.allowRecord(different)
	params["payload_ref"] = different
	_, err = apiCall(c, "effect.request", params)
	requireAPIKind(t, err, "identity_conflict")
	params["kind"] = "work.create"
	_, err = apiCall(c, "effect.request", params)
	requireAPIKind(t, err, "capability_missing")
}

func toolAPIFixture(t *testing.T) (*run, *observedExecutor) {
	t.Helper()
	root := t.TempDir()
	h := filepath.Join(root, "harness")
	if err := os.Mkdir(h, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(h, "manifest.json"), []byte(`{"protocol":1}`), 0600); err != nil {
		t.Fatal(err)
	}
	def := filepath.Join(root, "definition.toml")
	if err := os.WriteFile(def, []byte("schema_version=2\n[harness]\npath='harness'\nargv=['unused']\n[surface]\npath='surface'\n[model]\nservice='test'\n[targets.default]\nprofile='code'\n"), 0600); err != nil {
		t.Fatal(err)
	}
	w, err := work.Create(filepath.Join(root, "work"), h, def)
	if err != nil {
		t.Fatal(err)
	}
	a, err := authority.Open(filepath.Join(root, "host/authority.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	if err = a.Register(w); err != nil {
		t.Fatal(err)
	}
	if _, err = w.Events.Admit("host", "one", "input", Object{}); err != nil {
		t.Fatal(err)
	}
	round, err := w.Control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	w.Control = w.Control.Bind(round)
	w.Events.Control = w.Control
	executor := &observedExecutor{binding: contracts.Binding{ServiceID: "original", Endpoint: "https://original.example", Image: "fixed"}}
	c := &run{round: round, work: w, runtime: &Runtime{Authority: a, Targets: map[string]contracts.TaskExecutor{"default": executor}}}
	return c, executor
}

func TestAllocationLostReplyReconcilesAndReleaseWaitsForContent(t *testing.T) {
	c, executor := toolAPIFixture(t)
	creates, deletes := 0, 0
	original := ""
	executor.acquire = func(key, target string) (contracts.AllocationResult, error) {
		creates++
		original = key
		effects, err := c.work.Control.Effects(c.round.ID)
		if err != nil {
			return contracts.AllocationResult{}, err
		}
		if len(effects) != 1 || effects[0].DispatchState != "attempted" {
			t.Fatal("allocation dispatched without permit", effects)
		}
		return contracts.AllocationResult{}, errors.New("lost acknowledgement")
	}
	result, err := apiCall(c, "allocation.acquire", Object{"request_key": "once", "target": "default"})
	if err != nil {
		t.Fatal(err)
	}
	id := result.(Object)["allocation_id"].(string)
	if _, err = apiCall(c, "allocation.acquire", Object{"request_key": "once", "target": "default"}); err != nil || creates != 1 {
		t.Fatal("acquire replayed", creates, err)
	}
	executor.inspect = func(key, sid string) (contracts.AllocationResult, error) {
		if key != original || sid != "" && sid != "original-native" {
			t.Fatal("query rebound", key, sid)
		}
		return contracts.AllocationResult{ID: "original-native", State: "observed", Native: Object{"metadata": Object{"loom.operation": key}}}, nil
	}
	executor.release = func(id string) error {
		if id != "original-native" {
			t.Fatal("release rebound", id)
		}
		db, err := store.OpenDB(c.work.DBPath)
		if err != nil {
			return err
		}
		defer db.Close()
		var n int
		if err = db.QueryRow("SELECT count(*) FROM effect_observations WHERE effect_id=? AND kind='allocation.release_requested'", original).Scan(&n); err != nil {
			return err
		}
		if n == 0 {
			t.Fatal("release before durable request")
		}
		deletes++
		return nil
	}
	if _, err = apiCall(c, "allocation.inspect", Object{"id": id}); err != nil {
		t.Fatal(err)
	}
	effects, err := c.work.Control.Effects(c.round.ID)
	if err != nil || effects[0].Resolution != "native_result" {
		t.Fatal(effects, err)
	}
	// A reused command whose output is unknown prevents destroying the only copy.
	tool, err := c.work.Control.PrepareEffect(c.round.ID, "tool", "tool.exec", Object{"allocation_id": id})
	if err != nil {
		t.Fatal(err)
	}
	if err = c.work.Control.AttemptEffect(tool.ID, c.round.Owner); err != nil {
		t.Fatal(err)
	}
	_, err = apiCall(c, "allocation.release", Object{"id": id})
	requireAPIKind(t, err, "not_ready")
	if deletes != 0 {
		t.Fatal("unsaved task destroyed")
	}
	if err = c.work.Control.CompleteEffect(tool.ID, Object{"native": "saved by trusted adapter"}); err != nil {
		t.Fatal(err)
	}
	if _, err = apiCall(c, "allocation.release", Object{"id": id}); err != nil {
		t.Fatal(err)
	}
	if deletes != 1 {
		t.Fatal(deletes)
	}
	if _, err = apiCall(c, "allocation.release", Object{"id": id}); err != nil || deletes != 1 {
		t.Fatal("release replay", deletes, err)
	}
	if err = c.work.Control.AllocationReleaseObserved(id, false); err != nil {
		t.Fatal(err)
	}
	allocations, err := c.work.Control.Allocations(c.round.ID)
	if err != nil || allocations[0].ReleaseState != "confirmed" {
		t.Fatal("late failure downgraded confirmed release", allocations, err)
	}
}
