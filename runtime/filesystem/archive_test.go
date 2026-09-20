package filesystem

import (
	"archive/tar"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func digestBytes(data []byte) string { h := sha256.Sum256(data); return hex.EncodeToString(h[:]) }

func TestArchiveRoundTripAndConflict(t *testing.T) {
	root := filepath.Join(t.TempDir(), "content")
	if err := os.Mkdir(root, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "original"), []byte("before"), 0600); err != nil {
		t.Fatal(err)
	}
	original, err := os.Lstat(root)
	if err != nil {
		t.Fatal(err)
	}
	var data bytes.Buffer
	if err := Archive(root, &data); err != nil {
		t.Fatal(err)
	}
	digest := digestBytes(data.Bytes())
	if err := os.WriteFile(filepath.Join(root, "original"), []byte("manual"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := Restore(bytes.NewReader(data.Bytes()), root, original, digest); err == nil {
		t.Fatal("manual change was overwritten")
	}
	got, _ := os.ReadFile(filepath.Join(root, "original"))
	if string(got) != "manual" {
		t.Fatal(string(got))
	}
	if err := os.WriteFile(filepath.Join(root, "original"), []byte("before"), 0600); err != nil {
		t.Fatal(err)
	}
	// Metadata changed: derive the current authorized snapshot before this operation.
	data.Reset()
	if err := Archive(root, &data); err != nil {
		t.Fatal(err)
	}
	digest = digestBytes(data.Bytes())
	var replacement bytes.Buffer
	tw := tar.NewWriter(&replacement)
	if err := tw.WriteHeader(&tar.Header{Name: "new", Mode: 0600, Size: 5}); err != nil {
		t.Fatal(err)
	}
	tw.Write([]byte("after"))
	tw.Close()
	if err := Restore(bytes.NewReader(replacement.Bytes()), root, original, digest); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "original")); !os.IsNotExist(err) {
		t.Fatal("deletion not reflected", err)
	}
	got, _ = os.ReadFile(filepath.Join(root, "new"))
	if string(got) != "after" {
		t.Fatal(string(got))
	}
}

func TestPortableDigestRetainsContentTypesAndModes(t *testing.T) {
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "empty"), 0751); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "run"), []byte("#!/bin/sh\n"), 0750); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("run", filepath.Join(root, "link")); err != nil {
		t.Fatal(err)
	}
	initial, err := TreeDigest(root)
	if err != nil {
		t.Fatal(err)
	}
	var snapshot bytes.Buffer
	if err = Archive(root, &snapshot); err != nil {
		t.Fatal(err)
	}
	if initial != digestBytes(snapshot.Bytes()) {
		t.Fatal("digest is not canonical tar content")
	}
	copy := t.TempDir()
	if err = Extract(&snapshot, copy); err != nil {
		t.Fatal(err)
	}
	digest, err := TreeDigest(copy)
	if err != nil || digest != initial {
		t.Fatal("portable snapshot changed", initial, digest, err)
	}
	if err = os.Chtimes(filepath.Join(copy, "run"), time.Now(), time.Now()); err != nil {
		t.Fatal(err)
	}
	digest, err = TreeDigest(copy)
	if err != nil || digest != initial {
		t.Fatal("host timestamps affect content identity", err)
	}
	if err = os.Chmod(filepath.Join(copy, "run"), 0640); err != nil {
		t.Fatal(err)
	}
	digest, err = TreeDigest(copy)
	if err != nil || digest == initial {
		t.Fatal("executable mode omitted", err)
	}
	if err = os.Chmod(filepath.Join(copy, "run"), 0750); err != nil {
		t.Fatal(err)
	}
	if err = os.Remove(filepath.Join(copy, "empty")); err != nil {
		t.Fatal(err)
	}
	digest, err = TreeDigest(copy)
	if err != nil || digest == initial {
		t.Fatal("empty directory omitted", err)
	}
}
func TestArchiveRejectsEscapesAndSpecialFiles(t *testing.T) {
	for _, h := range []tar.Header{{Name: "../escape", Typeflag: tar.TypeReg, Mode: 0600}, {Name: "/escape", Typeflag: tar.TypeReg, Mode: 0600}, {Name: "link", Linkname: "../../escape", Typeflag: tar.TypeSymlink}, {Name: "device", Typeflag: tar.TypeChar}} {
		var data bytes.Buffer
		tw := tar.NewWriter(&data)
		if err := tw.WriteHeader(&h); err != nil {
			t.Fatal(err)
		}
		tw.Close()
		if err := Extract(bytes.NewReader(data.Bytes()), t.TempDir()); err == nil {
			t.Fatalf("accepted %+v", h)
		}
	}
	root := t.TempDir()
	if err := os.Symlink("../../escape", filepath.Join(root, "link")); err != nil {
		t.Fatal(err)
	}
	if err := Archive(root, &bytes.Buffer{}); err == nil {
		t.Fatal("escaping input accepted")
	}
}

func TestExtractionRejectsExistingContent(t *testing.T) {
	outside := t.TempDir()
	stage := t.TempDir()
	if err := os.Symlink(outside, filepath.Join(stage, "existing")); err != nil {
		t.Fatal(err)
	}
	var data bytes.Buffer
	tw := tar.NewWriter(&data)
	if err := tw.WriteHeader(&tar.Header{Name: "existing/escape", Mode: 0600, Size: 4}); err != nil {
		t.Fatal(err)
	}
	tw.Write([]byte("oops"))
	tw.Close()
	if err := Extract(&data, stage); err == nil {
		t.Fatal("accepted pre-existing staging entries")
	}
	if _, err := os.Stat(filepath.Join(outside, "escape")); !os.IsNotExist(err) {
		t.Fatal("wrote through existing symlink", err)
	}
}
func TestArchiveInternalSymlink(t *testing.T) {
	root := t.TempDir()
	os.WriteFile(filepath.Join(root, "a"), []byte("data"), 0600)
	os.Symlink("a", filepath.Join(root, "b"))
	var data bytes.Buffer
	if err := Archive(root, &data); err != nil {
		t.Fatal(err)
	}
	target := t.TempDir()
	if err := Extract(bytes.NewReader(data.Bytes()), target); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(filepath.Join(target, "b"))
	if err != nil || string(got) != "data" {
		t.Fatal(string(got), err)
	}
}

func TestArchiveDanglingLinkAndChainEscape(t *testing.T) {
	root := t.TempDir()
	os.Symlink("missing", filepath.Join(root, "internal"))
	var data bytes.Buffer
	if err := Archive(root, &data); err != nil {
		t.Fatal("internal dangling link rejected", err)
	}
	target := t.TempDir()
	if err := Extract(bytes.NewReader(data.Bytes()), target); err != nil {
		t.Fatal(err)
	}
	link, err := os.Readlink(filepath.Join(target, "internal"))
	if err != nil || link != "missing" {
		t.Fatal(link, err)
	}
	os.Symlink(".", filepath.Join(root, "alias"))
	os.Symlink("alias/../outside-missing", filepath.Join(root, "escape"))
	if err := Archive(root, &bytes.Buffer{}); err == nil {
		t.Fatal("chained escape accepted on input")
	}
	data.Reset()
	tw := tar.NewWriter(&data)
	tw.WriteHeader(&tar.Header{Name: "alias", Typeflag: tar.TypeSymlink, Linkname: "."})
	tw.WriteHeader(&tar.Header{Name: "escape", Typeflag: tar.TypeSymlink, Linkname: "alias/../outside-missing"})
	tw.Close()
	if err := Extract(bytes.NewReader(data.Bytes()), t.TempDir()); err == nil {
		t.Fatal("chained escape accepted on output")
	}
}
