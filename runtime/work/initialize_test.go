package work

import (
	"loom/runtime/store"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestInitializeOrdinaryDirectoryPreservesFilesAndIdentity(t *testing.T) {
	root, h, def := seededFixture(t, "")
	directory := filepath.Join(root, "assembled")
	if err := os.Mkdir(directory, 0700); err != nil {
		t.Fatal(err)
	}
	if err := copyTree(h, filepath.Join(directory, "harness")); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(directory, "surface"), 0700); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(def)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(directory, "work.toml"), raw, 0600); err != nil {
		t.Fatal(err)
	}
	note := []byte("assembled before registration\r\n")
	if err = os.WriteFile(filepath.Join(directory, "surface", "main.md"), note, 0640); err != nil {
		t.Fatal(err)
	}
	w, err := Initialize(directory)
	if err != nil {
		t.Fatal(err)
	}
	again, err := Initialize(directory)
	if err != nil || again.ID != w.ID {
		t.Fatal("registration changed identity", err)
	}
	ref, err := w.Control.SelectedStrategy()
	if err != nil {
		t.Fatal(err)
	}
	saved := filepath.Join(root, "saved")
	if err = w.Materialize(ref, saved); err != nil {
		t.Fatal(err)
	}
	observed, err := os.ReadFile(filepath.Join(saved, "surface", "main.md"))
	if err != nil || string(observed) != string(note) {
		t.Fatal("initial content lost", err)
	}
	info, err := os.Stat(filepath.Join(saved, "surface", "main.md"))
	if err != nil || info.Mode().Perm() != 0640 {
		t.Fatal("mode lost", err)
	}
}

func TestInvalidCandidateDoesNotInvalidateSelectedDefinition(t *testing.T) {
	w := fixture(t)
	original, err := w.Control.SelectedStrategy()
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(w.Path, "work.toml")
	if err = os.WriteFile(path, []byte("invalid TOML !"), 0600); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(w.Path)
	if err != nil {
		t.Fatal("candidate broke access to committed state", err)
	}
	if _, err = reopened.SelectHarness(); err == nil {
		t.Fatal("invalid candidate selected")
	}
	actual, err := w.Control.SelectedStrategy()
	if err != nil || actual != original {
		t.Fatal("failed selection replaced revision", err)
	}
	if reopened.Definition.Model.Service != "test" {
		t.Fatal("running definition replaced")
	}
}

func TestDefinitionSelectionPinsWholeRoundAndResume(t *testing.T) {
	w := fixture(t)
	if _, err := w.Events.Admit("host", "first", "input", store.Object{}); err != nil {
		t.Fatal(err)
	}
	first, err := w.Control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(w.Path, "work.toml")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	candidate := strings.Replace(string(raw), `service="test"`, `service="replacement"`, 1)
	candidate = strings.Replace(candidate, "argv=['unused']", "argv=['python3','replacement.py']", 1)
	if err = os.WriteFile(path, []byte(candidate), 0600); err != nil {
		t.Fatal(err)
	}
	before, err := Open(w.Path)
	if err != nil || before.Definition.Model.Service != "test" {
		t.Fatal("candidate activated implicitly", err)
	}
	chosen, err := before.SelectHarness()
	if err != nil {
		t.Fatal(err)
	}
	after, err := Open(w.Path)
	if err != nil || after.Definition.Model.Service != "replacement" {
		t.Fatal("selection not visible", err)
	}
	if err = w.Control.PauseRound(first.ID, "pause", store.Object{"plan": store.Object{}}); err != nil {
		t.Fatal(err)
	}
	resumed, err := w.Control.ResumeRound("next-owner")
	if err != nil {
		t.Fatal(err)
	}
	fixed, err := after.ForStrategy(resumed.HarnessRef)
	if err != nil || fixed.Definition.Model.Service != "test" || fixed.Definition.Harness.Argv[0] != "unused" {
		t.Fatal("resume mixed definitions", err)
	}
	if err = w.Control.FinishRound(first.ID, first.HarnessRef); err != nil {
		t.Fatal(err)
	}
	if _, err = w.Events.Admit("host", "second", "input", store.Object{}); err != nil {
		t.Fatal(err)
	}
	if _, err = w.Control.BeginRoundSelected("racer", first.HarnessRef); err == nil {
		t.Fatal("stale preflight accepted")
	}
	next, err := w.Control.BeginRoundSelected("new-owner", chosen)
	if err != nil {
		t.Fatal(err)
	}
	fixed, err = after.ForStrategy(next.HarnessRef)
	if err != nil || fixed.Definition.Model.Service != "replacement" {
		t.Fatal("new Round did not adopt selection", err)
	}
}

func TestInitializeRefusesSymbolicRootWithoutDestroyingAssembly(t *testing.T) {
	root, h, def := seededFixture(t, "")
	directory := filepath.Join(root, "assembly")
	if err := os.Mkdir(directory, 0700); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(def)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(directory, "work.toml"), raw, 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.Symlink(h, filepath.Join(directory, "harness")); err != nil {
		t.Fatal(err)
	}
	if err = os.Mkdir(filepath.Join(directory, "surface"), 0700); err != nil {
		t.Fatal(err)
	}
	if _, err = Initialize(directory); err == nil {
		t.Fatal("unresolved external source implicitly authorized")
	}
	if got, e := os.ReadFile(filepath.Join(directory, "work.toml")); e != nil || string(got) != string(raw) {
		t.Fatal("assembly altered", e)
	}
	if _, err = os.Lstat(filepath.Join(directory, ".loom")); !os.IsNotExist(err) {
		t.Fatal("failed assembly initialized", err)
	}
}

func TestDefinitionChangeAfterValidationCannotPublishStrategy(t *testing.T) {
	w := fixture(t)
	path := filepath.Join(w.Path, "work.toml")
	validated, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	prior, err := w.CurrentContent()
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(path, append(append([]byte(nil), validated...), []byte("\n# newer candidate\n")...), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = w.snapshot("stale candidate", validated); err == nil {
		t.Fatal("configuration changed after validation was accepted")
	}
	current, err := w.CurrentContent()
	if err != nil || current != prior {
		t.Fatal("rejected candidate published a content head", err)
	}
	selected, err := w.Control.SelectedStrategy()
	if err != nil || selected != prior {
		t.Fatal("rejected candidate activated", err)
	}
}
