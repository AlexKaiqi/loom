package authority

import (
	"loom/runtime/work"
	"os"
	"path/filepath"
	"testing"
)

func fixture(t *testing.T) (*Authority, *work.Work, string) {
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
	w, err := work.Create(filepath.Join(root, "work"), h, definition)
	if err != nil {
		t.Fatal(err)
	}
	a, err := Open(filepath.Join(root, "host", "authority.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	if err = a.Register(w); err != nil {
		t.Fatal(err)
	}
	return a, w, root
}
func TestPhysicalIdentityAndActiveGrant(t *testing.T) {
	a, w, root := fixture(t)
	users := filepath.Join(root, "users")
	os.Mkdir(users, 0700)
	if err := a.Grant(w, users); err != nil {
		t.Fatal(err)
	}
	w.Events.Admit("s", "r", "input", map[string]any{})
	if _, err := a.Claim(w, "owner", false); err != nil {
		t.Fatal(err)
	}
	other := filepath.Join(root, "other")
	os.Mkdir(other, 0700)
	if err := a.Grant(w, other); err == nil {
		t.Fatal("active grant changed")
	}
	os.Rename(users, users+"-old")
	os.Mkdir(users, 0700)
	if _, err := a.Userspace(w); err == nil {
		t.Fatal("replaced identity authorized")
	}
}
func TestImportedCopyHasNoGrant(t *testing.T) {
	a, w, root := fixture(t)
	archive := filepath.Join(root, "work.tar.gz")
	if err := w.Export(archive); err != nil {
		t.Fatal(err)
	}
	copy, err := work.Import(archive, filepath.Join(root, "copy"))
	if err != nil {
		t.Fatal(err)
	}
	if err = a.Authorize(copy); err == nil {
		t.Fatal("copy inherited registration")
	}
	b, err := Open(filepath.Join(root, "newhost", "authority.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	if err = b.Authorize(copy); err == nil {
		t.Fatal("import self authorized")
	}
	if err = b.Register(copy); err != nil {
		t.Fatal(err)
	}
	if _, err = b.Userspace(copy); err == nil {
		t.Fatal("import inherited userspace")
	}
}
