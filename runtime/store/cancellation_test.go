package store

import "testing"

func TestCancellationRetainsUnknownExecutionAndContentResponsibility(t *testing.T) {
	e, c := fixture(t)
	if _, err := e.Admit("host", "first", "input", Object{}); err != nil {
		t.Fatal(err)
	}
	r, err := c.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	bound := c.Bind(r)
	effect, err := bound.PrepareEffect(r.ID, "native", "tool.exec", Object{})
	if err != nil {
		t.Fatal(err)
	}
	if err = bound.AttemptEffect(effect.ID, r.Owner); err != nil {
		t.Fatal(err)
	}
	if err = bound.UnknownEffect(effect.ID, "lost reply"); err != nil {
		t.Fatal(err)
	}
	if err = bound.RequestCancellation(effect.ID); err != nil {
		t.Fatal(err)
	}
	if err = bound.ObserveCancellation(effect.ID, true, Object{"state": "session_deleted"}); err != nil {
		t.Fatal(err)
	}
	if err = bound.ObserveCancellation(effect.ID, false, Object{"state": "late timeout"}); err != nil {
		t.Fatal(err)
	}
	effects, err := c.Effects(r.ID)
	if err != nil {
		t.Fatal(err)
	}
	got := effects[0]
	if got.Resolution != "unresolved" || got.ContentDelivery != "pending" || got.Cancellation != "stop_confirmed" || got.DispatchState != "attempted" {
		t.Fatal(got)
	}
	if err = bound.FinishRound(r.ID, "fake"); err == nil {
		t.Fatal("stop was treated as execution success")
	}
	if _, err = c.BeginRecovery("replacement"); err != nil {
		t.Fatal(err)
	}
	if err = bound.RequestCancellation(effect.ID); err == nil {
		t.Fatal("revoked strategy requested cancellation")
	}
	db, err := OpenDB(c.Path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var n int
	if err = db.QueryRow("SELECT count(*) FROM effect_observations WHERE kind LIKE 'cancellation_%'").Scan(&n); err != nil || n != 3 {
		t.Fatal(n, err)
	}
}
