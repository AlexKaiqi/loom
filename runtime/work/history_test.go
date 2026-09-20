package work

import (
	"loom/runtime/store"
	"os"
	"path/filepath"
	"testing"
)

func TestHistoryForkDoesNotResetOriginalOrInheritResponsibility(t *testing.T) {
	w := fixture(t)
	source := t.TempDir()
	os.WriteFile(filepath.Join(source, "project"), []byte("initial"), 0600)
	if _, err := w.BindResource("app", source); err != nil {
		t.Fatal(err)
	}
	prior, err := w.ResourceCopy("app", "default")
	if err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(w.Surface, "memory.md"), []byte("at checkpoint"), 0600)
	os.Mkdir(filepath.Join(w.Surface, "empty"), 0750)
	os.Chmod(w.Surface, 0750)
	w.Events.Admit("user", "one", "input", store.Object{"text": "original"})
	round, err := w.Control.BeginRound("original-owner")
	if err != nil {
		t.Fatal(err)
	}
	version, err := w.Snapshot("saved")
	if err != nil {
		t.Fatal(err)
	}
	if err = w.Control.FinishRound(round.ID, version); err != nil {
		t.Fatal(err)
	}
	cps, err := w.Control.Checkpoints()
	if err != nil || len(cps) != 1 {
		t.Fatal(cps, err)
	}
	w.Events.Admit("user", "two", "input", store.Object{"text": "later"})
	active, err := w.Control.BeginRound("still-original")
	if err != nil {
		t.Fatal(err)
	}
	effect, err := w.Control.PrepareEffect(active.ID, "unknown", "tool.exec", store.Object{"script": "external"})
	if err != nil {
		t.Fatal(err)
	}
	w.Control.AttemptEffect(effect.ID, active.Owner)
	os.WriteFile(filepath.Join(w.Surface, "memory.md"), []byte("later original edit"), 0600)
	os.WriteFile(filepath.Join(source, "project"), []byte("shared human edit"), 0600)
	view := filepath.Join(t.TempDir(), "view")
	if err = w.Inspect(cps[0].ID, view); err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(filepath.Join(view, "surface", "memory.md"))
	if string(got) != "at checkpoint" {
		t.Fatal(string(got))
	}
	info, err := os.Stat(filepath.Join(view, "surface"))
	if err != nil || info.Mode().Perm() != 0750 {
		t.Fatal("root metadata lost", info, err)
	}
	child, err := w.Fork(cps[0].ID, filepath.Join(t.TempDir(), "fork"))
	if err != nil {
		t.Fatal(err)
	}
	if child.ID == w.ID {
		t.Fatal("identity copied")
	}
	rounds, _ := child.Control.Rounds()
	pending, _ := child.Events.Pending()
	if len(rounds) != 0 || len(pending) != 0 {
		t.Fatal("active responsibility copied", rounds, pending)
	}
	copied, err := child.ResourceCopy("app", "default")
	if err != nil || copied.ID == prior.ID || copied.ContentRef != prior.ContentRef {
		t.Fatal(copied, err)
	}
	if _, err = child.git("cat-file", "-e", version); err != nil {
		t.Fatal("historical projection content lost", err)
	}
	got, _ = os.ReadFile(filepath.Join(w.Surface, "memory.md"))
	if string(got) != "later original edit" {
		t.Fatal("original Work rewound")
	}
	got, _ = os.ReadFile(filepath.Join(source, "project"))
	if string(got) != "shared human edit" {
		t.Fatal("shared resource rewound")
	}
	effects, _ := w.Control.Effects(active.ID)
	if len(effects) != 1 || effects[0].Resolution != "unresolved" {
		t.Fatal("original unknown responsibility lost")
	}
	facts, _ := child.Events.Events(0)
	for _, fact := range facts {
		if fact.Payload["text"] == "later" {
			t.Fatal("future fact imported into past fork")
		}
	}
}

func TestMultiCopyCommitIsAtomic(t *testing.T) {
	w := fixture(t)
	source := t.TempDir()
	w.BindResource("app", source)
	a, _ := w.ResourceCopy("app", "default")
	b, _ := w.ResourceCopy("app", "other")
	os.WriteFile(filepath.Join(source, "new"), []byte("new"), 0600)
	next, _ := w.CaptureContent(source)
	if err := w.SaveResourceCopy(b, next, "newer"); err != nil {
		t.Fatal(err)
	}
	if err := w.SaveResourceCopies([]CopyUpdate{{a, next}, {b, next}}, "group"); err == nil {
		t.Fatal("stale second copy accepted")
	}
	stillA, err := w.ResourceCopy("app", "default")
	if err != nil || stillA != a {
		t.Fatal("first copy partially published", stillA, err)
	}
}
