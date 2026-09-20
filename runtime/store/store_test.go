package store

import (
	"errors"
	"path/filepath"
	"sync"
	"testing"
)

func fixture(t *testing.T) (*Events, *Control) {
	t.Helper()
	p := filepath.Join(t.TempDir(), "state.sqlite")
	if err := Initialize(p); err != nil {
		t.Fatal(err)
	}
	return &Events{Path: p}, &Control{Path: p}
}
func TestAtomicAdmissionAndConflict(t *testing.T) {
	e, _ := fixture(t)
	db, err := OpenDB(e.Path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err = db.Exec(`CREATE TRIGGER fail_pending BEFORE INSERT ON pending BEGIN SELECT RAISE(ABORT,'cut point'); END`); err != nil {
		t.Fatal(err)
	}
	if _, err = e.Admit("source", "id", "input", Object{"v": 7}); err == nil {
		t.Fatal("expected fault")
	}
	for _, table := range []string{"events", "admissions", "pending"} {
		var n int
		if err = db.QueryRow("SELECT count(*) FROM " + table).Scan(&n); err != nil || n != 0 {
			t.Fatalf("%s=%d: %v", table, n, err)
		}
	}
	if _, err = db.Exec(`DROP TRIGGER fail_pending`); err != nil {
		t.Fatal(err)
	}
	a, err := e.Admit("source", "id", "input", Object{"v": 7})
	if err != nil {
		t.Fatal(err)
	}
	b, err := e.Admit("source", "id", "input", Object{"v": 7})
	if err != nil || a.Seq != b.Seq {
		t.Fatal(b, err)
	}
	if _, err = e.Admit("source", "id", "input", Object{"v": 8}); !errors.Is(err, ErrConflict) {
		t.Fatal(err)
	}
	if _, err = db.Exec(`UPDATE events SET kind='changed'`); err == nil {
		t.Fatal("event update allowed")
	}
}
func TestConcurrentAdmissions(t *testing.T) {
	e, _ := fixture(t)
	var wg sync.WaitGroup
	results := make(chan int64, 12)
	failures := make(chan error, 12)
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			v, err := e.Admit("s", "id", "input", Object{})
			if err != nil {
				failures <- err
			} else {
				results <- v.Seq
			}
		}()
	}
	wg.Wait()
	close(results)
	close(failures)
	for err := range failures {
		t.Error(err)
	}
	for seq := range results {
		if seq != 1 {
			t.Error(seq)
		}
	}
	pending, err := e.Pending()
	if err != nil || len(pending) != 1 {
		t.Fatal(pending, err)
	}
}
func TestControlCustody(t *testing.T) {
	e, c := fixture(t)
	if _, err := e.Admit("s", "1", "input", Object{}); err != nil {
		t.Fatal(err)
	}
	r, err := c.BeginRound("one")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.BeginRound("two"); !errors.Is(err, ErrConflict) {
		t.Fatal(err)
	}
	f, err := c.PrepareEffect(r.ID, "tool", "shell", Object{"script": "append"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.PrepareEffect(r.ID, "tool", "shell", Object{"script": "append"}); !errors.Is(err, ErrUnknownEffect) {
		t.Fatal(err)
	}
	if err = c.CompleteEffect(f.ID, Object{"ok": true}); err == nil {
		t.Fatal("native result accepted before dispatch permission")
	}
	if err = c.AttemptEffect(f.ID, "stale-owner"); err == nil {
		t.Fatal("stale owner dispatched")
	}
	if err = c.AttemptEffect(f.ID, r.Owner); err != nil {
		t.Fatal(err)
	}
	if err = c.AttemptEffect(f.ID, r.Owner); err == nil {
		t.Fatal("dispatch permission issued twice")
	}
	if err = c.CompleteEffect(f.ID, Object{"ok": true}); err != nil {
		t.Fatal(err)
	}
	saved, err := c.PrepareEffect(r.ID, "tool", "shell", Object{"script": "append"})
	if err != nil || saved.Result["ok"] != true {
		t.Fatal(saved, err)
	}
	cp := Object{"context": Object{"messages": []any{}}}
	if err = c.PauseRound(r.ID, "budget", cp); err != nil {
		t.Fatal(err)
	}
	r, err = c.ResumeRound("three")
	if err != nil || r.Checkpoint == nil {
		t.Fatal(r, err)
	}
	later, err := e.Admit("s", "2", "input", Object{})
	if err != nil {
		t.Fatal(err)
	}
	if err = c.FinishRound(r.ID, "revision"); err != nil {
		t.Fatal(err)
	}
	pending, err := e.Pending()
	if err != nil || len(pending) != 1 || pending[0].Seq != later.Seq {
		t.Fatal(pending, err)
	}
}
func TestUnknownCannotResume(t *testing.T) {
	e, c := fixture(t)
	e.Admit("s", "1", "input", Object{})
	r, _ := c.BeginRound("one")
	f, _ := c.PrepareEffect(r.ID, "tool", "shell", Object{})
	if err := c.UnknownEffect(f.ID, "lost"); err != nil {
		t.Fatal(err)
	}
	if err := c.PauseRound(r.ID, "unknown", Object{"context": Object{}}); !errors.Is(err, ErrUnknownEffect) {
		t.Fatal(err)
	}
	if err := c.PauseRound(r.ID, "unknown", nil); err != nil {
		t.Fatal(err)
	}
	if _, err := c.ResumeRound("other"); err == nil {
		t.Fatal("unknown resumed")
	}
	if ok, err := c.RejectIfUndispatched(r.ID); err != nil || ok {
		t.Fatal(ok, err)
	}
}
