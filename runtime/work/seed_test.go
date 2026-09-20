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
	fields := map[string]any{"protocol": 1}
	if initial != "" {
		fields["initial_surface"] = initial
	}
	manifest, _ := json.Marshal(fields)
	for p, data := range map[string][]byte{filepath.Join(h, "manifest.json"): manifest, filepath.Join(h, "surface", "plan.md"): []byte("- [ ] Inspect inputs\r\n"), filepath.Join(root, "definition.toml"): []byte("schema_version=2\n[harness]\npath='harness'\nargv=['unused']\n[surface]\npath='surface'\n[model]\nservice='test'\n[model.parameters]\nid='test'\napi='openai-completions'\nprovider='test'\n")} {
		if err := os.WriteFile(p, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	return root, h, filepath.Join(root, "definition.toml")
}

func TestTemplateIsIndependentOrdinaryVersionedContent(t *testing.T) {
	root, h, def := seededFixture(t, "")
	w, err := Create(filepath.Join(root, "work"), h, def)
	if err != nil {
		t.Fatal(err)
	}
	entries, err := os.ReadDir(w.Surface)
	if err != nil || len(entries) != 0 {
		t.Fatal("Harness implicitly created Surface", entries, err)
	}
	template := []byte("- [ ] Inspect inputs\r\n")
	if err = os.WriteFile(filepath.Join(w.Surface, "plan.md"), template, 0600); err != nil {
		t.Fatal(err)
	}
	ref, err := w.Snapshot("assembled template")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(w.Surface, "plan.md"), []byte("- [x] Inspect inputs\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = Open(w.Path); err != nil {
		t.Fatal(err)
	}
	destination := filepath.Join(t.TempDir(), "history")
	if err = w.Materialize(ref, destination); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(filepath.Join(destination, "surface", "plan.md"))
	if err != nil || string(got) != string(template) {
		t.Fatal("historical raw bytes changed", err)
	}
}

func TestLegacyHarnessSurfaceProvisioningRejectedBeforeCreation(t *testing.T) {
	for _, initial := range []string{"surface", "..", "../outside", "/tmp", ".", "surface/../surface", "manifest.json", "missing", "linked"} {
		t.Run(initial, func(t *testing.T) {
			root, h, def := seededFixture(t, initial)
			path := filepath.Join(root, "work")
			if _, err := Create(path, h, def); err == nil {
				t.Fatal("obsolete Harness-owned template accepted")
			}
			if _, err := os.Lstat(path); !os.IsNotExist(err) {
				t.Fatal("failed validation left a Work", err)
			}
		})
	}
}

func TestCandidateDoesNotReplaceSelectedRoundStrategy(t *testing.T) {
	w := fixture(t)
	w.Events.Admit("host", "one", "input", map[string]any{})
	first, err := w.Control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(w.Path, "harness", "candidate.txt"), []byte("new"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = Open(w.Path); err != nil {
		t.Fatal("candidate edit invalidated Work", err)
	}
	newRef, err := w.SelectHarness()
	if err != nil {
		t.Fatal(err)
	}
	rounds, _ := w.Control.Rounds()
	if rounds[0].HarnessRef != first.HarnessRef || first.HarnessRef == newRef {
		t.Fatal("active strategy changed")
	}
	if err = w.Control.PauseRound(first.ID, "boundary", map[string]any{"plan": map[string]any{}}); err != nil {
		t.Fatal(err)
	}
	resumed, err := w.Control.ResumeRound("next-owner")
	if err != nil {
		t.Fatal(err)
	}
	if resumed.HarnessRef != first.HarnessRef || resumed.Epoch != 2 {
		t.Fatal("resume changed strategy or reused epoch")
	}
	if err = w.Control.FinishRound(first.ID, first.HarnessRef); err != nil {
		t.Fatal(err)
	}
	w.Events.Admit("host", "two", "input", map[string]any{})
	next, err := w.Control.BeginRound("third-owner")
	if err != nil {
		t.Fatal(err)
	}
	if next.HarnessRef != newRef {
		t.Fatal("new Round ignored selected strategy")
	}
}
