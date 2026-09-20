package work

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"

	"loom/runtime/filesystem"
	"loom/runtime/store"
)

// Files hashes link text without following it; resolving content is a separate authorized read.
func Files(root string) (map[string]string, error) {
	result := map[string]string{}
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() && !info.IsDir() && info.Mode()&os.ModeSymlink == 0 {
			return errors.New("unsupported file type: " + path)
		}
		if info.IsDir() {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			target, err := os.Readlink(path)
			if err != nil {
				return err
			}
			if filepath.IsAbs(target) || !filesystem.Inside(root, filepath.Clean(filepath.Join(filepath.Dir(path), target))) {
				return errors.New("escaping content link: " + relative)
			}
			sum := sha256.Sum256([]byte("symlink:" + target))
			result[filepath.ToSlash(relative)] = hex.EncodeToString(sum[:])
			return nil
		}
		f, err := os.Open(path)
		if err != nil {
			return err
		}
		hash := sha256.New()
		_, err = io.Copy(hash, f)
		closeErr := f.Close()
		if err != nil {
			return err
		}
		if closeErr != nil {
			return closeErr
		}
		result[filepath.ToSlash(relative)] = hex.EncodeToString(hash.Sum(nil))
		return nil
	})
	return result, err
}

func Save(path string, value []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	id, err := store.ID()
	if err != nil {
		return err
	}
	temporary := path + "." + id + ".tmp"
	f, err := os.OpenFile(temporary, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer os.Remove(temporary)
	if _, err = f.Write(value); err != nil {
		f.Close()
		return err
	}
	if err = f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	if err = os.Rename(temporary, path); err != nil {
		return err
	}
	dir, err := os.Open(filepath.Dir(path))
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}
func copyTree(source, target string) error {
	return filepath.WalkDir(source, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		relative, err := filepath.Rel(source, path)
		if err != nil {
			return err
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		destination := filepath.Join(target, relative)
		if info.IsDir() {
			return os.MkdirAll(destination, 0700)
		}
		if info.Mode()&os.ModeSymlink != 0 {
			link, err := os.Readlink(path)
			if err != nil {
				return err
			}
			return os.Symlink(link, destination)
		}
		if !info.Mode().IsRegular() {
			return errors.New("unsupported file type: " + path)
		}
		return copyFile(path, destination, info.Mode().Perm())
	})
}
func copyFile(source, destination string, mode fs.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(destination), 0700); err != nil {
		return err
	}
	src, err := os.Open(source)
	if err != nil {
		return err
	}
	defer src.Close()
	dst, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, mode)
	if err != nil {
		return err
	}
	_, err = io.Copy(dst, src)
	if err != nil {
		dst.Close()
		return err
	}
	if err = dst.Chmod(mode); err != nil {
		dst.Close()
		return err
	}
	if err = dst.Sync(); err != nil {
		dst.Close()
		return err
	}
	return dst.Close()
}
