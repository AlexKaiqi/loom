package work

import (
	"archive/tar"
	"compress/gzip"
	"encoding/json"
	"errors"
	"io"
	"loom/runtime/filesystem"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"loom/runtime/store"
)

func TestPortableLayoutAndDefinitionBinding(t *testing.T) {
	w := fixture(t)
	for _, p := range []string{"work.toml", "harness", "surface", ".loom/identity.json", ".loom/state.sqlite", ".loom/versions.git", ".loom/records"} {
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
	if reopened, err := Open(w.Path); err != nil || reopened.ID != w.ID || reopened.Definition.Model.Service != w.Definition.Model.Service {
		t.Fatal("candidate declaration changed Work identity or active definition", err)
	}
}

func TestDefinitionRejectsHostTransportSecretsAndUnknownFields(t *testing.T) {
	base := "schema_version=2\n[harness]\npath='harness'\nargv=['unused']\n[surface]\npath='surface'\n[model]\nservice='test'\n[model.parameters]\nid='model'\napi='openai-completions'\nprovider='test'\n"
	for _, extra := range []string{"baseUrl='https://old-host'", "headers={Authorization='secret'}", "apiKey='secret'", "[model.parameters.compat]\nsecret='value'", "[unexpected]\nvalue='x'"} {
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
	snapshot, err := w.BindResource("app", source)
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
	if err = imported.RestoreResource("app", "", destination); err != nil {
		t.Fatal(err)
	}
	if err = verifyResource(imported, "app", destination); err != nil {
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
	if err = imported.RestoreResource("app", "", destination); err == nil {
		t.Fatal("existing restore destination overwritten")
	}
	if err = imported.RestoreResource("app", "", filepath.Join(imported.Path, "illegal")); err == nil {
		t.Fatal("Userspace restored inside Work")
	}
	if err = os.WriteFile(filepath.Join(destination, "binary"), []byte("changed"), 0640); err != nil {
		t.Fatal(err)
	}
	if err = verifyResource(imported, "app", destination); err == nil {
		t.Fatal("changed Userspace verified")
	}
}

func TestUserspaceSnapshotMissingOrCorruptCannotExport(t *testing.T) {
	for _, attack := range []string{"missing-reference", "changed-reference", "missing-archive", "changed-archive"} {
		t.Run(attack, func(t *testing.T) {
			w := fixture(t)
			source := t.TempDir()
			snapshot, err := w.BindResource("app", source)
			if err != nil {
				t.Fatal(err)
			}
			archive := filepath.Join(w.ArtifactsDir(), snapshot.BaseRef.SHA256)
			switch attack {
			case "missing-reference", "changed-reference":
				db, e := store.OpenDB(w.DBPath)
				if e != nil {
					t.Fatal(e)
				}
				statement := "DELETE FROM resource_sources WHERE alias='app'"
				if attack == "changed-reference" {
					statement = "UPDATE resource_sources SET source='{}' WHERE alias='app'"
				}
				_, e = db.Exec(statement)
				db.Close()
				if e == nil {
					t.Fatal("immutable resource reference modified")
				}
				return
			case "missing-archive":
				err = os.Remove(archive)
			case "changed-archive":
				os.Chmod(archive, 0600)
				err = os.WriteFile(archive, []byte("bad"), 0600)
			}
			if err != nil {
				t.Fatal(err)
			}
			if _, err = w.ResourceSource("app"); err == nil {
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

// Publishing an immutable candidate is not a copy-version commit.
func TestUnpublishedSnapshotObjectsPreservePreviousReference(t *testing.T) {
	w := fixture(t)
	directory := t.TempDir()
	file := filepath.Join(directory, "state")
	os.WriteFile(file, []byte("before"), 0600)
	initial, err := w.BindResource("app", directory)
	if err != nil {
		t.Fatal(err)
	}
	copy, err := w.ResourceCopy("app", "default")
	if err != nil {
		t.Fatal(err)
	}
	os.WriteFile(file, []byte("after"), 0600)
	candidate, err := w.CaptureContent(directory)
	if err != nil {
		t.Fatal(err)
	}
	if initial.BaseRef == candidate {
		t.Fatal("fixture did not change")
	}
	opened, err := Open(w.Path)
	if err != nil {
		t.Fatal(err)
	}
	observed, err := opened.ResourceCopy("app", "default")
	if err != nil || observed != copy {
		t.Fatal("unpublished candidate became current", err)
	}
	destination := filepath.Join(t.TempDir(), "restored")
	if err = opened.RestoreResource("app", "default", destination); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(destination, "state"))
	if err != nil || string(data) != "before" {
		t.Fatal(string(data), err)
	}
	if err = opened.Export(filepath.Join(t.TempDir(), "usable.tar.gz")); err != nil {
		t.Fatal(err)
	}
}
func verifyResource(w *Work, alias, directory string) error {
	source, err := w.ResourceSource(alias)
	if err != nil {
		return err
	}
	digest, err := filesystem.TreeDigest(directory)
	if err != nil {
		return err
	}
	if source == nil || digest != source.BaseRef.SHA256 {
		return errors.New("resource differs from initial version")
	}
	return nil
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
