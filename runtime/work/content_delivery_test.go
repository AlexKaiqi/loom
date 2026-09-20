package work

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"loom/runtime/filesystem"
	"loom/runtime/store"
)

func contentDeliveryFixture(t *testing.T) (*Work, string, []ContentChange) {
	t.Helper()
	w := fixture(t)
	if _, err := w.Events.Admit("host", "delivery", "input", store.Object{}); err != nil {
		t.Fatal(err)
	}
	r, err := w.Control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	w.Control = w.Control.Bind(r)
	e, err := w.Control.PrepareEffect(r.ID, "write", "tool.exec", store.Object{"environment": "work"})
	if err != nil {
		t.Fatal(err)
	}
	if err = w.Control.AttemptEffect(e.ID, r.Owner); err != nil {
		t.Fatal(err)
	}
	if err = w.Control.NativeEffect(e.ID, store.Object{"exit_code": 0}); err != nil {
		t.Fatal(err)
	}
	changes := []ContentChange{}
	for _, name := range []string{"surface", "harness"} {
		expected, err := filesystem.TreeDigest(w.contentRoot(name))
		if err != nil {
			t.Fatal(err)
		}
		candidate := t.TempDir()
		if err = os.WriteFile(filepath.Join(candidate, "result.txt"), []byte(name+" result"), 0600); err != nil {
			t.Fatal(err)
		}
		ref, err := w.CaptureContent(candidate)
		if err != nil {
			t.Fatal(err)
		}
		changes = append(changes, ContentChange{Root: name, Expected: expected, Ref: ref})
	}
	return w, e.ID, changes
}

func TestContentDeliverySurvivesFailedCommit(t *testing.T) {
	w, effect, changes := contentDeliveryFixture(t)
	db, err := store.OpenDB(w.DBPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err = db.Exec("CREATE TRIGGER cut_delivery BEFORE UPDATE ON content_deliveries BEGIN SELECT RAISE(ABORT,'cut after directory exchange'); END"); err != nil {
		t.Fatal(err)
	}
	if _, err = w.PublishContent(effect, changes); err == nil {
		t.Fatal("injected publication failure absent")
	}
	var pending int
	if err = db.QueryRow("SELECT count(*) FROM content_deliveries WHERE revision IS NULL").Scan(&pending); err != nil || pending != 1 {
		t.Fatal(pending, err)
	}
	for _, change := range changes {
		actual, err := filesystem.TreeDigest(w.contentRoot(change.Root))
		if err != nil || actual != change.Ref.SHA256 {
			t.Fatal("candidate root not preserved", actual, err)
		}
	}
	if _, err = db.Exec("DROP TRIGGER cut_delivery"); err != nil {
		t.Fatal(err)
	}
	if err = w.RecoverContent(); err != nil {
		t.Fatal(err)
	}
	var revision, delivery string
	if err = db.QueryRow("SELECT revision FROM content_deliveries WHERE effect_id=?", effect).Scan(&revision); err != nil || revision == "" {
		t.Fatal(revision, err)
	}
	if err = db.QueryRow("SELECT content_delivery FROM effects WHERE id=?", effect).Scan(&delivery); err != nil || delivery != "confirmed" {
		t.Fatal(delivery, err)
	}
	materialized := filepath.Join(t.TempDir(), "saved")
	if err = w.Materialize(revision, materialized); err != nil {
		t.Fatal(err)
	}
	for _, change := range changes {
		got, err := os.ReadFile(filepath.Join(materialized, change.Root, "result.txt"))
		if err != nil || string(got) != change.Root+" result" {
			t.Fatal(string(got), err)
		}
	}
}

func TestPartialContentDeliveryPreservesConcurrentHumanEdit(t *testing.T) {
	w, effect, changes := contentDeliveryFixture(t)
	// Save the exact durable journal, then emulate termination after the first
	// atomic exchange. This recovery path never executes the original command.
	body, _ := json.Marshal(changes)
	ref, err := (store.Records{Directory: w.ArtifactsDir()}).Put(body, "application/vnd.loom.content-delivery+json")
	if err != nil {
		t.Fatal(err)
	}
	db, err := store.OpenDB(w.DBPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	encoded, _ := json.Marshal(ref)
	if _, err = db.Exec("INSERT INTO content_deliveries(effect_id,candidate_ref) VALUES(?,?)", effect, string(encoded)); err != nil {
		t.Fatal(err)
	}
	first := changes[0]
	data, err := (store.Records{Directory: w.ArtifactsDir()}).Get(first.Ref)
	if err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(w.Surface)
	if err != nil {
		t.Fatal(err)
	}
	if err = filesystem.Restore(bytes.NewReader(data), w.Surface, info, first.Expected); err != nil {
		t.Fatal(err)
	}
	human := filepath.Join(w.Harness, "human.txt")
	if err = os.WriteFile(human, []byte("new human version"), 0600); err != nil {
		t.Fatal(err)
	}
	if err = w.RecoverContent(); err == nil {
		t.Fatal("recovery overwrote a third version")
	}
	got, err := os.ReadFile(human)
	if err != nil || string(got) != "new human version" {
		t.Fatal(string(got), err)
	}
	if err = os.Remove(human); err != nil {
		t.Fatal(err)
	}
	if err = w.RecoverContent(); err != nil {
		t.Fatal(err)
	}
}

func TestInvalidSecondCandidateCannotPartiallyPublish(t *testing.T) {
	w, effect, changes := contentDeliveryFixture(t)
	invalid, err := (store.Records{Directory: w.ArtifactsDir()}).Put([]byte("not a content archive"), "application/x-tar")
	if err != nil {
		t.Fatal(err)
	}
	changes[1].Ref = invalid
	if _, err = w.PublishContent(effect, changes); err == nil {
		t.Fatal("invalid archive published")
	}
	for _, change := range changes {
		actual, err := filesystem.TreeDigest(w.contentRoot(change.Root))
		if err != nil || actual != change.Expected {
			t.Fatal("bad second candidate changed an earlier root", change.Root, err)
		}
	}
	effects, err := w.Control.Effects(w.Control.RoundID)
	if err != nil || len(effects) != 1 || effects[0].ContentDelivery != "pending" {
		t.Fatal("failed delivery lost responsibility", err)
	}
}
