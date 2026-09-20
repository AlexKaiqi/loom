package work

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"loom/runtime/filesystem"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"loom/runtime/store"
)

type FileEntry struct {
	Path   string `json:"path"`
	Kind   string `json:"kind"`
	Mode   uint32 `json:"mode"`
	Object string `json:"object,omitempty"`
	Target string `json:"target,omitempty"`
}

// gitInput uses plumbing with literal bytes; neither attributes, excludes nor
// hooks in the captured tree participate. The private repository is checked
// through gitCommand before use, and automatic pruning stays disabled.
func (w *Work) gitInput(input []byte, args ...string) (string, error) {
	if _, err := w.git("rev-parse", "--git-dir"); err != nil {
		return "", err
	}
	base := []string{"-c", "core.hooksPath=/dev/null", "-c", "core.fsync=all", "-c", "core.fsyncMethod=fsync", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "--git-dir=" + filepath.Join(w.Path, ".loom", "versions.git")}
	cmd := exec.Command("git", append(base, args...)...)
	cmd.Env = []string{"PATH=" + os.Getenv("PATH"), "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null", "GIT_AUTHOR_NAME=Loom", "GIT_AUTHOR_EMAIL=loom@local", "GIT_COMMITTER_NAME=Loom", "GIT_COMMITTER_EMAIL=loom@local"}
	cmd.Stdin = bytes.NewReader(input)
	out, err := cmd.CombinedOutput()
	if err != nil || bytes.Contains(out, []byte("warning:")) {
		return "", fmt.Errorf("git durability/capture failed: %s: %w", out, err)
	}
	return strings.TrimSpace(string(out)), nil
}

func (w *Work) captureDirectory(root, prefix string, manifest *[]FileEntry) (string, error) {
	entries, err := os.ReadDir(root)
	if err != nil {
		return "", err
	}
	var tree bytes.Buffer
	for _, entry := range entries {
		name := filepath.Join(root, entry.Name())
		rel := filepath.ToSlash(filepath.Join(prefix, entry.Name()))
		info, err := entry.Info()
		if err != nil {
			return "", err
		}
		item := FileEntry{Path: rel, Mode: uint32(info.Mode().Perm())}
		var object, mode, kind string
		switch {
		case info.IsDir():
			item.Kind = "directory"
			mode, kind = "040000", "tree"
			object, err = w.captureDirectory(name, rel, manifest)
		case info.Mode().IsRegular():
			item.Kind = "file"
			mode, kind = "100644", "blob"
			if info.Mode().Perm()&0111 != 0 {
				mode = "100755"
			}
			var data []byte
			data, err = os.ReadFile(name)
			if err == nil {
				object, err = w.gitInput(data, "hash-object", "-w", "--stdin", "--no-filters")
			}
		case info.Mode()&os.ModeSymlink != 0:
			item.Kind = "symlink"
			mode, kind = "120000", "blob"
			item.Target, err = os.Readlink(name)
			if err == nil {
				// A link is content, never an implicit read grant. Relative links
				// inside the logical Work may refer to separately captured roots.
				resolved := filepath.Clean(filepath.Join(filepath.Dir(name), item.Target))
				if filepath.IsAbs(item.Target) || !insideWork(w.Path, resolved) {
					return "", fmt.Errorf("escaping content link: %s", rel)
				}
				object, err = w.gitInput([]byte(item.Target), "hash-object", "-w", "--stdin", "--no-filters")
			}
		default:
			return "", fmt.Errorf("unsupported content file: %s", rel)
		}
		if err != nil {
			return "", err
		}
		item.Object = object
		*manifest = append(*manifest, item)
		fmt.Fprintf(&tree, "%s %s %s\t%s%c", mode, kind, object, entry.Name(), byte(0))
	}
	return w.gitInput(tree.Bytes(), "mktree", "-z")
}

func insideWork(root, name string) bool {
	rel, err := filepath.Rel(root, name)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}

// Snapshot captures all three portable roots, not just Surface. Git retention
// refs are durable before SQLite can reference a snapshot. The manifest retains
// empty directories and modes that a Git checkout alone cannot reconstruct.
func (w *Work) Snapshot(message string) (string, error) {
	return w.snapshot(message, nil)
}

func (w *Work) snapshot(message string, expectedDefinition []byte) (string, error) {
	definition, err := os.ReadFile(filepath.Join(w.Path, "work.toml"))
	if err != nil {
		return "", err
	}
	if expectedDefinition != nil && !bytes.Equal(definition, expectedDefinition) {
		return "", errors.New("baseline_conflict: definition changed after candidate validation")
	}
	if err := validateContentRoots(w.Path, w.Definition); err != nil {
		return "", err
	}
	stage, err := os.MkdirTemp(filepath.Join(w.Path, ".loom"), ".capture-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(stage)
	before := map[string]string{}
	for _, root := range []string{"harness", "surface"} {
		digest, e := filesystem.TreeDigest(w.contentRoot(root))
		if e != nil {
			return "", e
		}
		before[root] = digest
	}
	manifest := []FileEntry{}
	var tree bytes.Buffer
	for _, root := range []string{"harness", "surface"} {
		ref, e := w.CaptureContent(w.contentRoot(root))
		if e != nil {
			return "", e
		}
		if ref.SHA256 != before[root] {
			return "", errors.New("baseline_conflict: content changed while capturing sources")
		}
		fixed := filepath.Join(stage, root)
		if e = w.RestoreContent(ref, fixed); e != nil {
			return "", e
		}
		object, e := w.captureDirectory(fixed, root, &manifest)
		if e != nil {
			return "", e
		}
		info, e := os.Stat(fixed)
		if e != nil {
			return "", e
		}
		manifest = append(manifest, FileEntry{Path: root, Kind: "directory", Mode: uint32(info.Mode().Perm()), Object: object})
		fmt.Fprintf(&tree, "040000 tree %s\t%s%c", object, root, byte(0))
	}
	for _, root := range []string{"harness", "surface"} {
		digest, e := filesystem.TreeDigest(w.contentRoot(root))
		if e != nil {
			return "", e
		}
		if digest != before[root] {
			return "", errors.New("baseline_conflict: sources changed during capture")
		}
	}
	data, err := os.ReadFile(filepath.Join(w.Path, "work.toml"))
	if err != nil {
		return "", err
	}
	if !bytes.Equal(data, definition) {
		return "", errors.New("baseline_conflict: definition changed during capture")
	}
	object, err := w.gitInput(data, "hash-object", "-w", "--stdin", "--no-filters")
	if err != nil {
		return "", err
	}
	fmt.Fprintf(&tree, "100644 blob %s\twork.toml%c", object, byte(0))
	manifest = append(manifest, FileEntry{Path: "work.toml", Kind: "file", Mode: 0600, Object: object})
	body, err := json.Marshal(manifest)
	if err != nil {
		return "", err
	}
	ref, err := (store.Records{Directory: w.ArtifactsDir()}).Put(body, "application/vnd.loom.file-manifest+json")
	if err != nil {
		return "", err
	}
	root, err := w.gitInput(tree.Bytes(), "mktree", "-z")
	if err != nil {
		return "", err
	}
	args := []string{"commit-tree", root}
	parent, parentErr := w.git("rev-parse", "--verify", "HEAD")
	if parentErr == nil {
		args = append(args, "-p", parent)
	}
	commit, err := w.gitInput([]byte(message+"\n\nfile-manifest: "+ref.SHA256+"\n"), args...)
	if err != nil {
		return "", err
	}
	if _, err = w.git("update-ref", "refs/loom/retained/"+commit, commit); err != nil {
		return "", err
	}
	if parentErr != nil {
		parent = strings.Repeat("0", len(commit))
	}
	if _, err = w.git("update-ref", "HEAD", commit, parent); err != nil {
		return "", err
	}
	if commit == "" {
		return "", errors.New("empty content version")
	}
	return commit, nil
}

func (w *Work) contentRoot(root string) string {
	if root == "harness" {
		return w.Harness
	}
	return w.Surface
}

func (w *Work) CurrentContent() (string, error) { return w.git("rev-parse", "--verify", "HEAD") }
