// Package work owns portable files and version capture, never host authority.
package work

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"loom/runtime/store"
)

const safeGitConfig = "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = true\n"
const safeGitAttributes = "* -text -filter -ident -working-tree-encoding\n"

type Work struct {
	Path       string
	ID         string
	DBPath     string
	Surface    string
	Manifest   store.Object
	Definition Definition
	Events     *store.Events
	Control    *store.Control
}

func newWork(path string, manifest store.Object, definition Definition) *Work {
	db := filepath.Join(path, ".loom", "state.sqlite")
	return &Work{Path: path, ID: manifest["id"].(string), DBPath: db, Surface: filepath.Join(path, "surface"), Manifest: manifest, Definition: definition, Events: &store.Events{Path: db}, Control: &store.Control{Path: db}}
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
	body, err := os.ReadFile(filepath.Join(harness, "manifest.json"))
	if err != nil {
		return nil, err
	}
	var policy struct {
		Protocol       int      `json:"protocol"`
		Command        []string `json:"command"`
		InitialSurface string   `json:"initial_surface"`
	}
	if err = json.Unmarshal(body, &policy); err != nil {
		return nil, err
	}
	if policy.Protocol != 1 || len(policy.Command) == 0 || policy.Command[0] == "" {
		return nil, errors.New("Harness requires protocol=1 and command argv")
	}
	if policy.InitialSurface != "" {
		relative := policy.InitialSurface
		if filepath.IsAbs(relative) || filepath.Clean(relative) != relative || relative == "." || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
			return nil, errors.New("initial_surface must name a directory inside the Harness")
		}
		info, err := os.Lstat(filepath.Join(harness, relative))
		if err != nil || !info.IsDir() {
			return nil, errors.New("initial_surface must be a real Harness directory")
		}
	}
	entries, err := Files(harness)
	if err != nil {
		return nil, err
	}
	harnessDigest, err := store.Digest(entries)
	if err != nil {
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
	if err = copyTree(harness, filepath.Join(path, "harness")); err != nil {
		return nil, err
	}
	for _, relative := range []string{"surface", ".loom/artifacts", ".loom/dependencies"} {
		if err = os.MkdirAll(filepath.Join(path, relative), 0700); err != nil {
			return nil, err
		}
	}
	if policy.InitialSurface != "" {
		if err = copyTree(filepath.Join(harness, policy.InitialSurface), filepath.Join(path, "surface")); err != nil {
			return nil, err
		}
	}
	id, err := store.ID()
	if err != nil {
		return nil, err
	}
	manifest := store.Object{"format": 3, "id": id, "harness_digest": harnessDigest, "definition_digest": digestBytes(definitionBytes)}
	encoded, err := store.Canonical(manifest)
	if err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(path, ".loom", "identity.json"), []byte(encoded)); err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(path, "work.toml"), definitionBytes); err != nil {
		return nil, err
	}
	if err = store.Initialize(filepath.Join(path, ".loom", "state.sqlite")); err != nil {
		return nil, err
	}
	path, err = filepath.EvalSymlinks(path)
	if err != nil {
		return nil, err
	}
	w := newWork(path, manifest, definition)
	if _, err = w.gitCommand(true, "init", "--bare", "--template=", filepath.Join(path, ".loom", "versions.git")); err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(path, ".loom", "versions.git", "config"), []byte(safeGitConfig)); err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(path, ".loom", "versions.git", "info", "attributes"), []byte(safeGitAttributes)); err != nil {
		return nil, err
	}
	if _, err = w.Snapshot("initial"); err != nil {
		return nil, err
	}
	return w, nil
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
	for _, relative := range []string{"work.toml", "harness", "surface", ".loom", ".loom/identity.json", ".loom/versions.git", ".loom/state.sqlite", ".loom/artifacts", ".loom/dependencies"} {
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
	definitionBytes, err := os.ReadFile(filepath.Join(path, "work.toml"))
	if err != nil {
		return nil, err
	}
	definition, err := parseDefinition(definitionBytes)
	if err != nil {
		return nil, err
	}
	if digestBytes(definitionBytes) != manifest["definition_digest"] {
		return nil, errors.New("fixed Work definition changed")
	}
	entries, err := Files(filepath.Join(path, "harness"))
	if err != nil {
		return nil, err
	}
	digest, err := store.Digest(entries)
	if err != nil {
		return nil, err
	}
	if digest != manifest["harness_digest"] {
		return nil, errors.New("fixed Harness content changed")
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
	if version != 2 {
		return nil, errors.New("unsupported database format")
	}
	w := newWork(path, manifest, definition)
	if _, err = w.UserspaceSnapshot(); err != nil {
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
	command.Dir = w.Surface
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
func (w *Work) Snapshot(message string) (string, error) {
	if _, err := Files(w.Surface); err != nil {
		return "", err
	}
	if err := filepath.WalkDir(w.Surface, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.Name() == ".git" {
			return errors.New("nested Git repositories are not ordinary Surface files")
		}
		return nil
	}); err != nil {
		return "", err
	}
	if _, err := w.git("add", "--force", "--all", "--", "."); err != nil {
		return "", err
	}
	if _, err := w.git("commit", "--allow-empty", "-m", message); err != nil {
		return "", err
	}
	return w.git("rev-parse", "HEAD")
}
func (w *Work) Artifact(value []byte, suffix string) (store.Object, error) {
	if suffix != ".json" && suffix != ".txt" && suffix != ".bin" {
		return nil, errors.New("invalid artifact extension")
	}
	hash := sha256.Sum256(value)
	sha := hex.EncodeToString(hash[:])
	relative := ".loom/artifacts/" + sha + suffix
	if err := Save(filepath.Join(w.Path, relative), value); err != nil {
		return nil, err
	}
	return store.Object{"path": relative, "sha256": sha, "size": len(value)}, nil
}

func (w *Work) ArtifactsDir() string { return filepath.Join(w.Path, ".loom", "artifacts") }
