package authority

import (
	"loom/runtime/store"
	"os"
	"path/filepath"
	"testing"
)

func TestReadGrantIsScopedAndDoesNotConferRelayOrResourceAuthority(t *testing.T) {
	a, w, _ := fixture(t)
	_, other, _ := fixture(t)
	if err := a.Register(other); err != nil {
		t.Fatal(err)
	}
	if err := a.GrantRead(w, other, "peer"); err != nil {
		t.Fatal(err)
	}
	grants, err := a.ReadGrants(other)
	if err != nil || len(grants) != 1 || grants[0].Source.ID != w.ID {
		t.Fatal(grants, err)
	}
	if err = a.RelayAllowed(w, other); err == nil {
		t.Fatal("read grant became event-delivery authority")
	}
	if _, err = a.Resource(other, "peer"); err == nil {
		t.Fatal("read view became write resource authority")
	}
	if err = a.GrantRead(w, other, "app"); err == nil {
		t.Fatal("alias shadowed a declared resource")
	}
	other.Events.Admit("host", "input", "work.message", store.Object{"text": "read"})
	round, err := other.Control.BeginRound("active")
	if err != nil {
		t.Fatal(err)
	}
	if err = a.RevokeRead(other, "peer"); err == nil {
		t.Fatal("live reader revoked without fencing")
	}
	if err = other.Control.PauseRound(round.ID, "not executed", nil); err != nil {
		t.Fatal(err)
	}
	if err = a.RevokeRead(other, "peer"); err != nil {
		t.Fatal(err)
	}
	grants, err = a.ReadGrants(other)
	if err != nil || len(grants) != 0 {
		t.Fatal(grants, err)
	}
}

func TestGrantCannotRebindAnotherWorksResource(t *testing.T) {
	a, w, _ := fixture(t)
	_, other, _ := fixture(t)
	if err := a.Register(other); err != nil {
		t.Fatal(err)
	}
	source := t.TempDir()
	nested := filepath.Join(source, "nested")
	os.Mkdir(nested, 0700)
	if err := a.Grant(w, source); err != nil {
		t.Fatal(err)
	}
	if err := a.Grant(other, nested); err == nil {
		t.Fatal("grant rebound another Work's same-named resource")
	}
	grant, err := a.Resource(w, "app")
	physical, e := StatIdentity(source)
	if e != nil {
		t.Fatal(e)
	}
	if err != nil || grant.Path != physical.Path {
		t.Fatal(grant, err)
	}
}
