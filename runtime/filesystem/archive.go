// Package filesystem provides content snapshots without execution or host authority.
package filesystem

import (
	"archive/tar"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

func Inside(root, name string) bool {
	r, err := filepath.Rel(root, name)
	return err == nil && r != ".." && !strings.HasPrefix(r, ".."+string(filepath.Separator))
}

// Archive uses the standard tar format, with no host ownership in the handoff.
// The original physical root and this full-content digest are also checked before publication.
func Archive(directory string, destination io.Writer) error {
	root, err := os.OpenRoot(directory)
	if err != nil {
		return err
	}
	defer root.Close()
	tw := tar.NewWriter(destination)
	err = filepath.WalkDir(directory, func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(directory, name)
		if err != nil {
			return err
		}
		link := ""
		if info.Mode()&os.ModeSymlink != 0 {
			link, err = os.Readlink(name)
			if err != nil {
				return err
			}
			if filepath.IsAbs(link) {
				return fmt.Errorf("escaping input symlink: %s", rel)
			}
			if err := containedLink(root, rel); err != nil {
				return err
			}
		} else if !info.Mode().IsRegular() && !info.IsDir() {
			return fmt.Errorf("unsupported input file type: %s", rel)
		}
		h, err := tar.FileInfoHeader(info, link)
		if err != nil {
			return err
		}
		h.Name = filepath.ToSlash(rel)
		h.Uid = 0
		h.Gid = 0
		h.Uname = ""
		h.Gname = ""
		h.Mode &= 0777
		h.ModTime = time.Unix(0, 0)
		h.AccessTime = time.Time{}
		h.ChangeTime = time.Time{}
		if err = tw.WriteHeader(h); err != nil {
			return err
		}
		if info.Mode().IsRegular() {
			f, err := root.Open(rel)
			if err != nil {
				return err
			}
			_, err = io.Copy(tw, f)
			return errors.Join(err, f.Close())
		}
		return nil
	})
	return errors.Join(err, tw.Close())
}

func validMember(name string) (string, error) {
	name = path.Clean(name)
	if strings.Contains(name, "\\") || strings.ContainsRune(name, 0) || path.IsAbs(name) || name == ".." || strings.HasPrefix(name, "../") {
		return "", fmt.Errorf("unsafe archive path %q", name)
	}
	return name, nil
}

// Extract requires an empty staging directory. It creates ordinary content first
// and links last, so archive links cannot redirect writes. Links stay within root.
func Extract(source io.Reader, directory string) error {
	entries, err := os.ReadDir(directory)
	if err != nil {
		return err
	}
	if len(entries) != 0 {
		return errors.New("archive extraction requires an empty staging directory")
	}
	root, err := os.OpenRoot(directory)
	if err != nil {
		return err
	}
	defer root.Close()
	tr := tar.NewReader(source)
	type link struct {
		name, target string
		hard         bool
	}
	var links []link
	type directoryMode struct {
		path string
		mode os.FileMode
	}
	var directories []directoryMode
	seen := map[string]bool{}
	for {
		h, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
		name, err := validMember(h.Name)
		if err != nil {
			return err
		}
		if name == "." {
			if h.Typeflag != tar.TypeDir {
				return errors.New("archive root must be directory")
			}
			directories = append(directories, directoryMode{directory, os.FileMode(h.Mode) & 0777})
			continue
		}
		if seen[name] {
			return fmt.Errorf("duplicate archive member %s", name)
		}
		seen[name] = true
		dest := filepath.Join(directory, filepath.FromSlash(name))
		if err = os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
			return err
		}
		switch h.Typeflag {
		case tar.TypeDir:
			directories = append(directories, directoryMode{dest, os.FileMode(h.Mode) & 0777})
			if err = os.MkdirAll(dest, os.FileMode(h.Mode)&0777|0700); err != nil {
				return err
			}
		case tar.TypeReg, tar.TypeRegA:
			f, err := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_EXCL, os.FileMode(h.Mode)&0777)
			if err != nil {
				return err
			}
			_, copyErr := io.Copy(f, tr)
			err = errors.Join(copyErr, f.Chmod(os.FileMode(h.Mode)&0777), f.Sync(), f.Close())
			if err != nil {
				return err
			}
		case tar.TypeSymlink, tar.TypeLink:
			target := h.Linkname
			if h.Typeflag == tar.TypeSymlink {
				target = path.Join(path.Dir(name), h.Linkname)
			}
			if path.IsAbs(h.Linkname) {
				return errors.New("absolute archive link")
			}
			target, err = validMember(target)
			if err != nil {
				return err
			}
			if h.Typeflag == tar.TypeSymlink {
				target = h.Linkname
			}
			links = append(links, link{name, target, h.Typeflag == tar.TypeLink})
		default:
			return fmt.Errorf("unsupported archive type %d", h.Typeflag)
		}
	}
	for _, l := range links {
		dest := filepath.Join(directory, filepath.FromSlash(l.name))
		target := filepath.Join(directory, filepath.FromSlash(l.target))
		if l.hard {
			info, err := os.Lstat(target)
			if err != nil {
				return err
			}
			if !info.Mode().IsRegular() {
				return errors.New("hardlink target must be regular content")
			}
			if err = os.Link(target, dest); err != nil {
				return err
			}
		} else {
			if err = os.Symlink(l.target, dest); err != nil {
				return err
			}
		}
	}
	// A nested symlink chain can alter the effective target even when each lexical
	// target is internal. Resolve every link only after the complete graph exists.
	for _, l := range links {
		if err := containedLink(root, l.name); err != nil {
			return err
		}
	}
	if err := syncTreeDirs(directory); err != nil {
		return err
	}
	// Apply restrictive modes only once extraction and traversal checks are done.
	// Deepest-first keeps parents accessible, regardless of archive entry order.
	sort.SliceStable(directories, func(i, j int) bool { return len(directories[i].path) > len(directories[j].path) })
	for _, d := range directories {
		f, err := os.Open(d.path)
		if err != nil {
			return err
		}
		if err = errors.Join(f.Chmod(d.mode), f.Sync(), f.Close()); err != nil {
			return err
		}
	}
	return nil
}

// os.Root validates the complete symlink chain without permitting traversal.
// Internal dangling links are valid content; an escaping chain fails with a
// traversal error even if its eventual target does not exist.
func containedLink(root *os.Root, name string) error {
	info, err := root.Stat(name)
	if err == nil {
		if !info.Mode().IsRegular() && !info.IsDir() {
			return errors.New("archive link targets a special file")
		}
		return nil
	}
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}
func syncTreeDirs(directory string) error {
	return filepath.WalkDir(directory, func(name string, e fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if e.IsDir() {
			return SyncDir(name)
		}
		return nil
	})
}
func SyncDir(directory string) error {
	f, err := os.Open(directory)
	if err != nil {
		return err
	}
	return errors.Join(f.Sync(), f.Close())
}
func TreeDigest(directory string) (string, error) {
	h := sha256.New()
	if err := Archive(directory, h); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
func Unchanged(directory string, identity os.FileInfo, digest string) error {
	info, err := os.Lstat(directory)
	if err != nil {
		return err
	}
	if !info.IsDir() || !os.SameFile(info, identity) {
		return errors.New("authorized directory identity changed; local edits and remote archive preserved")
	}
	now, err := TreeDigest(directory)
	if err != nil {
		return err
	}
	if now != digest {
		return errors.New("authorized directory changed during remote execution; local edits and remote archive preserved")
	}
	return nil
}
func Restore(source io.Reader, directory string, identity os.FileInfo, digest string) error {
	stage, err := os.MkdirTemp(filepath.Dir(directory), ".loom-stage-")
	if err != nil {
		return err
	}
	cleanup := true
	defer func() {
		if cleanup {
			_ = os.RemoveAll(stage)
		}
	}()
	if err = Extract(source, stage); err != nil {
		return err
	}
	if err = Unchanged(directory, identity, digest); err != nil {
		return err
	}
	// The root is never absent, even if the controller is killed at publication.
	// Unsupported filesystems fail; a two-rename fallback would reintroduce a gap.
	if err = exchangeDirectories(stage, directory); err != nil {
		return err
	}
	cleanup = false
	if err = Unchanged(stage, identity, digest); err != nil {
		rollback := exchangeDirectories(stage, directory)
		cleanup = rollback == nil
		return errors.Join(err, rollback)
	}
	cleanup = true
	if err = SyncDir(filepath.Dir(directory)); err != nil {
		return err
	}
	return nil
}
