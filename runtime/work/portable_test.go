package work

import (
	"archive/tar"
	"compress/gzip"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"loom/runtime/store"
)

func TestPortableLayoutAndDefinitionBinding(t *testing.T) {
	w := fixture(t)
	for _, p := range []string{"work.toml", "harness", "surface", ".loom/identity.json", ".loom/state.sqlite", ".loom/versions.git", ".loom/artifacts", ".loom/dependencies"} {
		if _, err := os.Stat(filepath.Join(w.Path, p)); err != nil {
			t.Fatal(p, err)
		}
	}
	for _, p := range []string{"work.json", "ledger", "artifacts", "surface/content", "surface/versions.git"} {
		if _, err := os.Stat(filepath.Join(w.Path, p)); !os.IsNotExist(err) {
			t.Fatal("legacy path remains", p, err)
		}
	}
	p := filepath.Join(w.Path, "work.toml")
	b, _ := os.ReadFile(p)
	os.WriteFile(p, append(b, []byte("\n# changed after creation\n")...), 0600)
	if _, err := Open(w.Path); err == nil {
		t.Fatal("changed declaration accepted")
	}
}

func TestDefinitionRejectsHostTransportSecretsAndUnknownFields(t *testing.T) {
	base := "[model]\nservice='test'\n[model.definition]\nid='model'\napi='openai-completions'\nprovider='test'\n"
	for _, extra := range []string{"baseUrl='https://old-host'", "headers={Authorization='secret'}", "apiKey='secret'", "[model.definition.compat]\nsecret='value'", "[unexpected]\nvalue='x'"} {
		if _, err := parseDefinition([]byte(base + extra)); err == nil {
			t.Fatal("accepted forbidden declaration", extra)
		}
	}
	if _, err := parseDefinition([]byte(base)); err != nil {
		t.Fatal(err)
	}
}

func TestUserspaceSnapshotRestoresPortableExactTree(t *testing.T) {
	w := fixture(t)
	source := filepath.Join(t.TempDir(), "source")
	if err := os.Mkdir(source, 0750); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(source, "empty"), 0711); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(source, "run"), []byte("#!/bin/sh\nprintf 'retained'\n"), 0751); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(source, "binary"), []byte{0, 1, 2, 255}, 0640); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("run", filepath.Join(source, "alias")); err != nil {
		t.Fatal(err)
	}
	snapshot, err := w.CaptureUserspace(source)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(snapshot)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), source) || strings.Contains(string(encoded), "inode") || strings.Contains(string(encoded), "device") {
		t.Fatal("host identity leaked", string(encoded))
	}
	archive := filepath.Join(t.TempDir(), "portable.tar.gz")
	if err = w.Export(archive); err != nil {
		t.Fatal(err)
	}
	imported, err := Import(archive, filepath.Join(t.TempDir(), "imported"))
	if err != nil {
		t.Fatal(err)
	}
	if err = os.RemoveAll(source); err != nil {
		t.Fatal(err)
	}
	destination := filepath.Join(t.TempDir(), "restored")
	if err = imported.RestoreUserspace(destination); err != nil {
		t.Fatal(err)
	}
	if err = imported.VerifyUserspace(destination); err != nil {
		t.Fatal(err)
	}
	for path, mode := range map[string]os.FileMode{"": 0750, "empty": 0711, "run": 0751, "binary": 0640} {
		info, err := os.Stat(filepath.Join(destination, path))
		if err != nil || info.Mode().Perm() != mode {
			t.Fatal(path, info, err)
		}
	}
	if link, err := os.Readlink(filepath.Join(destination, "alias")); err != nil || link != "run" {
		t.Fatal(link, err)
	}
	if err = imported.RestoreUserspace(destination); err == nil {
		t.Fatal("existing restore destination overwritten")
	}
	if err = imported.RestoreUserspace(filepath.Join(imported.Path, "illegal")); err == nil {
		t.Fatal("Userspace restored inside Work")
	}
	if err = os.WriteFile(filepath.Join(destination, "binary"), []byte("changed"), 0640); err != nil {
		t.Fatal(err)
	}
	if err = imported.VerifyUserspace(destination); err == nil {
		t.Fatal("changed Userspace verified")
	}
}

func TestUserspaceSnapshotMissingOrCorruptCannotExport(t *testing.T) {
	for _, attack := range []string{"missing-reference", "changed-reference", "missing-archive", "changed-archive"} {
		t.Run(attack, func(t *testing.T) {
			w := fixture(t)
			source := t.TempDir()
			snapshot, err := w.CaptureUserspace(source)
			if err != nil {
				t.Fatal(err)
			}
			archive := filepath.Join(w.Path, filepath.FromSlash(snapshot.Archive.Path))
			switch attack {
			case "missing-reference":
				err = os.Remove(w.dependencyPath(w.Manifest["userspace_snapshot_digest"].(string)))
			case "changed-reference":
				err = os.WriteFile(w.dependencyPath(w.Manifest["userspace_snapshot_digest"].(string)), []byte(`{}`), 0600)
			case "missing-archive":
				err = os.Remove(archive)
			case "changed-archive":
				err = os.WriteFile(archive, []byte("bad"), 0600)
			}
			if err != nil {
				t.Fatal(err)
			}
			if _, err = w.UserspaceSnapshot(); err == nil {
				t.Fatal("corrupt dependency validated")
			}
			if err = w.Export(filepath.Join(t.TempDir(), "corrupt.tar.gz")); err == nil {
				t.Fatal("corrupt dependency exported")
			}
		})
	}
}

func TestUnconfirmedAndUnknownPauseCannotExport(t *testing.T) {
	for _, unknown := range []bool{false, true} {
		w := fixture(t)
		w.Events.Admit("host", "request", "input", store.Object{})
		r, err := w.Control.BeginRound("owner")
		if err != nil {
			t.Fatal(err)
		}
		if unknown {
			e, err := w.Control.PrepareEffect(r.ID, "tool:0:call", "sandbox", store.Object{"target": "userspace"})
			if err != nil {
				t.Fatal(err)
			}
			if err = w.Control.UnknownEffect(e.ID, "lost connection"); err != nil {
				t.Fatal(err)
			}
		}
		if err = w.Control.PauseRound(r.ID, "unconfirmed", nil); err != nil {
			t.Fatal(err)
		}
		if err = w.Export(filepath.Join(t.TempDir(), "invalid.tar.gz")); err == nil {
			t.Fatal("unconfirmed pause exported")
		}
	}
}

func TestExportRetainsHumanFilesOutsideSurface(t *testing.T) {
	w := fixture(t)
	if err := os.WriteFile(filepath.Join(w.Path, "README.md"), []byte("Human guide"), 0600); err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(t.TempDir(), "work.tar.gz")
	if err := w.Export(archive); err != nil {
		t.Fatal(err)
	}
	imported, err := Import(archive, filepath.Join(t.TempDir(), "copy"))
	if err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(imported.Path, "README.md"))
	if err != nil || string(content) != "Human guide" {
		t.Fatal(string(content), err)
	}
}

func TestExportRejectsChangedFileModeWithUnchangedBytes(t *testing.T) {
	w := fixture(t)
	filename := filepath.Join(w.Surface, "run.sh")
	if err := os.WriteFile(filename, []byte("#!/bin/sh\n"), 0751); err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(t.TempDir(), "original.tar.gz")
	if err := w.Export(archive); err != nil {
		t.Fatal(err)
	}
	input, err := os.Open(archive)
	if err != nil {
		t.Fatal(err)
	}
	defer input.Close()
	compressed, err := gzip.NewReader(input)
	if err != nil {
		t.Fatal(err)
	}
	defer compressed.Close()
	reader := tar.NewReader(compressed)
	damaged := filepath.Join(t.TempDir(), "damaged.tar.gz")
	output, err := os.Create(damaged)
	if err != nil {
		t.Fatal(err)
	}
	gzipWriter := gzip.NewWriter(output)
	writer := tar.NewWriter(gzipWriter)
	changed := false
	for {
		header, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if header.Name == "work/surface/run.sh" {
			header.Mode = 0600
			changed = true
		}
		if err = writer.WriteHeader(header); err != nil {
			t.Fatal(err)
		}
		if _, err = io.Copy(writer, reader); err != nil {
			t.Fatal(err)
		}
	}
	writer.Close()
	gzipWriter.Close()
	output.Close()
	if !changed {
		t.Fatal("fixture did not alter a file mode")
	}
	if _, err = Import(damaged, filepath.Join(t.TempDir(), "imported")); err == nil {
		t.Fatal("changed executable permission passed export validation")
	}
}

// A crash between writing immutable objects and publishing identity must leave
// the previous complete dependency usable. The identity rename is the commit.
func TestUnpublishedSnapshotObjectsPreservePreviousReference(t *testing.T) {
	w := fixture(t)
	directory := t.TempDir()
	file := filepath.Join(directory, "state")
	if err := os.WriteFile(file, []byte("before"), 0600); err != nil {
		t.Fatal(err)
	}
	oldSnapshot, err := w.CaptureUserspace(directory)
	if err != nil {
		t.Fatal(err)
	}
	identityPath := filepath.Join(w.Path, ".loom", "identity.json")
	oldIdentity, err := os.ReadFile(identityPath)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(file, []byte("after"), 0600); err != nil {
		t.Fatal(err)
	}
	newSnapshot, err := w.CaptureUserspace(directory)
	if err != nil {
		t.Fatal(err)
	}
	if oldSnapshot.TreeDigest == newSnapshot.TreeDigest {
		t.Fatal("fixture did not change")
	}
	// Reconstruct exactly the durable state before the final atomic publish:
	// old identity, both versions' fsynced immutable files.
	if err = Save(identityPath, oldIdentity); err != nil {
		t.Fatal(err)
	}
	opened, err := Open(w.Path)
	if err != nil {
		t.Fatal(err)
	}
	observed, err := opened.UserspaceSnapshot()
	if err != nil {
		t.Fatal(err)
	}
	if observed.TreeDigest != oldSnapshot.TreeDigest {
		t.Fatal("unpublished version became current")
	}
	destination := filepath.Join(t.TempDir(), "restored")
	if err = opened.RestoreUserspace(destination); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(destination, "state"))
	if err != nil || string(content) != "before" {
		t.Fatal(string(content), err)
	}
	if err = opened.Export(filepath.Join(t.TempDir(), "usable.tar.gz")); err != nil {
		t.Fatal(err)
	}
}

func TestConfirmedPausePortable(t *testing.T) {
	w := fixture(t)
	w.Events.Admit("host", "request", "input", store.Object{"text": "pending"})
	r, err := w.Control.BeginRound("oldhost")
	if err != nil {
		t.Fatal(err)
	}
	cp := store.Object{"plan": store.Object{"context": store.Object{"messages": []any{}}}}
	if err = w.Control.PauseRound(r.ID, "budget", cp); err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(t.TempDir(), "work.tar.gz")
	if err = w.Export(archive); err != nil {
		t.Fatal(err)
	}
	imported, err := Import(archive, filepath.Join(t.TempDir(), "new-work"))
	if err != nil {
		t.Fatal(err)
	}
	resumed, err := imported.Control.ResumeRound("newhost")
	if err != nil {
		t.Fatal(err)
	}
	if resumed.ID != r.ID || resumed.Checkpoint == nil {
		t.Fatal("lost continuation", resumed)
	}
	pending, _ := imported.Events.Pending()
	if len(pending) != 1 {
		t.Fatal("lost pending", pending)
	}
}
