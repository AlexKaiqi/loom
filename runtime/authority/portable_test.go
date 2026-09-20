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

func TestSharedSourceEditsDoNotReplaceWorkCopyOrBlockResume(t *testing.T) {
	a, w, root := fixture(t)
	directory := filepath.Join(root, "users")
	os.Mkdir(directory, 0700)
	file := filepath.Join(directory, "note")
	os.WriteFile(file, []byte("first"), 0600)
	if err := a.Grant(w, directory); err != nil {
		t.Fatal(err)
	}
	first, err := w.ResourceCopy("app", "default")
	if err != nil {
		t.Fatal(err)
	}
	os.WriteFile(file, []byte("human edit before Round"), 0600)
	w.Events.Admit("host", "request", "input", store.Object{})
	r, err := a.Claim(w, "firsthost", false)
	if err != nil {
		t.Fatal(err)
	}
	current, err := w.ResourceCopy("app", "default")
	if err != nil || current != first {
		t.Fatal("shared source drift replaced copy", err)
	}
	if err = w.Control.PauseRound(r.ID, "budget", store.Object{"plan": store.Object{}}); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(file, []byte("another shared edit"), 0600)
	continued, err := a.Claim(w, "newowner", true)
	if err != nil || continued.ID != r.ID {
		t.Fatal("shared source drift blocked independent continuation", err)
	}
	after, err := w.ResourceCopy("app", "default")
	if err != nil || after != first {
		t.Fatal("resume changed copy", err)
	}
	if _, err = a.Claim(w, "thirdowner", false); err == nil {
		t.Fatal("active Round replaced")
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
		copy, err := w.ResourceCopy("app", "default")
		if err != nil {
			return err
		}
		ref, err := w.CaptureContent(directory)
		if err != nil {
			return err
		}
		return w.SaveResourceCopy(copy, ref, "test-confirmed-effect")
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
	if err = imported.RestoreResource("app", "default", destination); err != nil {
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
	if err = imported.RestoreResource("app", "", target); err != nil {
		t.Fatal(err)
	}
	if _, err = b.Claim(imported, "newhost", true); err == nil {
		t.Fatal("restore implicitly granted Userspace")
	}
	different := t.TempDir()
	os.WriteFile(filepath.Join(different, "retained"), []byte("different"), 0750)
	// New host authority is rebuilt explicitly; shared current bytes may differ
	// because the portable Work already retains its own exact initial/copy bytes.
	if err = b.Grant(imported, different); err != nil {
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

func TestFailedInitialResourceCaptureDoesNotGrantOrClaim(t *testing.T) {
	a, w, root := fixture(t)
	directory := filepath.Join(root, "users")
	os.Mkdir(directory, 0700)
	if err := os.Symlink("/etc/passwd", filepath.Join(directory, "escape")); err != nil {
		t.Fatal(err)
	}
	if err := a.Grant(w, directory); err == nil {
		t.Fatal("unsafe initial source granted")
	}
	if _, err := a.Resource(w, "app"); err == nil {
		t.Fatal("failed grant left authority")
	}
	w.Events.Admit("host", "input", "input", store.Object{})
	if _, err := a.Claim(w, "owner", false); err == nil {
		t.Fatal("missing dependency claimed Round")
	}
	rounds, err := w.Control.Rounds()
	if err != nil || len(rounds) != 0 {
		t.Fatal(rounds, err)
	}
}

func TestExportRejectsRetainedExecutionDomain(t *testing.T) {
	a, w, root := fixture(t)
	db, err := store.OpenDB(a.Path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	// A confirmed Work checkpoint does not imply its old Linux writer is fenced.
	_, err = db.Exec("INSERT INTO execution_domains(id,work_id,round_id,owner,role,cgroup,staging,state) VALUES('domain',?,'round','owner','harness','cgroup','stage','retained')", w.ID)
	if err != nil {
		t.Fatal(err)
	}
	destination := filepath.Join(root, "must-not-publish.tar.gz")
	if err = a.Export(w, destination); err == nil {
		t.Fatal("export ignored retained writer")
	}
	if _, err = os.Stat(destination); !os.IsNotExist(err) {
		t.Fatal("export published before fencing", err)
	}
}
