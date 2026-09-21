package taskio

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"

	"loom/runtime/contracts"
	"loom/runtime/filesystem"
)

func Save(path string, source io.Reader) (contracts.Artifact, error) {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return contracts.Artifact{}, err
	}
	h := sha256.New()
	size, copyErr := io.Copy(io.MultiWriter(f, h), source)
	if err = errors.Join(copyErr, f.Sync(), f.Close()); err != nil {
		return contracts.Artifact{}, err
	}
	if err = filesystem.SyncDir(filepath.Dir(path)); err != nil {
		return contracts.Artifact{}, err
	}
	absolute, err := filepath.Abs(path)
	return contracts.Artifact{Path: absolute, Size: size, SHA256: hex.EncodeToString(h.Sum(nil))}, err
}
