package work

import (
	"archive/tar"
	"compress/gzip"
	"os"
	"path/filepath"
	"testing"

	"loom/runtime/store"
)

func fixture(t *testing.T) *Work {
	t.Helper()
	root := t.TempDir()
	h := filepath.Join(root, "policy")
	os.Mkdir(h, 0700)
	os.WriteFile(filepath.Join(h, "manifest.json"), []byte(`{"protocol":1,"command":["unused"]}`), 0600)
	definition := filepath.Join(root, "definition.toml")
	os.WriteFile(definition, []byte(`[model]
service="test"
[model.definition]
id="test-model"
api="openai-completions"
provider="test"
[userspace]
name="project"
`), 0600)
	w, err := Create(filepath.Join(root, "work"), h, definition)
	if err != nil {
		t.Fatal(err)
	}
	return w
}
func TestVersionAndPortablePending(t *testing.T) {
	w := fixture(t)
	name := filepath.Join(w.Surface, "note")
	os.WriteFile(name, []byte("before"), 0600)
	rev, err := w.Snapshot("before")
	if err != nil {
		t.Fatal(err)
	}
	os.WriteFile(name, []byte("after"), 0600)
	w.Snapshot("after")
	old, err := w.git("show", rev+":note")
	if err != nil || old != "before" {
		t.Fatal(old, err)
	}
	// Keep a live connection so the writer's close cannot checkpoint away WAL.
	reader, err := store.OpenDB(w.DBPath)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	event, err := w.Events.Admit("s", "r", "input", map[string]any{"v": 7})
	if err != nil {
		t.Fatal(err)
	}
	if wal, err := os.Stat(w.DBPath + "-wal"); err != nil || wal.Size() == 0 {
		t.Fatal("fixture must contain committed WAL before snapshot", err)
	}
	archive := filepath.Join(t.TempDir(), "portable.tar.gz")
	if err = w.Export(archive); err != nil {
		t.Fatal(err)
	}
	restored, err := Import(archive, filepath.Join(t.TempDir(), "restored"))
	if err != nil {
		t.Fatal(err)
	}
	events, err := restored.Events.Pending()
	if err != nil || len(events) != 1 || events[0].Seq != event.Seq {
		t.Fatal(events, err)
	}
	old, err = restored.git("show", rev+":note")
	if err != nil || old != "before" {
		t.Fatal(old, err)
	}
}
func TestActiveAndTraversalReject(t *testing.T) {
	w := fixture(t)
	w.Events.Admit("s", "r", "input", map[string]any{})
	w.Control.BeginRound("active")
	if err := w.Export(filepath.Join(t.TempDir(), "active.tar.gz")); err == nil {
		t.Fatal("active export allowed")
	}
	root := t.TempDir()
	archive := filepath.Join(root, "attack.tar.gz")
	f, _ := os.Create(archive)
	gz := gzip.NewWriter(f)
	tw := tar.NewWriter(gz)
	tw.WriteHeader(&tar.Header{Name: "../outside", Mode: 0600, Size: 1, Typeflag: tar.TypeReg})
	tw.Write([]byte("x"))
	tw.Close()
	gz.Close()
	f.Close()
	if _, err := Import(archive, filepath.Join(root, "imported")); err == nil {
		t.Fatal("traversal allowed")
	}
	if _, err := os.Stat(filepath.Join(root, "outside")); !os.IsNotExist(err) {
		t.Fatal(err)
	}
}

func TestSnapshotRetainsIgnoredBytesWithoutAttributeConversion(t *testing.T) {
	w := fixture(t)
	for name, content := range map[string][]byte{
		".gitignore":     []byte("hidden.bin\n"),
		".gitattributes": []byte("*.txt text eol=lf\n"),
		"hidden.bin":     {0, 1, 2, 255},
		"exact.txt":      []byte("a\r\nb\r\nc"),
	} {
		if err := os.WriteFile(filepath.Join(w.Surface, name), content, 0600); err != nil {
			t.Fatal(err)
		}
	}
	rev, err := w.Snapshot("capture every byte")
	if err != nil {
		t.Fatal(err)
	}
	for name, expected := range map[string]string{"hidden.bin": string([]byte{0, 1, 2, 255}), "exact.txt": "a\r\nb\r\nc"} {
		observed, err := w.git("show", rev+":"+name)
		if err != nil || observed != expected {
			t.Fatalf("snapshot %s = %q, expected %q: %v", name, observed, expected, err)
		}
	}
}
