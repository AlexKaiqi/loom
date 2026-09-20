package authority

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"
	"time"

	"loom/runtime/store"
	"loom/runtime/work"
)

func TestFreshRoundCapturesEditsAndResumeRefusesDrift(t *testing.T) {
	a, w, root := fixture(t)
	directory := filepath.Join(root, "users")
	os.Mkdir(directory, 0700)
	file := filepath.Join(directory, "note")
	os.WriteFile(file, []byte("first"), 0600)
	if err := a.Grant(w, directory); err != nil {
		t.Fatal(err)
	}
	first, err := w.UserspaceSnapshot()
	if err != nil {
		t.Fatal(err)
	}
	os.WriteFile(file, []byte("human edit before Round"), 0600)
	if _, err = w.Events.Admit("host", "request", "input", store.Object{}); err != nil {
		t.Fatal(err)
	}
	r, err := a.Claim(w, "firsthost", false)
	if err != nil {
		t.Fatal(err)
	}
	current, err := w.UserspaceSnapshot()
	if err != nil {
		t.Fatal(err)
	}
	if first.TreeDigest == current.TreeDigest {
		t.Fatal("fresh Round did not capture edit")
	}
	if err = w.Control.PauseRound(r.ID, "budget", store.Object{"plan": store.Object{"context": store.Object{}}}); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(file, []byte("edit during confirmed pause"), 0600)
	if _, err = a.Claim(w, "newowner", true); err == nil {
		t.Fatal("resume accepted changed dependency")
	}
	if _, err = a.Claim(w, "newowner", false); err == nil {
		t.Fatal("new Round replaced paused dependency")
	}
	after, err := w.UserspaceSnapshot()
	if err != nil {
		t.Fatal(err)
	}
	if after.TreeDigest != current.TreeDigest {
		t.Fatal("failed claim changed saved dependency")
	}
	rounds, err := w.Control.Rounds()
	if err != nil || len(rounds) != 1 || rounds[0].State != "paused" || rounds[0].Checkpoint == nil {
		t.Fatal(rounds, err)
	}
}

func TestExportWaitsForAuthorizedSnapshotPublication(t *testing.T) {
	a, w, root := fixture(t)
	directory := filepath.Join(root, "users")
	os.Mkdir(directory, 0700)
	filename := filepath.Join(directory, "state")
	os.WriteFile(filename, []byte("before"), 0600)
	if err := a.Grant(w, directory); err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(root, "snapshot.tar.gz")
	finished := make(chan error, 1)
	err := store.Immediate(a.Path, func(_ *sql.Conn) error {
		started := make(chan struct{})
		go func() { close(started); finished <- a.Export(w, archive) }()
		<-started
		select {
		case err := <-finished:
			t.Fatalf("export bypassed authority mutation lock: %v", err)
		case <-time.After(150 * time.Millisecond):
		}
		if err := os.WriteFile(filename, []byte("after"), 0600); err != nil {
			return err
		}
		_, err := w.CaptureUserspace(directory)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	select {
	case err = <-finished:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("export did not resume after publication")
	}
	imported, err := work.Import(archive, filepath.Join(t.TempDir(), "imported"))
	if err != nil {
		t.Fatal(err)
	}
	destination := filepath.Join(t.TempDir(), "users")
	if err = imported.RestoreUserspace(destination); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(destination, "state"))
	if err != nil || string(content) != "after" {
		t.Fatal("mixed dependency snapshot", string(content), err)
	}
}

func TestPausedMigrationRequiresMatchingIndependentGrant(t *testing.T) {
	a, w, root := fixture(t)
	directory := filepath.Join(root, "users")
	os.Mkdir(directory, 0700)
	os.WriteFile(filepath.Join(directory, "retained"), []byte("exact"), 0750)
	if err := a.Grant(w, directory); err != nil {
		t.Fatal(err)
	}
	w.Events.Admit("host", "input", "input", store.Object{})
	r, err := a.Claim(w, "oldhost", false)
	if err != nil {
		t.Fatal(err)
	}
	if err = w.Control.PauseRound(r.ID, "budget", store.Object{"plan": store.Object{}}); err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(root, "portable.tar.gz")
	if err = w.Export(archive); err != nil {
		t.Fatal(err)
	}
	imported, err := work.Import(archive, filepath.Join(t.TempDir(), "work"))
	if err != nil {
		t.Fatal(err)
	}
	b, err := Open(filepath.Join(t.TempDir(), "authority.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	if err = b.Register(imported); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(t.TempDir(), "restored")
	if err = imported.RestoreUserspace(target); err != nil {
		t.Fatal(err)
	}
	if _, err = b.Claim(imported, "newhost", true); err == nil {
		t.Fatal("restore implicitly granted Userspace")
	}
	different := t.TempDir()
	os.WriteFile(filepath.Join(different, "retained"), []byte("different"), 0750)
	if err = b.Grant(imported, different); err == nil {
		t.Fatal("mismatched rebind succeeded")
	}
	if err = b.Grant(imported, target); err != nil {
		t.Fatal(err)
	}
	continued, err := b.Claim(imported, "newhost", true)
	if err != nil {
		t.Fatal(err)
	}
	if continued.ID != r.ID || continued.Checkpoint == nil {
		t.Fatal("migration began another Round", continued)
	}
}

func TestFailedUserspaceCaptureDoesNotCreateRunningRound(t *testing.T) {
	a, w, root := fixture(t)
	directory := filepath.Join(root, "users")
	os.Mkdir(directory, 0700)
	if err := a.Grant(w, directory); err != nil {
		t.Fatal(err)
	}
	w.Events.Admit("host", "input", "input", store.Object{})
	if err := os.Symlink("/etc/passwd", filepath.Join(directory, "escape")); err != nil {
		t.Fatal(err)
	}
	if _, err := a.Claim(w, "owner", false); err == nil {
		t.Fatal("unsafe snapshot claimed Round")
	}
	rounds, err := w.Control.Rounds()
	if err != nil || len(rounds) != 0 {
		t.Fatal("failed capture left running Round", rounds, err)
	}
}
