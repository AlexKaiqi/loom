package sandbox

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"

	"loom/runtime/filesystem"
)

func digestBytes(data []byte) string { h := sha256.Sum256(data); return hex.EncodeToString(h[:]) }

func save(path string, source io.Reader) (Artifact, error) {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return Artifact{}, err
	}
	h := sha256.New()
	size, copyErr := io.Copy(io.MultiWriter(f, h), source)
	if err = errors.Join(copyErr, f.Sync(), f.Close()); err != nil {
		return Artifact{}, err
	}
	if err = filesystem.SyncDir(filepath.Dir(path)); err != nil {
		return Artifact{}, err
	}
	absolute, err := filepath.Abs(path)
	return Artifact{Path: absolute, Size: size, SHA256: hex.EncodeToString(h.Sum(nil))}, err
}
