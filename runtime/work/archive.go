package work

import (
	"compress/gzip"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"strings"

	"loom/runtime/filesystem"
	"loom/runtime/store"
)

func portable(db interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
}) error {
	var n int
	if err := db.QueryRowContext(context.Background(), "SELECT (SELECT count(*) FROM rounds WHERE state IN('running','recovering','blocked') OR (state='ready' AND checkpoint IS NULL)) + (SELECT count(*) FROM effects WHERE status!='completed')").Scan(&n); err != nil {
		return err
	}
	if n != 0 {
		return fmt.Errorf("%w: export requires inactive Work or a confirmed pause with known effects", store.ErrConflict)
	}
	return nil
}
func (w *Work) Export(archive string) error {
	archive, err := filepath.Abs(archive)
	if err != nil {
		return err
	}
	if err = os.MkdirAll(filepath.Dir(archive), 0700); err != nil {
		return err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(archive))
	if err != nil {
		return err
	}
	archive = filepath.Join(parent, filepath.Base(archive))
	relative, err := filepath.Rel(w.Path, archive)
	if err != nil {
		return err
	}
	if relative == "." || relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return errors.New("export destination must be outside Work")
	}
	return store.Immediate(w.DBPath, func(guard *sql.Conn) error {
		if err := portable(guard); err != nil {
			return err
		}
		temporary, err := os.MkdirTemp("", "loom-export-")
		if err != nil {
			return err
		}
		defer os.RemoveAll(temporary)
		staging := filepath.Join(temporary, "work")
		if err = os.Mkdir(staging, 0700); err != nil {
			return err
		}
		if _, err := Open(w.Path); err != nil {
			return err
		}
		if err := w.ValidateResources(); err != nil {
			return err
		}
		if err = copyPortableTree(w.Path, staging); err != nil {
			return err
		}
		source, err := store.OpenDB(w.DBPath)
		if err != nil {
			return err
		}
		_, vacuumErr := source.Exec("VACUUM INTO ?", filepath.Join(staging, ".loom", "state.sqlite"))
		closeErr := source.Close()
		if vacuumErr != nil {
			return vacuumErr
		}
		if closeErr != nil {
			return closeErr
		}
		entries, err := Files(staging)
		if err != nil {
			return err
		}
		treeDigest, err := filesystem.TreeDigest(staging)
		if err != nil {
			return err
		}
		encoded, err := store.Canonical(store.Object{"format": 3, "files": entries, "tree_digest": treeDigest})
		if err != nil {
			return err
		}
		if err = Save(filepath.Join(staging, ".loom", "export.json"), []byte(encoded)); err != nil {
			return err
		}
		return writeArchive(archive, staging)
	})
}
func writeArchive(destination, root string) (err error) {
	output, err := os.OpenFile(destination, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer func() {
		if err != nil {
			os.Remove(destination)
		}
	}()
	defer output.Close()
	compressed := gzip.NewWriter(output)
	// The parent contains only work/, retaining the public archive root while
	// reusing the same safe, metadata-normalized tar codec as file transfers.
	if err = filesystem.Archive(filepath.Dir(root), compressed); err != nil {
		compressed.Close()
		return err
	}
	if err = compressed.Close(); err != nil {
		return err
	}
	if err = output.Sync(); err != nil {
		return err
	}
	return output.Close()
}
func Import(archive, destination string) (*Work, error) {
	destination, err := filepath.Abs(destination)
	if err != nil {
		return nil, err
	}
	if _, err = os.Lstat(destination); !os.IsNotExist(err) {
		if err == nil {
			err = os.ErrExist
		}
		return nil, err
	}
	if err = os.MkdirAll(filepath.Dir(destination), 0700); err != nil {
		return nil, err
	}
	temporary, err := os.MkdirTemp(filepath.Dir(destination), ".loom-import-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(temporary)
	if err = extractArchive(archive, temporary); err != nil {
		return nil, err
	}
	children, err := os.ReadDir(temporary)
	if err != nil {
		return nil, err
	}
	if len(children) != 1 || children[0].Name() != "work" || !children[0].IsDir() {
		return nil, errors.New("export archive must contain only work/")
	}
	root := filepath.Join(temporary, "work")
	content, err := os.ReadFile(filepath.Join(root, ".loom", "export.json"))
	if err != nil {
		return nil, err
	}
	var index struct {
		Format     int               `json:"format"`
		Files      map[string]string `json:"files"`
		TreeDigest string            `json:"tree_digest"`
	}
	if err = json.Unmarshal(content, &index); err != nil {
		return nil, err
	}
	if index.Format != 3 {
		return nil, errors.New("unsupported export format")
	}
	if err = os.Remove(filepath.Join(root, ".loom", "export.json")); err != nil {
		return nil, err
	}
	entries, err := Files(root)
	if err != nil {
		return nil, err
	}
	if !reflect.DeepEqual(entries, index.Files) {
		return nil, errors.New("export digest mismatch")
	}
	observedDigest, err := filesystem.TreeDigest(root)
	if err != nil {
		return nil, err
	}
	if !validDigest(index.TreeDigest) || observedDigest != index.TreeDigest {
		return nil, errors.New("export tree metadata digest mismatch")
	}
	candidate, err := Open(root)
	if err != nil {
		return nil, err
	}
	db, err := store.OpenDB(candidate.DBPath)
	if err != nil {
		return nil, err
	}
	var integrity string
	err = db.QueryRow("PRAGMA integrity_check").Scan(&integrity)
	if err == nil && integrity != "ok" {
		err = errors.New("invalid exported SQLite state")
	}
	if err == nil {
		err = portable(db)
	}
	closeErr := db.Close()
	if err != nil {
		return nil, err
	}
	if closeErr != nil {
		return nil, closeErr
	}
	if err = candidate.ValidateResources(); err != nil {
		return nil, err
	}
	if _, err = candidate.git("fsck", "--full"); err != nil {
		return nil, err
	}
	if err = os.Rename(root, destination); err != nil {
		return nil, err
	}
	return Open(destination)
}
func extractArchive(archive, destination string) error {
	input, err := os.Open(archive)
	if err != nil {
		return err
	}
	defer input.Close()
	compressed, err := gzip.NewReader(input)
	if err != nil {
		return err
	}
	defer compressed.Close()
	return filesystem.Extract(compressed, destination)
}

// Copy ordinary Work files, retaining user additions but replacing live SQLite
// and its WAL with one SQLite-produced consistent database snapshot.
func copyPortableTree(source, target string) error {
	return filepath.WalkDir(source, func(name string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		relative, err := filepath.Rel(source, name)
		if err != nil {
			return err
		}
		normalized := filepath.ToSlash(relative)
		switch normalized {
		case ".loom/state.sqlite", ".loom/state.sqlite-wal", ".loom/state.sqlite-shm":
			return nil
		case ".loom/export.json":
			return errors.New("reserved export manifest already exists")
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		destination := filepath.Join(target, relative)
		if info.IsDir() {
			if err = os.MkdirAll(destination, info.Mode().Perm()); err != nil {
				return err
			}
			return os.Chmod(destination, info.Mode().Perm())
		}
		if info.Mode()&os.ModeSymlink != 0 {
			link, err := os.Readlink(name)
			if err != nil {
				return err
			}
			return os.Symlink(link, destination)
		}
		if !info.Mode().IsRegular() {
			return errors.New("unsupported Work file: " + relative)
		}
		return copyFile(name, destination, info.Mode().Perm())
	})
}
