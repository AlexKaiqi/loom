package controller

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"loom/runtime/authority"
	"loom/runtime/contracts"
	"loom/runtime/store"
	"loom/runtime/work"
)

type observedExecutor struct {
	binding contracts.Binding
	cancel  func() error
	calls   int
	execute func(contracts.Request, func(contracts.Checkpoint) error) (contracts.Result, error)
	acquire func(string, string) (contracts.AllocationResult, error)
	inspect func(string, string) (contracts.AllocationResult, error)
	release func(string) error
}

func (e *observedExecutor) Binding() contracts.Binding { return e.binding }
func (e *observedExecutor) Execute(_ context.Context, request contracts.Request, checkpoint func(contracts.Checkpoint) error) (contracts.Result, error) {
	if e.execute != nil {
		e.calls++
		return e.execute(request, checkpoint)
	}
	return contracts.Result{}, errors.New("business replay forbidden")
}
func (e *observedExecutor) Query(context.Context, string, string, contracts.Binding) (map[string]any, error) {
	e.calls++
	return Object{"state": "finished", "exit_code": 0}, nil
}
func (e *observedExecutor) Cancel(_ context.Context, sid, eid string, b contracts.Binding) (map[string]any, error) {
	e.calls++
	if sid != "original-sandbox" || eid != "original-session/original-run" || b != e.binding {
		return nil, errors.New("binding changed")
	}
	if err := e.cancel(); err != nil {
		return nil, err
	}
	return Object{"state": "session_deleted"}, nil
}
func (e *observedExecutor) Acquire(_ context.Context, key, target string) (contracts.AllocationResult, error) {
	if e.acquire != nil {
		return e.acquire(key, target)
	}
	return contracts.AllocationResult{}, errors.New("unexpected acquire")
}
func (e *observedExecutor) InspectAllocation(_ context.Context, key, id string) (contracts.AllocationResult, error) {
	if e.inspect != nil {
		return e.inspect(key, id)
	}
	return contracts.AllocationResult{}, errors.New("unexpected allocation query")
}
func (e *observedExecutor) Release(_ context.Context, id string) error {
	if e.release != nil {
		return e.release(id)
	}
	return errors.New("unexpected release")
}

func TestRemoteCancellationChecksOriginalBindingAndDoesNotSettleOutcome(t *testing.T) {
	root := t.TempDir()
	h := filepath.Join(root, "harness")
	if err := os.Mkdir(h, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(h, "manifest.json"), []byte(`{"protocol":1}`), 0600); err != nil {
		t.Fatal(err)
	}
	def := filepath.Join(root, "work.toml")
	if err := os.WriteFile(def, []byte("schema_version=2\n[harness]\npath='harness'\nargv=['unused']\n[surface]\npath='surface'\n[model]\nservice='test'\n[model.parameters]\nid='test'\napi='openai-completions'\nprovider='test'\n"), 0600); err != nil {
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
	effect, err := w.Control.PrepareEffect(round.ID, "one", "tool.exec", Object{"environment": "sandbox"})
	if err != nil {
		t.Fatal(err)
	}
	if err = w.Control.AttemptEffect(effect.ID, round.Owner); err != nil {
		t.Fatal(err)
	}
	binding := contracts.Binding{ServiceID: "original", Endpoint: "https://old.example", Image: "fixed-image", Profile: "code", CPU: "1", Memory: "1Gi", LeaseSeconds: 600, RequestTimeoutSeconds: 30}
	if err = w.Control.CheckpointEffect(effect.ID, Object{"binding": binding, "sandbox_id": "original-sandbox", "execution_id": "original-session/original-run"}); err != nil {
		t.Fatal(err)
	}
	if err = w.Control.UnknownEffect(effect.ID, "reply lost"); err != nil {
		t.Fatal(err)
	}
	executor := &observedExecutor{binding: binding}
	executor.cancel = func() error {
		db, err := store.OpenDB(w.DBPath)
		if err != nil {
			return err
		}
		defer db.Close()
		var state string
		if err = db.QueryRow("SELECT cancellation FROM effects WHERE id=?", effect.ID).Scan(&state); err != nil {
			return err
		}
		if state != "requested" {
			return errors.New("cancel without durable request")
		}
		return nil
	}
	runtime := Runtime{Authority: a, ResolveSandbox: func(got contracts.Binding) (contracts.TaskExecutor, error) {
		if got != binding {
			t.Fatal("resolver did not receive original binding")
		}
		return executor, nil
	}}
	executor.binding.Endpoint = "https://replacement.example"
	if _, err = runtime.CancelRemote(context.Background(), w, round.ID, effect.ID); err == nil {
		t.Fatal("rebound destination accepted")
	}
	if executor.calls != 0 {
		t.Fatal("contacted replacement destination")
	}
	executor.binding = binding
	if _, err = runtime.QueryRemote(context.Background(), w, round.ID, effect.ID); err != nil {
		t.Fatal(err)
	}
	answer, err := runtime.CancelRemote(context.Background(), w, round.ID, effect.ID)
	if err != nil || answer["cancellation"] != "stop_confirmed" {
		t.Fatal(answer, err)
	}
	effects, err := w.Control.Effects(round.ID)
	if err != nil {
		t.Fatal(err)
	}
	if effects[0].Resolution != "unresolved" || effects[0].ContentDelivery != "pending" || effects[0].Cancellation != "stop_confirmed" {
		t.Fatal(effects)
	}
	db, err := store.OpenDB(w.DBPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var count int
	if err = db.QueryRow("SELECT count(*) FROM effect_observations WHERE kind='remote_query'").Scan(&count); err != nil || count != 1 {
		t.Fatal("query evidence not retained", count, err)
	}
}
