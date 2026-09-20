// Package work owns portable files and version capture, never host authority.
package work

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"loom/runtime/store"
)

const safeGitConfig = "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = true\n\tfsync = all\n\tfsyncMethod = fsync\n[gc]\n\tauto = 0\n[maintenance]\n\tauto = false\n"
const safeGitAttributes = "* -text -filter -ident -working-tree-encoding\n"

type Work struct {
	Path       string
	ID         string
	DBPath     string
	Harness    string
	Surface    string
	Manifest   store.Object
	Definition Definition
	Events     *store.Events
	Control    *store.Control
}

func newWork(path string, manifest store.Object, definition Definition) *Work {
	db := filepath.Join(path, ".loom", "state.sqlite")
	return &Work{Path: path, ID: manifest["id"].(string), DBPath: db, Harness: filepath.Join(path, definition.Harness.Path), Surface: filepath.Join(path, definition.Surface.Path), Manifest: manifest, Definition: definition, Events: &store.Events{Path: db}, Control: &store.Control{Path: db}}
}
func Create(path, harness, definitionFile string) (result *Work, err error) {
	definitionBytes, err := os.ReadFile(definitionFile)
	if err != nil {
		return nil, err
	}
	definition, err := parseDefinition(definitionBytes)
	if err != nil {
		return nil, err
	}
	path, err = filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	harness, err = filepath.EvalSymlinks(harness)
	if err != nil {
		return nil, err
	}
	harness, err = filepath.Abs(harness)
	if err != nil {
		return nil, err
	}
	if _, err = os.Lstat(path); !os.IsNotExist(err) {
		if err == nil {
			err = os.ErrExist
		}
		return nil, err
	}
	if err = validateHarness(harness); err != nil {
		return nil, err
	}
	if err = os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return nil, err
	}
	if err = os.Mkdir(path, 0700); err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			os.RemoveAll(path)
		}
	}()
	if err = copyTree(harness, filepath.Join(path, definition.Harness.Path)); err != nil {
		return nil, err
	}
	if err = os.MkdirAll(filepath.Join(path, definition.Surface.Path), 0700); err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(path, "work.toml"), definitionBytes); err != nil {
		return nil, err
	}
	return Initialize(path)
}

func validateHarness(harness string) error {
	body, err := os.ReadFile(filepath.Join(harness, "manifest.json"))
	if err != nil {
		return err
	}
	var policy struct {
		Protocol int             `json:"protocol"`
		Events   json.RawMessage `json:"events"`
		Tools    json.RawMessage `json:"tools"`
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(&policy); err != nil {
		return err
	}
	if policy.Protocol != 1 {
		return errors.New("Harness requires protocol=1; execution argv belongs to work.toml")
	}
	return nil
}

// Initialize adopts an ordinary, already assembled directory. Only Runtime
// metadata is created; user files are never replaced and no host grant is made.
func Initialize(path string) (result *Work, err error) {
	path, err = filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	path, err = filepath.EvalSymlinks(path)
	if err != nil {
		return nil, err
	}
	meta := filepath.Join(path, ".loom")
	if _, e := os.Lstat(meta); e == nil {
		return Open(path)
	} else if !os.IsNotExist(e) {
		return nil, e
	}
	info, err := os.Lstat(filepath.Join(path, "work.toml"))
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("regular Work definition required")
	}
	definition, err := ReadDefinition(filepath.Join(path, "work.toml"))
	if err != nil {
		return nil, err
	}
	if err = validateContentRoots(path, definition); err != nil {
		return nil, err
	}
	if err = validateHarness(filepath.Join(path, definition.Harness.Path)); err != nil {
		return nil, err
	}
	if err = os.Mkdir(meta, 0700); err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			os.RemoveAll(meta)
		}
	}()
	if err = os.Mkdir(filepath.Join(meta, "records"), 0700); err != nil {
		return nil, err
	}
	id, err := store.ID()
	if err != nil {
		return nil, err
	}
	manifest := store.Object{"format": 3, "id": id}
	encoded, err := store.Canonical(manifest)
	if err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(meta, "identity.json"), []byte(encoded)); err != nil {
		return nil, err
	}
	if err = store.Initialize(filepath.Join(meta, "state.sqlite")); err != nil {
		return nil, err
	}
	w := newWork(path, manifest, definition)
	if _, err = w.gitCommand(true, "init", "--bare", "--template=", filepath.Join(meta, "versions.git")); err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(meta, "versions.git", "config"), []byte(safeGitConfig)); err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(meta, "versions.git", "info", "attributes"), []byte(safeGitAttributes)); err != nil {
		return nil, err
	}
	revision, err := w.Snapshot("initial")
	if err != nil {
		return nil, err
	}
	if err = w.Control.SelectStrategy(revision); err != nil {
		return nil, err
	}
	return w, nil
}

func validateContentRoots(path string, definition Definition) error {
	for _, root := range []string{definition.Harness.Path, definition.Surface.Path} {
		name := filepath.Join(path, root)
		resolved, e := filepath.EvalSymlinks(name)
		if e != nil || resolved != name {
			return errors.New("invalid or symbolic Work content root")
		}
		info, e := os.Lstat(name)
		if e != nil || !info.IsDir() {
			return errors.New("invalid Work content root")
		}
	}
	return nil
}

func Open(path string) (*Work, error) {
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return nil, err
	}
	path, err = filepath.Abs(resolved)
	if err != nil {
		return nil, err
	}
	if _, legacyErr := os.Lstat(filepath.Join(path, "work.json")); legacyErr == nil {
		return nil, errors.New("unsupported Work format: legacy layout")
	}
	for _, relative := range []string{"work.toml", ".loom", ".loom/identity.json", ".loom/versions.git", ".loom/state.sqlite", ".loom/records"} {
		info, err := os.Lstat(filepath.Join(path, relative))
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, errors.New("symbolic Work boundary")
		}
	}
	encoded, err := os.ReadFile(filepath.Join(path, ".loom", "identity.json"))
	if err != nil {
		return nil, err
	}
	manifest, err := store.DecodeObject(string(encoded))
	if err != nil {
		return nil, err
	}
	if manifest["format"] != json.Number("3") {
		return nil, errors.New("unsupported Work format")
	}
	if id, ok := manifest["id"].(string); !ok || id == "" {
		return nil, errors.New("Work ID required")
	}
	db, err := store.OpenDB(filepath.Join(path, ".loom", "state.sqlite"))
	if err != nil {
		return nil, err
	}
	defer db.Close()
	var version int
	if err = db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		return nil, err
	}
	if version != 3 {
		return nil, errors.New("unsupported database format")
	}
	w := newWork(path, manifest, Definition{})
	ref, err := w.Control.SelectedStrategy()
	if err != nil {
		return nil, err
	}
	w, err = w.ForStrategy(ref)
	if err != nil {
		return nil, err
	}
	if err = w.ValidateResources(); err != nil {
		return nil, err
	}
	return w, nil
}
func (w *Work) git(args ...string) (string, error) { return w.gitCommand(false, args...) }
func (w *Work) gitCommand(initialize bool, args ...string) (string, error) {
	base := []string{"-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"}
	if !initialize {
		repository := filepath.Join(w.Path, ".loom", "versions.git")
		content, err := os.ReadFile(filepath.Join(repository, "config"))
		if err != nil {
			return "", err
		}
		if string(content) != safeGitConfig {
			return "", errors.New("unsafe version repository configuration")
		}
		attributes, err := os.ReadFile(filepath.Join(repository, "info", "attributes"))
		if err != nil || string(attributes) != safeGitAttributes {
			return "", errors.New("unsafe version repository attributes")
		}
		for _, name := range []string{"objects/info/alternates", "objects/info/http-alternates"} {
			if _, err = os.Lstat(filepath.Join(repository, name)); !os.IsNotExist(err) {
				return "", errors.New("unsafe version object alternate")
			}
		}
		base = append(base, "--git-dir="+repository, "--work-tree="+w.Surface)
	}
	command := exec.Command("git", append(base, args...)...)
	command.Dir = w.Path
	command.Env = []string{"GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null", "GIT_AUTHOR_NAME=Loom", "GIT_AUTHOR_EMAIL=loom@local", "GIT_COMMITTER_NAME=Loom", "GIT_COMMITTER_EMAIL=loom@local"}
	for _, key := range []string{"PATH", "LANG", "TMPDIR"} {
		if value, ok := os.LookupEnv(key); ok {
			command.Env = append(command.Env, key+"="+value)
		}
	}
	result, err := command.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("git: %w: %s", err, result)
	}
	return strings.TrimSpace(string(result)), nil
}
func (w *Work) Artifact(value []byte, suffix string) (store.Object, error) {
	media := map[string]string{".json": "application/json", ".txt": "text/plain", ".bin": "application/octet-stream"}[suffix]
	if media == "" {
		return nil, errors.New("invalid artifact extension")
	}
	ref, err := (store.Records{Directory: w.ArtifactsDir()}).Put(value, media)
	if err != nil {
		return nil, err
	}
	return store.Object{"path": ".loom/records/" + ref.SHA256, "sha256": ref.SHA256, "size_bytes": ref.SizeBytes, "media_type": ref.MediaType}, nil
}

func (w *Work) ArtifactsDir() string { return filepath.Join(w.Path, ".loom", "records") }
