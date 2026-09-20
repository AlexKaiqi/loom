package store

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRecordPublicationAndCorruption(t *testing.T) {
	s := Records{Directory: filepath.Join(t.TempDir(), "records")}
	r, err := s.Put([]byte("raw\r\n\x00bytes"), "application/octet-stream")
	if err != nil {
		t.Fatal(err)
	}
	if r.SizeBytes != "11" {
		t.Fatal(r)
	}
	again, err := s.Put([]byte("raw\r\n\x00bytes"), r.MediaType)
	if err != nil || again != r {
		t.Fatal(again, err)
	}
	name := filepath.Join(s.Directory, r.SHA256)
	if err = os.Chmod(name, 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(name, []byte("bad\r\n\x00bytes"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Get(r); err == nil {
		t.Fatal("corruption accepted")
	}
	if _, err = s.Put([]byte("raw\r\n\x00bytes"), r.MediaType); err == nil {
		t.Fatal("corruption silently replaced")
	}
	if err = os.Remove(name); err != nil {
		t.Fatal(err)
	}
	if err = os.Symlink("/etc/passwd", name); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Get(r); err == nil {
		t.Fatal("record symlink accepted")
	}
	bad := r
	bad.SHA256 = "../escape"
	if _, err = s.Get(bad); err == nil {
		t.Fatal("escaping reference accepted")
	}
}

func TestDatabaseActualDurabilitySettings(t *testing.T) {
	db, err := OpenDB(filepath.Join(t.TempDir(), "state.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var version, mode string
	var full, fk int
	if err = db.QueryRow("SELECT sqlite_version()").Scan(&version); err != nil {
		t.Fatal(err)
	}
	if version != "3.51.3" {
		t.Fatalf("update release evidence for changed embedded engine: %s", version)
	}
	if err = db.QueryRow("PRAGMA journal_mode").Scan(&mode); err != nil {
		t.Fatal(err)
	}
	if err = db.QueryRow("PRAGMA synchronous").Scan(&full); err != nil {
		t.Fatal(err)
	}
	if err = db.QueryRow("PRAGMA foreign_keys").Scan(&fk); err != nil {
		t.Fatal(err)
	}
	if mode != "wal" || full != 2 || fk != 1 {
		t.Fatalf("%s %d %d", mode, full, fk)
	}
}
