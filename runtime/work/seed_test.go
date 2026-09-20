package work

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func seededFixture(t *testing.T, initial string) (string, string, string) {
	t.Helper()
	root := t.TempDir()
	h := filepath.Join(root, "harness")
	if err := os.MkdirAll(filepath.Join(h, "surface"), 0700); err != nil {
		t.Fatal(err)
	}
	manifest, _ := json.Marshal(map[string]any{"protocol": 1, "command": []string{"unused"}, "initial_surface": initial})
	for p, data := range map[string][]byte{
		filepath.Join(h, "manifest.json"):      manifest,
		filepath.Join(h, "surface", "plan.md"): []byte("- [ ] Inspect inputs\r\n"),
		filepath.Join(root, "definition.toml"): []byte("[model]\nservice='test'\n[model.definition]\nid='test'\napi='openai-completions'\nprovider='test'\n"),
	} {
		if err := os.WriteFile(p, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	return root, h, filepath.Join(root, "definition.toml")
}

func TestInitialSurfaceIsOrdinaryVersionedContent(t *testing.T) {
	root, h, def := seededFixture(t, "surface")
	w, err := Create(filepath.Join(root, "work"), h, def)
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(w.Surface, "plan.md"))
	if err != nil || string(data) != "- [ ] Inspect inputs\r\n" {
		t.Fatal("seed bytes not preserved", err)
	}
	if got, err := w.git("show", "HEAD:plan.md"); err != nil || got != "- [ ] Inspect inputs" {
		t.Fatal("seed missing from initial snapshot", err)
	}
	if err = os.WriteFile(filepath.Join(w.Surface, "plan.md"), []byte("- [x] Inspect inputs\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = Open(w.Path); err != nil {
		t.Fatal("ordinary Surface edits changed fixed Harness", err)
	}
	fixed, err := os.ReadFile(filepath.Join(w.Path, "harness", "surface", "plan.md"))
	if err != nil || string(fixed) != string(data) {
		t.Fatal("editing Surface also edited fixed template", err)
	}
}

func TestInitialSurfaceRejectsEscapesBeforeCreation(t *testing.T) {
	for _, initial := range []string{"..", "../outside", "/tmp", ".", "surface/../surface", "manifest.json", "missing", "linked"} {
		t.Run(initial, func(t *testing.T) {
			root, h, def := seededFixture(t, initial)
			if initial == "linked" {
				if err := os.Symlink(filepath.Join(h, "surface"), filepath.Join(h, "linked")); err != nil {
					t.Fatal(err)
				}
			}
			path := filepath.Join(root, "work")
			if _, err := Create(path, h, def); err == nil {
				t.Fatal("invalid seed accepted")
			}
			if _, err := os.Lstat(path); !os.IsNotExist(err) {
				t.Fatal("failed validation left a Work", err)
			}
		})
	}
}
