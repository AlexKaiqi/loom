package work

import (
	"os"
	"path/filepath"
	"testing"
)

func TestIndependentTargetCopiesAndPredecessorCAS(t *testing.T) {
	w := fixture(t)
	source := t.TempDir()
	os.WriteFile(filepath.Join(source, "state"), []byte("base"), 0600)
	if _, err := w.BindResource("app", source); err != nil {
		t.Fatal(err)
	}
	a, err := w.ResourceCopy("app", "default")
	if err != nil {
		t.Fatal(err)
	}
	b, err := w.ResourceCopy("app", "other")
	if err != nil {
		t.Fatal(err)
	}
	if a.ID == b.ID || a.ContentRef != b.ContentRef {
		t.Fatal("Targets do not start from separate copies of same version")
	}
	os.WriteFile(filepath.Join(source, "state"), []byte("shared human edit"), 0600)
	private := t.TempDir()
	os.WriteFile(filepath.Join(private, "state"), []byte("target A edit"), 0600)
	next, err := w.CaptureContent(private)
	if err != nil {
		t.Fatal(err)
	}
	if err = w.SaveResourceCopy(a, next, "effect-A"); err != nil {
		t.Fatal(err)
	}
	if err = w.SaveResourceCopy(a, next, "stale-effect"); err == nil {
		t.Fatal("stale predecessor overwritten")
	}
	stillB, err := w.ResourceCopy("app", "other")
	if err != nil || stillB != b {
		t.Fatal("A changed B", err)
	}
	dest := filepath.Join(t.TempDir(), "restored-B")
	if err = w.RestoreResource("app", "other", dest); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(filepath.Join(dest, "state"))
	if string(data) != "base" {
		t.Fatal("B followed source or A")
	}
	data, _ = os.ReadFile(filepath.Join(source, "state"))
	if string(data) != "shared human edit" {
		t.Fatal("private copy commit reset shared source")
	}
}
