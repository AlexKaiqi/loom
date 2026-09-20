package work

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"loom/runtime/store"
)

func TestManifestCannotReplaceCommittedTree(t *testing.T) {
	w := fixture(t)
	if err := os.WriteFile(filepath.Join(w.Surface, "note.md"), []byte("actual tree bytes"), 0600); err != nil {
		t.Fatal(err)
	}
	ref, err := w.Snapshot("actual")
	if err != nil {
		t.Fatal(err)
	}
	commit, err := w.gitBytes("commit", ref)
	if err != nil {
		t.Fatal(err)
	}
	digest := strings.TrimSpace(strings.Split(string(commit), "\nfile-manifest: ")[1])
	raw, err := os.ReadFile(filepath.Join(w.ArtifactsDir(), digest))
	if err != nil {
		t.Fatal(err)
	}
	var entries []FileEntry
	if err = json.Unmarshal(raw, &entries); err != nil {
		t.Fatal(err)
	}
	forged, err := w.gitInput([]byte("different bytes outside this tree"), "hash-object", "-w", "--stdin", "--no-filters")
	if err != nil {
		t.Fatal(err)
	}
	for i := range entries {
		if entries[i].Path == "surface/note.md" {
			entries[i].Object = forged
		}
	}
	bad, _ := json.Marshal(entries)
	manifest, err := (store.Records{Directory: w.ArtifactsDir()}).Put(bad, "application/vnd.loom.file-manifest+json")
	if err != nil {
		t.Fatal(err)
	}
	tree, err := w.git("rev-parse", ref+"^{tree}")
	if err != nil {
		t.Fatal(err)
	}
	badCommit, err := w.gitInput([]byte("mismatched manifest\n\nfile-manifest: "+manifest.SHA256+"\n"), "commit-tree", tree)
	if err != nil {
		t.Fatal(err)
	}
	destination := filepath.Join(t.TempDir(), "restore")
	if err = w.Materialize(badCommit, destination); err == nil {
		t.Fatal("manifest substituted another valid blob")
	}
	if _, err = os.Lstat(destination); !os.IsNotExist(err) {
		t.Fatal("invalid historical content was materialized", err)
	}
	if err = w.Materialize(ref, destination); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(filepath.Join(destination, "surface/note.md"))
	if err != nil || string(got) != "actual tree bytes" {
		t.Fatal(string(got), err)
	}
}
