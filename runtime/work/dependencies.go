package work

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"loom/runtime/filesystem"
	"loom/runtime/store"
)

type ArchiveReference struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Size   int64  `json:"size"`
}
type DependencySnapshot struct {
	Format     int              `json:"format"`
	Name       string           `json:"name"`
	TreeDigest string           `json:"tree_digest"`
	Archive    ArchiveReference `json:"archive"`
}

func (w *Work) dependencyPath(digest string) string {
	return filepath.Join(w.Path, ".loom", "dependencies", "userspace-"+digest+".json")
}

// UserspaceSnapshot validates the portable reference and actual retained archive.
// A declared but never bound Userspace has no snapshot yet.
func (w *Work) UserspaceSnapshot() (*DependencySnapshot, error) {
	manifestBytes, err := os.ReadFile(filepath.Join(w.Path, ".loom", "identity.json"))
	if err != nil {
		return nil, err
	}
	manifest, err := store.DecodeObject(string(manifestBytes))
	if err != nil {
		return nil, err
	}
	boundDigest, present := manifest["userspace_snapshot_digest"]
	if !present {
		return nil, nil
	}
	sha, ok := boundDigest.(string)
	if !ok || !validDigest(sha) {
		return nil, errors.New("invalid Userspace snapshot identity binding")
	}
	info, err := os.Lstat(w.dependencyPath(sha))
	if errors.Is(err, os.ErrNotExist) {
		return nil, errors.New("retained Userspace snapshot reference is missing")
	}
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("invalid Userspace snapshot file")
	}
	if w.Definition.Userspace == nil {
		return nil, errors.New("snapshot exists without Userspace declaration")
	}
	data, err := os.ReadFile(w.dependencyPath(sha))
	if err != nil {
		return nil, err
	}
	if digestBytes(data) != sha {
		return nil, errors.New("Userspace snapshot reference binding mismatch")
	}
	var snapshot DependencySnapshot
	if err = json.Unmarshal(data, &snapshot); err != nil {
		return nil, err
	}
	expected := ".loom/artifacts/" + snapshot.Archive.SHA256 + ".tar"
	if snapshot.Format != 1 || snapshot.Name != w.Definition.Userspace.Name || !validDigest(snapshot.TreeDigest) || !validDigest(snapshot.Archive.SHA256) || snapshot.Archive.Path != expected || snapshot.Archive.Size < 0 {
		return nil, errors.New("invalid Userspace snapshot reference")
	}
	filename := filepath.Join(w.Path, filepath.FromSlash(expected))
	info, err = os.Lstat(filename)
	if err != nil {
		return nil, fmt.Errorf("Userspace snapshot archive unavailable: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() != snapshot.Archive.Size {
		return nil, errors.New("Userspace snapshot archive changed")
	}
	digest, err := fileDigest(filename)
	if err != nil {
		return nil, err
	}
	if digest != snapshot.Archive.SHA256 {
		return nil, errors.New("Userspace snapshot archive digest mismatch")
	}
	// The shared tar encoder is canonical, so the tree digest is the archive hash.
	if snapshot.TreeDigest != snapshot.Archive.SHA256 {
		return nil, errors.New("Userspace tree and archive reference disagree")
	}
	return &snapshot, nil
}
func validDigest(value string) bool {
	if len(value) != 64 {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}
func fileDigest(name string) (string, error) {
	f, err := os.Open(name)
	if err != nil {
		return "", err
	}
	defer f.Close()
	hash := sha256.New()
	if _, err = io.Copy(hash, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
func (w *Work) CaptureUserspace(directory string) (*DependencySnapshot, error) {
	if w.Definition.Userspace == nil {
		return nil, errors.New("Work does not declare a Userspace dependency")
	}
	if _, err := w.UserspaceSnapshot(); err != nil {
		return nil, err
	}
	before, err := filesystem.TreeDigest(directory)
	if err != nil {
		return nil, err
	}
	temporary, err := os.CreateTemp(w.ArtifactsDir(), ".userspace-*.tar")
	if err != nil {
		return nil, err
	}
	defer os.Remove(temporary.Name())
	if err = temporary.Chmod(0600); err == nil {
		err = filesystem.Archive(directory, temporary)
	}
	if err == nil {
		err = temporary.Sync()
	}
	closeErr := temporary.Close()
	if err != nil {
		return nil, err
	}
	if closeErr != nil {
		return nil, closeErr
	}
	after, err := filesystem.TreeDigest(directory)
	if err != nil {
		return nil, err
	}
	digest, err := fileDigest(temporary.Name())
	if err != nil {
		return nil, err
	}
	if before != after || digest != before {
		return nil, errors.New("Userspace changed while capturing portable snapshot")
	}
	info, err := os.Stat(temporary.Name())
	if err != nil {
		return nil, err
	}
	reference := ArchiveReference{Path: ".loom/artifacts/" + digest + ".tar", SHA256: digest, Size: info.Size()}
	destination := filepath.Join(w.Path, filepath.FromSlash(reference.Path))
	if err = os.Rename(temporary.Name(), destination); err != nil {
		return nil, err
	}
	if err = syncDirectory(w.ArtifactsDir()); err != nil {
		return nil, err
	}
	snapshot := &DependencySnapshot{Format: 1, Name: w.Definition.Userspace.Name, TreeDigest: digest, Archive: reference}
	encoded, err := json.Marshal(snapshot)
	if err != nil {
		return nil, err
	}
	if err = Save(w.dependencyPath(digestBytes(encoded)), encoded); err != nil {
		return nil, err
	}
	manifestBytes, err := os.ReadFile(filepath.Join(w.Path, ".loom", "identity.json"))
	if err != nil {
		return nil, err
	}
	manifest, err := store.DecodeObject(string(manifestBytes))
	if err != nil {
		return nil, err
	}
	manifest["userspace_snapshot_digest"] = digestBytes(encoded)
	identity, err := store.Canonical(manifest)
	if err != nil {
		return nil, err
	}
	if err = Save(filepath.Join(w.Path, ".loom", "identity.json"), []byte(identity)); err != nil {
		return nil, err
	}
	w.Manifest = manifest
	return snapshot, nil
}
func (w *Work) VerifyUserspace(directory string) error {
	snapshot, err := w.UserspaceSnapshot()
	if err != nil {
		return err
	}
	if snapshot == nil {
		return errors.New("Userspace has no retained version; explicit initial grant required")
	}
	digest, err := filesystem.TreeDigest(directory)
	if err != nil {
		return err
	}
	if digest != snapshot.TreeDigest {
		return fmt.Errorf("%w: Userspace differs from retained Work version", store.ErrConflict)
	}
	return nil
}
func (w *Work) RestoreUserspace(destination string) error {
	snapshot, err := w.UserspaceSnapshot()
	if err != nil {
		return err
	}
	if snapshot == nil {
		return errors.New("Work has no retained Userspace snapshot")
	}
	destination, err = filepath.Abs(destination)
	if err != nil {
		return err
	}
	if _, err = os.Lstat(destination); !os.IsNotExist(err) {
		if err == nil {
			err = os.ErrExist
		}
		return err
	}
	if err = os.MkdirAll(filepath.Dir(destination), 0700); err != nil {
		return err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(destination))
	if err != nil {
		return err
	}
	destination = filepath.Join(parent, filepath.Base(destination))
	relative, err := filepath.Rel(w.Path, destination)
	if err != nil {
		return err
	}
	if relative == "." || relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return errors.New("Userspace restoration target must be outside Work")
	}
	staging, err := os.MkdirTemp(parent, ".loom-userspace-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(staging)
	input, err := os.Open(filepath.Join(w.Path, filepath.FromSlash(snapshot.Archive.Path)))
	if err != nil {
		return err
	}
	err = filesystem.Extract(input, staging)
	closeErr := input.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	digest, err := filesystem.TreeDigest(staging)
	if err != nil {
		return err
	}
	if digest != snapshot.TreeDigest {
		return errors.New("restored Userspace does not match retained tree")
	}
	if _, err = os.Lstat(destination); !os.IsNotExist(err) {
		if err == nil {
			err = os.ErrExist
		}
		return err
	}
	if err = os.Rename(staging, destination); err != nil {
		return err
	}
	return syncDirectory(parent)
}
func syncDirectory(path string) error {
	directory, err := os.Open(path)
	if err != nil {
		return err
	}
	defer directory.Close()
	return directory.Sync()
}
