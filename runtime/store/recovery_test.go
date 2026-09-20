package store

import (
	"errors"
	"testing"
)

func TestRecoveryRevokesOwnerAndDoesNotReplayUnknown(t *testing.T) {
	e, c := fixture(t)
	e.Admit("s", "1", "input", Object{})
	r, err := c.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	bound := c.Bind(r)
	prepared, err := bound.PrepareEffect(r.ID, "prepared", "tool.exec", Object{"script": "a"})
	if err != nil {
		t.Fatal(err)
	}
	attempted, err := bound.PrepareEffect(r.ID, "attempted", "tool.exec", Object{"script": "b"})
	if err != nil {
		t.Fatal(err)
	}
	if err = bound.AttemptEffect(attempted.ID, r.Owner); err != nil {
		t.Fatal(err)
	}
	recovery, err := c.BeginRecovery("recovery")
	if err != nil {
		t.Fatal(err)
	}
	if recovery.Epoch <= r.Epoch {
		t.Fatal("epoch not revoked")
	}
	for _, err := range []error{
		bound.AttemptEffect(prepared.ID, r.Owner),
		bound.FinishRound(r.ID, "revision"),
		bound.PauseRound(r.ID, "stale", nil),
		bound.Owned(func() error { t.Error("stale owner published files"); return nil }),
	} {
		if !errors.Is(err, ErrConflict) {
			t.Fatal("stale write accepted", err)
		}
	}
	if _, err = bound.PrepareEffect(r.ID, "new", "tool.exec", Object{}); !errors.Is(err, ErrConflict) {
		t.Fatal(err)
	}
	ownedEvents := &Events{Path: e.Path, Control: bound}
	if _, err = ownedEvents.AppendOwned("runtime", "old-projection", "projection.published", Object{}); !errors.Is(err, ErrConflict) {
		t.Fatal("revoked Harness published a projection", err)
	}
	if _, err = ownedEvents.Append("model-adapter", "late", "model.message", Object{}); err != nil {
		t.Fatal("recovery dropped late native evidence", err)
	}
	if err = c.EndRecovery(recovery); err != nil {
		t.Fatal(err)
	}
	effects, err := c.Effects(r.ID)
	if err != nil {
		t.Fatal(err)
	}
	if effects[0].Resolution != "confirmed_not_executed" || effects[1].Resolution != "unresolved" {
		t.Fatal(effects)
	}
	rounds, _ := c.Rounds()
	if rounds[0].State != "blocked" {
		t.Fatal(rounds)
	}
	if _, err = c.ResumeRound("next"); err == nil {
		t.Fatal("unknown attempted effect resumed")
	}
	pending, _ := e.Pending()
	if len(pending) != 1 {
		t.Fatal("recovery dropped input responsibility")
	}
	// Late native evidence is retained independently from the revoked strategy.
	if err = bound.CompleteEffect(attempted.ID, Object{"native": "observed"}); err != nil {
		t.Fatal(err)
	}
	if err = bound.Owned(func() error { t.Error("late evidence restored authority"); return nil }); err == nil {
		t.Fatal("old epoch revived")
	}
}

func TestRecoveryBeforeDispatchAndRecoveryCrash(t *testing.T) {
	e, c := fixture(t)
	e.Admit("s", "1", "input", Object{})
	r, _ := c.BeginRound("owner")
	first, err := c.BeginRecovery("recovery-1")
	if err != nil {
		t.Fatal(err)
	}
	second, err := c.BeginRecovery("recovery-2")
	if err != nil {
		t.Fatal(err)
	}
	if err = c.EndRecovery(first); !errors.Is(err, ErrConflict) {
		t.Fatal("stale recovery settled", err)
	}
	if err = c.EndRecovery(second); err != nil {
		t.Fatal(err)
	}
	resumed, err := c.ResumeRound("new")
	if err != nil {
		t.Fatal(err)
	}
	if resumed.ID != r.ID || resumed.Epoch <= second.Epoch || resumed.State != "running" {
		t.Fatal(resumed)
	}
}
