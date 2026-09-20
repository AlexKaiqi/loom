package work

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"loom/runtime/filesystem"
	"loom/runtime/store"
)

var fullGitObject = regexp.MustCompile(`^(?:[0-9a-f]{40}|[0-9a-f]{64})$`)

func (w *Work) gitBytes(kind, object string) ([]byte, error) {
	if !fullGitObject.MatchString(object) {
		return nil, errors.New("invalid immutable Git object")
	}
	if _, err := w.git("rev-parse", "--git-dir"); err != nil {
		return nil, err
	}
	cmd := exec.Command("git", "--git-dir="+filepath.Join(w.Path, ".loom", "versions.git"), "cat-file", kind, object)
	cmd.Env = []string{"PATH=" + os.Getenv("PATH"), "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null"}
	return cmd.Output()
}

// Materialize restores literal bytes and the separate file manifest. It neither
// checks out a mutable branch nor runs filters, hooks or code from the snapshot.
// The destination must be a new directory owned by the Runtime.
func (w *Work) Materialize(ref, destination string) error {
	commit, err := w.gitBytes("commit", ref)
	if err != nil {
		return err
	}
	parts := strings.Split(string(commit), "\nfile-manifest: ")
	if len(parts) != 2 {
		return errors.New("content snapshot has no unique file manifest")
	}
	digest := strings.TrimSpace(parts[1])
	if len(digest) != 64 {
		return errors.New("invalid file manifest reference")
	}
	info, err := os.Lstat(filepath.Join(w.ArtifactsDir(), digest))
	if err != nil {
		return err
	}
	raw, err := (store.Records{Directory: w.ArtifactsDir()}).Get(store.RecordRef{SHA256: digest, SizeBytes: strconv.FormatInt(info.Size(), 10), MediaType: "application/vnd.loom.file-manifest+json"})
	if err != nil {
		return err
	}
	var entries []FileEntry
	if err = json.Unmarshal(raw, &entries); err != nil {
		return err
	}
	if err = w.verifyManifestTree(ref, entries); err != nil {
		return err
	}
	if err = os.Mkdir(destination, 0700); err != nil {
		return err
	}
	successful := false
	defer func() {
		if !successful {
			os.RemoveAll(destination)
		}
	}()
	seen := map[string]bool{}
	for _, entry := range entries {
		name := entry.Path
		if filepath.ToSlash(filepath.Clean(name)) != name || filepath.IsAbs(name) || !filesystem.Inside(destination, filepath.Join(destination, name)) || name == "." || seen[name] || entry.Mode > 0777 {
			return errors.New("invalid file manifest member")
		}
		if name != "work.toml" && name != "harness" && name != "surface" && !strings.HasPrefix(name, "harness/") && !strings.HasPrefix(name, "surface/") {
			return errors.New("file manifest member outside Work content")
		}
		seen[name] = true
	}
	// Creating all directories before links prevents link-assisted writes.
	if err = os.MkdirAll(filepath.Join(destination, "harness"), 0700); err != nil {
		return err
	}
	if err = os.MkdirAll(filepath.Join(destination, "surface"), 0700); err != nil {
		return err
	}
	sort.Slice(entries, func(i, j int) bool { return len(entries[i].Path) < len(entries[j].Path) })
	for _, entry := range entries {
		name := filepath.Join(destination, entry.Path)
		if err = os.MkdirAll(filepath.Dir(name), 0700); err != nil {
			return err
		}
		switch entry.Kind {
		case "directory":
			err = os.MkdirAll(name, 0700)
		case "file":
			var data []byte
			data, err = w.gitBytes("blob", entry.Object)
			if err != nil {
				return err
			}
			var f *os.File
			f, err = os.OpenFile(name, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
			if err != nil {
				return err
			}
			_, writeErr := f.Write(data)
			err = errors.Join(writeErr, f.Chmod(os.FileMode(entry.Mode)), f.Sync(), f.Close())
		case "symlink":
			continue
		default:
			return errors.New("unsupported file manifest kind")
		}
		if err != nil {
			return err
		}
	}
	for _, entry := range entries {
		if entry.Kind == "symlink" {
			data, err := w.gitBytes("blob", entry.Object)
			if err != nil {
				return err
			}
			if string(data) != entry.Target {
				return errors.New("symlink content differs from manifest")
			}
			if err = os.Symlink(entry.Target, filepath.Join(destination, entry.Path)); err != nil {
				return err
			}
		}
	}
	if err = filesystem.Archive(destination, io.Discard); err != nil {
		return fmt.Errorf("snapshot link validation: %w", err)
	}
	for i := len(entries) - 1; i >= 0; i-- {
		entry := entries[i]
		if entry.Kind == "directory" {
			if err = os.Chmod(filepath.Join(destination, entry.Path), os.FileMode(entry.Mode)); err != nil {
				return err
			}
		}
	}
	successful = true
	return filesystem.SyncDir(destination)
}

// The manifest supplies metadata Git does not retain, not an alternate tree.
// Verify its paths, object IDs and file kinds against the actual commit before
// materialization, including empty directories and the two logical roots.
func (w *Work) verifyManifestTree(ref string, entries []FileEntry) error {
	raw, err := w.gitInput(nil, "ls-tree", "--full-tree", "-r", "-t", "-z", ref)
	if err != nil {
		return err
	}
	type member struct{ mode, kind, object string }
	tree := map[string]member{}
	for _, line := range strings.Split(raw, "\x00") {
		if line == "" {
			continue
		}
		header, path, ok := strings.Cut(line, "\t")
		fields := strings.Fields(header)
		if !ok || len(fields) != 3 {
			return errors.New("invalid Git tree entry")
		}
		tree[path] = member{fields[0], fields[1], fields[2]}
	}
	if len(entries) != len(tree) {
		return errors.New("file manifest does not cover the committed tree")
	}
	seen := map[string]bool{}
	for _, entry := range entries {
		actual, ok := tree[entry.Path]
		if !ok || seen[entry.Path] || actual.object != entry.Object {
			return errors.New("file manifest differs from committed object")
		}
		seen[entry.Path] = true
		mode, kind := "", "blob"
		switch entry.Kind {
		case "directory":
			mode, kind = "040000", "tree"
		case "symlink":
			mode = "120000"
		case "file":
			mode = "100644"
			if entry.Mode&0111 != 0 {
				mode = "100755"
			}
		default:
			return errors.New("unsupported file manifest kind")
		}
		if mode != actual.mode || kind != actual.kind {
			return errors.New("file manifest kind differs from committed tree")
		}
	}
	if !seen["harness"] || !seen["surface"] || !seen["work.toml"] {
		return errors.New("incomplete Work content snapshot")
	}
	return nil
}

func (w *Work) SelectHarness() (string, error) {
	raw, err := os.ReadFile(filepath.Join(w.Path, "work.toml"))
	if err != nil {
		return "", err
	}
	definition, err := parseDefinition(raw)
	if err != nil {
		return "", err
	}
	if err = validateContentRoots(w.Path, definition); err != nil {
		return "", err
	}
	if err = validateHarness(filepath.Join(w.Path, definition.Harness.Path)); err != nil {
		return "", err
	}
	candidate := *w
	candidate.Definition = definition
	candidate.Harness = filepath.Join(w.Path, definition.Harness.Path)
	candidate.Surface = filepath.Join(w.Path, definition.Surface.Path)
	if err = candidate.ValidateResources(); err != nil {
		return "", err
	}
	ref, err := candidate.snapshot("explicit strategy selection", raw)
	if err != nil {
		return "", err
	}
	if err = w.Control.SelectStrategy(ref); err != nil {
		return "", err
	}
	_, err = w.Events.Append("host", "strategy:"+ref, "harness.selected", store.Object{"harness_ref": ref})
	return ref, err
}

// ForStrategy resolves the complete execution definition from the same immutable
// revision as Harness code. Candidate work.toml bytes never retarget a Round.
func (w *Work) ForStrategy(ref string) (*Work, error) {
	if !fullGitObject.MatchString(ref) {
		return nil, errors.New("full strategy object required")
	}
	object, err := w.git("rev-parse", "--verify", ref+":work.toml")
	if err != nil {
		return nil, err
	}
	raw, err := w.gitBytes("blob", object)
	if err != nil {
		return nil, err
	}
	definition, err := parseDefinition(raw)
	if err != nil {
		return nil, err
	}
	bound := *w
	bound.Definition = definition
	bound.Harness = filepath.Join(w.Path, definition.Harness.Path)
	bound.Surface = filepath.Join(w.Path, definition.Surface.Path)
	return &bound, nil
}
