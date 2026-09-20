package controller

import (
	"context"
	"errors"
	"loom/runtime/authority"
	"loom/runtime/store"
	"loom/runtime/work"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

func TestSubscriptionsBackfillLostReceiptAndHandoffRace(t *testing.T) {
	root := t.TempDir()
	h := filepath.Join(root, "harness")
	if err := os.Mkdir(h, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(h, "manifest.json"), []byte(`{"protocol":1}`), 0600); err != nil {
		t.Fatal(err)
	}
	def := filepath.Join(root, "definition.toml")
	if err := os.WriteFile(def, []byte("schema_version=2\n[harness]\npath='harness'\nargv=['unused']\n[surface]\npath='surface'\n[model]\nservice='test'\n[model.parameters]\nid='model'\napi='openai-completions'\nprovider='test'\n"), 0600); err != nil {
		t.Fatal(err)
	}
	source, err := work.Create(filepath.Join(root, "source"), h, def)
	if err != nil {
		t.Fatal(err)
	}
	target, err := work.Create(filepath.Join(root, "target"), h, def)
	if err != nil {
		t.Fatal(err)
	}
	a, err := authority.Open(filepath.Join(root, "host", "authority.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	for _, w := range []*work.Work{source, target} {
		if err = a.Register(w); err != nil {
			t.Fatal(err)
		}
	}
	if err = a.AllowRelay(source, target); err != nil {
		t.Fatal(err)
	}
	r := Runtime{Authority: a}
	sources := map[string]*work.Work{source.ID: source}
	first, err := source.Events.Append("adapter", "result-1", "artifact.ready", Object{"version": "V17"})
	if err != nil {
		t.Fatal(err)
	}
	if err = target.Events.Subscribe("watch", source.ID, []string{"artifact.ready"}, 0); err != nil {
		t.Fatal(err)
	}
	// Actual receipt loss: commit target input but leave the source scan cursor.
	if _, err = target.Events.Admit("work:"+source.ID, "fact:"+first.FactID, first.Kind, first.Payload); err != nil {
		t.Fatal(err)
	}
	if err = r.PumpSubscriptions(target, sources); err != nil {
		t.Fatal(err)
	}
	inputs, err := target.Events.Pending()
	if err != nil || len(inputs) != 1 {
		t.Fatal(inputs, err)
	}
	round, err := target.Control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = source.Events.Append("adapter", "result-2", "artifact.ready", Object{"version": "V18"}); err != nil {
		t.Fatal(err)
	}
	if err = r.PumpSubscriptions(target, sources); err != nil {
		t.Fatal(err)
	}
	if err = target.Control.FinishRound(round.ID, "content-version"); err != nil {
		t.Fatal(err)
	}
	inputs, err = target.Events.Pending()
	if err != nil || len(inputs) != 1 || inputs[0].Payload["version"] != "V18" {
		t.Fatal("handoff consumed unclaimed input", inputs, err)
	}
	// Restart the target and scanner without any live strategy object.
	target, err = work.Open(target.Path)
	if err != nil {
		t.Fatal(err)
	}
	if err = r.PumpSubscriptions(target, sources); err != nil {
		t.Fatal(err)
	}
	facts, err := target.Events.Events(0)
	if err != nil || len(facts) != 2 {
		t.Fatal("duplicate delivery", facts, err)
	}
	if err = target.Events.Subscribe("watch", source.ID, []string{"other"}, 0); err == nil {
		t.Fatal("changed subscription accepted")
	}
	db, err := store.OpenDB(target.DBPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var n int
	if err = db.QueryRow("SELECT count(*) FROM deliveries").Scan(&n); err != nil || n != 2 {
		t.Fatal(n, err)
	}
}

func TestSchedulerContinuesWhenAnotherRegisteredWorkDisappears(t *testing.T) {
	root := t.TempDir()
	harness := filepath.Join(root, "harness")
	if err := os.Mkdir(harness, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(harness, "manifest.json"), []byte(`{"protocol":1}`), 0600); err != nil {
		t.Fatal(err)
	}
	definition := filepath.Join(root, "definition.toml")
	if err := os.WriteFile(definition, []byte("schema_version=2\n[harness]\npath='harness'\nargv=['unused']\n[surface]\npath='surface'\n[model]\nservice='test'\n[model.parameters]\nid='model'\napi='openai-completions'\nprovider='test'\n"), 0600); err != nil {
		t.Fatal(err)
	}
	a, err := authority.Open(filepath.Join(root, "authority.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	works := []*work.Work{}
	for _, name := range []string{"missing", "healthy"} {
		w, err := work.Create(filepath.Join(root, name), harness, definition)
		if err != nil {
			t.Fatal(err)
		}
		if err = a.Register(w); err != nil {
			t.Fatal(err)
		}
		works = append(works, w)
	}
	if err = os.Rename(works[0].Path, works[0].Path+"-moved"); err != nil {
		t.Fatal(err)
	}
	if _, err = works[1].Events.Admit("host", "new", "input", Object{"text": "still owed"}); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	var mu sync.Mutex
	failed := map[string]error{}
	dispatched := make(chan string, 1)
	sentinel := errors.New("resolver observed independent dispatch")
	s := Scheduler{Authority: a, Interval: time.Second, Concurrency: 1,
		Observe:    func(id string, err error) { mu.Lock(); failed[id] = err; mu.Unlock() },
		RuntimeFor: func(w *work.Work) (*Runtime, error) { dispatched <- w.ID; cancel(); return nil, sentinel },
	}
	if err = s.Serve(ctx); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	select {
	case id := <-dispatched:
		if id != works[1].ID {
			t.Fatal(id)
		}
	default:
		t.Fatal("healthy Work was not dispatched")
	}
	mu.Lock()
	defer mu.Unlock()
	if failed[works[0].ID] == nil || !errors.Is(failed[works[1].ID], sentinel) {
		t.Fatal(failed)
	}
	pending, err := works[1].Events.Pending()
	if err != nil || len(pending) != 1 {
		t.Fatal(pending, err)
	}
}
