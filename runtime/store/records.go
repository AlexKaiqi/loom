package store

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

// RecordRef identifies bytes, never a physical path or an authorization grant.
type RecordRef struct {
	SHA256    string `json:"sha256"`
	SizeBytes string `json:"size_bytes"`
	MediaType string `json:"media_type"`
}

func (r RecordRef) Validate() error {
	b, err := hex.DecodeString(r.SHA256)
	n, e := strconv.ParseUint(r.SizeBytes, 10, 63)
	if err != nil || len(b) != 32 || hex.EncodeToString(b) != r.SHA256 || e != nil || strconv.FormatUint(n, 10) != r.SizeBytes || r.MediaType == "" {
		return errors.New("invalid record_ref")
	}
	return nil
}

type Records struct{ Directory string }

func refFor(data []byte, mediaType string) RecordRef {
	h := sha256.Sum256(data)
	return RecordRef{hex.EncodeToString(h[:]), strconv.Itoa(len(data)), mediaType}
}

// Put publishes fully synchronized bytes with a no-replace link. Existing
// content is verified, including on deduplication; corrupt objects never heal
// silently. Authority checks belong to the caller that resolves the reference.
func (s Records) Put(data []byte, mediaType string) (RecordRef, error) {
	r := refFor(data, mediaType)
	if err := r.Validate(); err != nil {
		return r, err
	}
	if err := os.MkdirAll(s.Directory, 0700); err != nil {
		return r, err
	}
	if err := syncDir(filepath.Dir(s.Directory)); err != nil {
		return r, err
	}
	name := filepath.Join(s.Directory, r.SHA256)
	if _, err := os.Lstat(name); err == nil {
		_, err = s.Get(r)
		return r, err
	} else if !errors.Is(err, os.ErrNotExist) {
		return r, err
	}
	f, err := os.CreateTemp(s.Directory, ".record-")
	if err != nil {
		return r, err
	}
	defer os.Remove(f.Name())
	_, err = f.Write(data)
	if err == nil {
		err = f.Chmod(0400)
	}
	if err == nil {
		err = f.Sync()
	}
	err = errors.Join(err, f.Close())
	if err != nil {
		return r, err
	}
	if err = os.Link(f.Name(), name); err != nil && !errors.Is(err, os.ErrExist) {
		return r, err
	}
	if _, err = s.Get(r); err != nil {
		return r, err
	}
	return r, syncDir(s.Directory)
}

func (s Records) Get(r RecordRef) ([]byte, error) {
	if err := r.Validate(); err != nil {
		return nil, err
	}
	root, err := os.OpenRoot(s.Directory)
	if err != nil {
		return nil, err
	}
	defer root.Close()
	info, err := root.Lstat(r.SHA256)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || strconv.FormatInt(info.Size(), 10) != r.SizeBytes {
		return nil, errors.New("record type or size mismatch")
	}
	data, err := root.ReadFile(r.SHA256)
	if err != nil {
		return nil, err
	}
	h := sha256.Sum256(data)
	if hex.EncodeToString(h[:]) != r.SHA256 {
		return nil, fmt.Errorf("record digest mismatch: %s", r.SHA256)
	}
	return data, nil
}

func syncDir(name string) error {
	f, err := os.Open(name)
	if err != nil {
		return err
	}
	return errors.Join(f.Sync(), f.Close())
}
